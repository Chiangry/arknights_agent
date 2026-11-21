"""PostgreSQL 聊天历史；仅本机单用户部署。"""
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from index.store import _conn

DEFAULT_TITLE = "新战术对话"
INTERRUPTED = "这次回答已中断，可以重新提问。"
MUTABLE_FIELDS = {"title", "scope", "scoped_video_title", "agent_enabled"}


class ChatConflict(Exception):
    pass


def list_threads():
    with _conn() as conn, conn.cursor(row_factory=dict_row) as cursor:
        return cursor.execute("""
            SELECT t.*, EXISTS(SELECT 1 FROM chat_messages m WHERE m.thread_id=t.id AND m.status='running') AS running
            FROM chat_threads t
            ORDER BY COALESCE(last_message_at, created_at) DESC, id
        """).fetchall()


def get_thread(thread_id):
    with _conn() as conn, conn.cursor(row_factory=dict_row) as cursor:
        thread = cursor.execute("SELECT * FROM chat_threads WHERE id=%s", (thread_id,)).fetchone()
        if thread is not None:
            thread["messages"] = cursor.execute(
                "SELECT * FROM chat_messages WHERE thread_id=%s ORDER BY id", (thread_id,),
            ).fetchall()
        return thread


def create_thread(thread_id, title, scope, scoped_video_title):
    with _conn() as conn, conn.cursor(row_factory=dict_row) as cursor:
        cursor.execute("""
            INSERT INTO chat_threads(id,title,scope,scoped_video_title) VALUES (%s,%s,%s,%s)
            ON CONFLICT (id) DO NOTHING
        """, (thread_id, title, Jsonb(scope), scoped_video_title))
        return cursor.execute("SELECT * FROM chat_threads WHERE id=%s", (thread_id,)).fetchone()


def update_thread(thread_id, changes):
    with _conn() as conn, conn.cursor(row_factory=dict_row) as cursor:
        keys = [key for key in changes if key in MUTABLE_FIELDS]
        if not keys:
            return cursor.execute("SELECT * FROM chat_threads WHERE id=%s", (thread_id,)).fetchone()
        assignments = sql.SQL(", ").join(sql.SQL("{}=%s").format(sql.Identifier(key)) for key in keys)
        values = [Jsonb(changes[key]) if key == "scope" else changes[key] for key in keys]
        return cursor.execute(
            sql.SQL("UPDATE chat_threads SET {} WHERE id=%s RETURNING *").format(assignments),
            (*values, thread_id),
        ).fetchone()


def delete_thread(thread_id):
    with _conn() as conn:
        return conn.execute("DELETE FROM chat_threads WHERE id=%s", (thread_id,)).rowcount == 1


def begin_turn(thread_id, request_id, question):
    """锁住会话；同一个请求 ID 只建立一组消息。"""
    with _conn() as conn, conn.cursor(row_factory=dict_row) as cursor:
        thread = cursor.execute("SELECT * FROM chat_threads WHERE id=%s FOR UPDATE", (thread_id,)).fetchone()
        if thread is None:
            return None
        existing = cursor.execute("""
            SELECT a.*, u.content AS question FROM chat_messages a JOIN chat_messages u
              ON a.thread_id=u.thread_id AND a.request_id=u.request_id AND u.role='user'
            WHERE a.thread_id=%s AND a.request_id=%s AND a.role='assistant'
        """, (thread_id, request_id)).fetchone()
        if existing:
            if existing["question"] != question:
                raise ChatConflict("同一个请求编号不能发送不同问题。")
            if existing["status"] == "running":
                raise ChatConflict("这条消息仍在处理中，请查看会话历史。")
            return {"replay": existing}
        if cursor.execute("SELECT 1 FROM chat_messages WHERE thread_id=%s AND status='running'",
                          (thread_id,)).fetchone():
            raise ChatConflict("当前会话还有回答正在处理。")
        history = cursor.execute("""
            SELECT m.role,m.content FROM chat_messages m
            JOIN chat_messages a ON a.thread_id=m.thread_id AND a.request_id=m.request_id
                  AND a.role='assistant' AND a.status='completed'
            WHERE m.thread_id=%s ORDER BY m.id DESC LIMIT 8
        """, (thread_id,)).fetchall()
        cursor.execute("""
            INSERT INTO chat_messages(thread_id,request_id,role,content,status)
            VALUES (%s,%s,'user',%s,'completed')
        """, (thread_id, request_id, question))
        assistant = cursor.execute("""
            INSERT INTO chat_messages(thread_id,request_id,role,status,agent_mode)
            VALUES (%s,%s,'assistant','running',%s) RETURNING id
        """, (thread_id, request_id, thread["agent_enabled"])).fetchone()
        cursor.execute("""
            UPDATE chat_threads SET last_message_at=now(),
              title=CASE WHEN last_message_at IS NULL AND title=%s THEN %s ELSE title END
            WHERE id=%s
        """, (DEFAULT_TITLE, question[:18] + ("…" if len(question) > 18 else ""), thread_id))
        return {"thread": thread, "assistant_id": assistant["id"], "history": list(reversed(history))}


def checkpoint(thread_id, message_id, snapshot, game_state=None):
    with _conn() as conn:
        if game_state is not None:
            conn.execute("UPDATE chat_threads SET game_state=%s WHERE id=%s", (Jsonb(game_state), thread_id))
        changed = conn.execute("""
            UPDATE chat_messages SET content=%s,citations=%s,steps=%s,status=%s,error=%s
            WHERE id=%s AND thread_id=%s AND status='running'
        """, (snapshot["content"], Jsonb(snapshot["citations"]), Jsonb(snapshot["steps"]),
              snapshot["status"], snapshot.get("error"), message_id, thread_id)).rowcount
        return changed == 1


def interrupt_running():
    with _conn() as conn:
        conn.execute("UPDATE chat_messages SET status='interrupted',error=%s WHERE status='running'",
                     (INTERRUPTED,))
