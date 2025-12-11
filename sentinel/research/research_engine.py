"""Autonomous research engine coordinating discovery, ranking, and semantics."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sentinel.logging.logger import get_logger
from sentinel.memory.memory_manager import MemoryManager
from sentinel.policy.policy_engine import PolicyEngine
from sentinel.research.domain_extractor import DomainKnowledgeExtractor
from sentinel.research.effect_predictor import ToolEffectPredictorV2
from sentinel.research.source_ranker import SourceRanker
from sentinel.research.tool_semantics import ToolSemanticsExtractor
from sentinel.simulation.sandbox import SimulationSandbox
from sentinel.tools.registry import ToolRegistry

logger = get_logger(__name__)


class AutonomousResearchEngine:
    """Coordinate research cycles and feed findings into simulations and planning."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        memory: MemoryManager,
        policy_engine: PolicyEngine,
        simulation_sandbox: Optional[SimulationSandbox] = None,
        predictor: Optional[ToolEffectPredictorV2] = None,
    ) -> None:
        self.tool_registry = tool_registry
        self.memory = memory
        self.policy_engine = policy_engine
        self.simulation_sandbox = simulation_sandbox
        self.predictor = predictor or ToolEffectPredictorV2()
        self.domain_extractor = DomainKnowledgeExtractor()
        self.tool_semantics_extractor = ToolSemanticsExtractor()

    def run_research_cycle(self, query: str, depth: int = 1):
        self.policy_engine.check_research_limits(query, depth)
        raw_results: List[Dict[str, Any]] = []
        for hop in range(max(1, depth)):
            search_payload = self.tool_registry.call("web_search", query=query)
            for idx, snippet in enumerate(search_payload):
                source_label = f"search://{query}/{hop}-{idx}"
                safe_url = snippet if snippet.startswith("http") else f"https://research.local/{idx}"
                extraction = self.tool_registry.call(
                    "internet_extract", url=safe_url, store=False, namespace="research"
                )
                raw_results.append(
                    {
                        "source": source_label,
                        "content": extraction.get("clean_text") or snippet,
                        "metadata": {"summary": extraction.get("summary", ""), "query": query},
                    }
                )
        ranked = self.rank_sources(raw_results)
        domain_data = self.extract_domain_knowledge(ranked)
        tool_data = self.extract_tool_semantics(ranked)
        semantic_models = self.build_semantic_models(domain_data, tool_data)
        self.update_predictors(semantic_models)
        self.store_research_outputs(semantic_models, raw_results, ranked)
        return semantic_models

    def ingest_results(self, raw_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        cleaned: List[Dict[str, Any]] = []
        for entry in raw_results:
            if not entry:
                continue
            content = str(entry.get("content", "")).strip()
            if not content:
                continue
            if len(cleaned) >= getattr(self.policy_engine, "max_documents_per_cycle", len(raw_results)):
                break
            cleaned.append({
                "source": entry.get("source", "unknown"),
                "content": content,
                "metadata": entry.get("metadata", {}),
            })
        self.memory.store_fact("research.raw", key=None, value=cleaned)
        return cleaned

    def rank_sources(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ingested = self.ingest_results(documents)
        ranker = SourceRanker(
            query=documents[0].get("metadata", {}).get("query", "") if documents else "",
            memory=self.memory,
        )
        ranked = ranker.rank(ingested)
        self.memory.store_fact("research.ranked", key=None, value=ranked)
        return ranked

    def extract_domain_knowledge(self, ranked_docs: List[Dict[str, Any]]) -> Dict:
        domain = self.domain_extractor.extract(ranked_docs)
        self.memory.store_fact("research.domain", key=None, value=domain)
        return domain

    def extract_tool_semantics(self, ranked_docs: List[Dict[str, Any]]) -> Dict:
        semantics = self.tool_semantics_extractor.extract_semantics(ranked_docs)
        merged = self.tool_semantics_extractor.merge_with_existing(self.tool_registry, semantics)
        self.memory.store_fact("research.tools", key=None, value=merged)
        return merged

    def build_semantic_models(self, domain_data: Dict, tool_data: Dict) -> Dict[str, Any]:
        models = {
            "domain_model": domain_data,
            "tool_semantics": tool_data,
            "predictive_effects": self.predictor.semantic_profiles,
        }
        self.memory.store_fact("research.models", key=None, value=models)
        return models

    def update_predictors(self, semantic_models: Dict[str, Any]) -> None:
        tool_semantics = semantic_models.get("tool_semantics", {})
        self.predictor.update_model(tool_semantics)
        if self.simulation_sandbox:
            self.simulation_sandbox.set_semantic_profiles(self.predictor.semantic_profiles)
        self.memory.store_fact(
            "research.predictor_updates",
            key=None,
            value={"tools": list(tool_semantics.keys()), "count": len(tool_semantics)},
        )

    def store_research_outputs(self, models: Dict[str, Any], raw: List[Dict], ranked: List[Dict]) -> None:
        payload = {
            "raw_count": len(raw),
            "ranked_count": len(ranked),
            "models": list(models.keys()),
        }
        self.memory.store_fact("research.raw", key="latest_metadata", value=payload)
        self.memory.store_fact("research.ranked", key="latest_metadata", value=payload)
        self.memory.store_fact("research.models", key="latest_metadata", value=models)
        if models.get("tool_semantics"):
            self.policy_engine.validate_semantic_updates(models["tool_semantics"])
        summary = {
            "domain": models.get("domain_model", {}),
            "tools": models.get("tool_semantics", {}),
            "effects": self.predictor.semantic_profiles,
        }
        self.memory.store_fact("research.domain", key="latest_summary", value=summary)
