"""复现实际本地检索并输出逐阶段 JSON；不触发 B 站补查。"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from index.catalog import RetrievalScope
from rag.retriever import retrieve_with_status
from rag.video_retrieval import plan_video_retrieval


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--game")
    parser.add_argument("--category")
    parser.add_argument("--video", action="append", default=[])
    parser.add_argument("--verify", action="store_true", help="还用已配置的问答模型核验最终切片覆盖")
    args = parser.parse_args()
    scope = RetrievalScope(game_id=args.game, category_id=args.category, video_ids=args.video)
    plan = plan_video_retrieval(args.question, args.question, scope)

    def trace(stage, **details):
        print(json.dumps({"stage": stage, **details}, ensure_ascii=False))

    trace("plan", query=plan.query, scope=plan.scope.model_dump() if plan.scope else None,
          label=plan.label, blocked=plan.blocked)
    if plan.blocked:
        return
    hits, status, reason = retrieve_with_status(plan.query, scope=plan.scope,
                                               video_hints=plan.hints, trace=trace,
                                               ranking_question=args.question if plan.label else None)
    trace("retrieval_result", status=status, reason=reason)
    if args.verify and hits:
        from app.services import _context_answerability
        trace("answer_check", **_context_answerability(args.question, hits))


if __name__ == "__main__":
    main()
