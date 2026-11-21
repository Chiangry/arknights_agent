"""会话问答与浏览器连接分离，SSE 只消费事件。"""
import logging
from queue import Empty, Queue
from threading import Thread
from time import monotonic

from app import chat_store
from app.sse import format_sse

logger = logging.getLogger(__name__)
ERROR_MESSAGE = "回答未能完成，可以重新提问。"


def _citation_refs(data):
    # 保存引用位置，不复制整段知识库文本。
    return [{k: v for k, v in cite.items() if k != "text"} for cite in data.get("citations", [])]


def replay(saved):
    yield format_sse("citations", {"citations": saved["citations"]})
    if saved["content"]:
        yield format_sse("delta", {"text": saved["content"]})
    if saved["status"] == "completed":
        yield format_sse("done", {"citations": saved["citations"]})
    else:
        yield format_sse("error", {"message": saved["error"] or ERROR_MESSAGE})


def _run(thread_id, message_id, generate, publish):
    snapshot = {"content": "", "citations": [], "steps": [], "status": "running"}
    steps = {}
    first_content = True
    last_write = monotonic()

    def persist(state=None):
        nonlocal last_write
        last_write = monotonic()
        return chat_store.checkpoint(thread_id, message_id, snapshot, state)

    try:
        for item in generate():
            event, data = item["event"], item["data"]
            save = False
            state = None
            if event == "agent_step":
                steps[data["stage"]] = data
                snapshot["steps"] = list(steps.values())
                save = True
            elif event == "game_state":
                state, save = data, True
            elif event in ("answer_replace", "delta"):
                text = data.get("text", "")
                if event == "answer_replace":
                    snapshot["content"] = text
                    snapshot["citations"] = _citation_refs(data)
                else:
                    snapshot["content"] += text
                save = first_content or event == "answer_replace" or monotonic() - last_write >= 1
                first_content = False
            elif event == "citations":
                snapshot["citations"] = _citation_refs(data)
                save = True
            elif event == "done":
                snapshot["citations"] = _citation_refs(data)
                snapshot["status"] = "completed"
                save = True
            if save and not persist(state):
                publish("error", {"message": "会话已结束或删除。"})
                return
            publish(event, data)
            if event == "done":
                return
        raise RuntimeError("问答未产生结束事件")
    except Exception:
        logger.exception("会话回答失败 thread=%s message=%s", thread_id, message_id)
        try:
            snapshot.update(status="failed", error=ERROR_MESSAGE)
            persist()
        except Exception:
            logger.exception("未能保存会话失败状态")
        publish("error", {"message": ERROR_MESSAGE})


def start(thread_id, message_id, generate):
    queue = Queue()

    def publish(event, data):
        queue.put((event, data))

    def work():
        try:
            _run(thread_id, message_id, generate, publish)
        finally:
            queue.put(None)

    Thread(target=work, daemon=True, name=f"chat-turn-{message_id}").start()

    def stream():
        while True:
            try:
                item = queue.get(timeout=10)
            except Empty:
                # SSE 注释，在模型长时间无事件时维持连接。
                yield ": waiting\n\n"
                continue
            if item is None:
                break
            yield format_sse(*item)

    return stream()
