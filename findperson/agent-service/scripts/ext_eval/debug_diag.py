import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.agent.chain import build_orchestrator
from app.agent.orchestrator import ServiceRegistry
from app.contracts.agent_state import (
    AgentState, Intent, IntentState, QueryType, RequestState, UserContext,
    UnderstandingState,
)
from app.core.db import close_pool, init_pool


class _GoldIntentService:
    def __init__(self, case):
        self._case = case
    async def classify(self, query):
        return IntentState(
            intent=Intent(self._case["intent"]),
            query_type=QueryType(self._case["query_type"]),
            confidence=1.0,
        )


class _GoldStructurer:
    def __init__(self, case):
        self._case = case
    async def structure(self, query):
        u = UnderstandingState()
        names = self._case["gold"].get("concept_names", [])
        u.mentioned_systems = list(names)
        u.explicit_terms = list(names)
        u.field_sources = {f"systems:{n}": "explicit" for n in names}
        return u


async def main():
    await init_pool()
    case = {
        "id": "T0004", "query": "Spring服务启动缓慢，现在应该先找谁处理？",
        "intent": "find_person", "query_type": "explicit_responsibility",
        "gold": {"concept_names": ["Java后端开发"]},
    }
    services = ServiceRegistry({
        "intent_service": _GoldIntentService(case),
        "query_structurer": _GoldStructurer(case),
    })
    orch = build_orchestrator(services)
    state = AgentState(
        request=RequestState(
            trace_id="debug-T0004", run_id="debug",
            user_context=UserContext(user_id="p-0001", name="评测"),
            original_query=case["query"], normalized_query=case["query"],
        )
    )
    final = await orch.run(state)
    print("intent:", final.intent.intent, final.intent.query_type)
    print("retrieval structured:", [e.get("person_id") for e in final.retrieval.structured_candidates][:10])
    print("retrieval rag_docs:", [d.get("document_id") for d in final.retrieval.rag_documents])
    print("retrieval rag_person_evidence:", [e.get("person_id") for e in final.retrieval.rag_person_evidence][:10])
    print("ranked:", [c.get("person_id") for c in final.ranking.ranked_candidates][:10])
    await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
