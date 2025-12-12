"""Conversational intent and goal normalization engine."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Protocol, Tuple

from sentinel.logging.logger import get_logger
from sentinel.memory.memory_manager import MemoryManager
from sentinel.tools.registry import ToolRegistry
from sentinel.world.model import WorldModel

logger = get_logger(__name__)


@dataclass
class IntentResult:
    intent: str
    confidence: float
    domain: str
    rationale: str = ""


@dataclass
class NormalizedGoal:
    """Structured goal passed to downstream planners."""

    type: str
    domain: str
    parameters: Dict[str, object] = field(default_factory=dict)
    constraints: List[str] = field(default_factory=list)
    preferences: List[str] = field(default_factory=list)
    context: Dict[str, object] = field(default_factory=dict)
    source_intent: Optional[IntentResult] = None
    ambiguities: List[str] = field(default_factory=list)
    raw_text: str = ""

    def as_goal_statement(self) -> str:
        parameter_view = ", ".join(f"{k}={v}" for k, v in sorted(self.parameters.items()))
        constraint_view = "; ".join(sorted(self.constraints)) if self.constraints else "none"
        preference_view = "; ".join(sorted(self.preferences)) if self.preferences else "default"
        return (
            f"Goal[{self.type}] in domain={self.domain} "
            f"with parameters: {parameter_view or 'none'}; "
            f"constraints: {constraint_view}; preferences: {preference_view}"
        )


class IntentClassifier:
    """Deterministic intent classifier grounded in world model hints."""

    def __init__(self, world_model: WorldModel) -> None:
        self.world_model = world_model
        self._domain_map: Dict[str, str] = {
            "coding": "coding",
            "fix": "coding",
            "bug": "coding",
            "debug": "coding",
            "refactor": "coding",
            "optimize": "optimization",
            "optimization": "optimization",
            "benchmark": "optimization",
            "improve": "optimization",
            "speed": "optimization",
            "faster": "optimization",
            "deploy": "devops",
            "devops": "devops",
            "service": "multi_service",
            "microservice": "multi_service",
            "web": "web_interaction",
            "browser": "web_interaction",
            "automate": "automation",
            "automation": "automation",
            "research": "research",
            "workflow": "real_world_planning",
            "weekly": "real_world_planning",
            "plan": "real_world_planning",
        }

    def classify(self, text: str) -> IntentResult:
        normalized = text.lower()
        domain = self._predict_domain(normalized)
        intent = self._intent_from(normalized, domain)
        confidence = self._confidence_score(normalized, domain, intent)
        rationale = f"domain={domain}; intent={intent}; confidence={confidence}"
        logger.debug("Intent classified: %s", rationale)
        return IntentResult(intent=intent, confidence=confidence, domain=domain, rationale=rationale)

    def _predict_domain(self, normalized: str) -> str:
        for keyword, domain in self._domain_map.items():
            if keyword in normalized:
                return domain
        domain_profile = self.world_model.get_domain(normalized)
        return domain_profile.name.replace(" ", "_")

    def _intent_from(self, normalized: str, domain: str) -> str:
        if domain == "real_world_planning":
            return "schedule_planning"
        if "workflow" in normalized and "week" in normalized:
            return "schedule_planning"
        if "scrape" in normalized or "crawl" in normalized:
            return "web_scraping"
        if "optimiz" in normalized:
            return "optimize_system"
        if any(keyword in normalized for keyword in ["speed up", "faster", "improve performance"]):
            return "performance_revision"
        if any(keyword in normalized for keyword in ["fix", "bug", "issue", "debug"]):
            return "general_goal"
        if "deploy" in normalized or "ci" in normalized:
            return "devops_pipeline"
        if "service" in normalized or "api" in normalized:
            return "build_microservice"
        if "benchmark" in normalized or "rewrite" in normalized:
            return "performance_revision"
        if domain == "automation":
            return "workflow_automation"
        if domain == "research":
            return "research_task"
        return "general_goal"

    def _confidence_score(self, normalized: str, domain: str, intent: str) -> float:
        score = 0.55
        score += 0.1 if domain in normalized else 0.0
        score += 0.1 if intent != "general_goal" else 0.0
        score += 0.1 if any(keyword in normalized for keyword in ["benchmark", "optimize", "microservice", "browser"]) else 0.0
        return min(round(score, 2), 0.98)


class IntentEnginePlugin(Protocol):
    """Extend the intent engine with optional tuning hooks."""

    def enhance_parameters(
        self, text: str, intent: IntentResult, parameters: Dict[str, object]
    ) -> Dict[str, object]:
        ...

    def adjust_preferences(
        self,
        text: str,
        intent: IntentResult,
        parameters: Dict[str, object],
        base_preferences: List[str],
    ) -> List[str]:
        ...

    def adjust_ambiguities(
        self,
        text: str,
        intent: IntentResult,
        parameters: Dict[str, object],
        ambiguities: List[str],
    ) -> List[str]:
        ...


class GoalExtractor:
    """Convert natural language into a concrete technical target."""

    def __init__(
        self,
        memory: MemoryManager,
        world_model: WorldModel,
        tool_registry: ToolRegistry,
    ) -> None:
        self.memory = memory
        self.world_model = world_model
        self.tool_registry = tool_registry

    def extract(self, text: str, intent: IntentResult) -> Tuple[str, Dict[str, object]]:
        domain_profile = self.world_model.get_domain(text)
        capabilities = self.world_model.list_capabilities(domain_profile.name)
        resources = [descriptor.name for descriptor in self.world_model.predict_required_resources(text)]
        context_window = self.memory.recall_recent(limit=4, namespace="dialog_turns")
        hints = self.tool_registry.describe_tools()
        goal_type = intent.intent
        metadata = {
            "domain_capabilities": capabilities,
            "resources": resources,
            "tools": hints,
            "recent_turns": context_window,
        }
        return goal_type, metadata


class ParameterResolver:
    """Extract actionable parameters and resolve references from memory."""

    def __init__(self, memory: MemoryManager, world_model: WorldModel) -> None:
        self.memory = memory
        self.world_model = world_model

    def resolve(self, text: str, metadata: Dict[str, object]) -> Dict[str, object]:
        normalized = text.lower()
        parameters: Dict[str, object] = {}
        parameters.update({k: v for k, v in metadata.items() if k in {"domain_capabilities", "resources"}})
        if "http" in text or "www" in text:
            parameters["target_website"] = self._extract_url(text)
        if "endpoint" in normalized or "api" in normalized:
            parameters["endpoint"] = self._extract_endpoint(text)
        if "file" in normalized or "folder" in normalized:
            parameters["file_path"] = self._resolve_latest("file_resource")
        if "latest" in normalized or "newest" in normalized:
            parameters["latest_artifact"] = self._resolve_latest("code_artifact")
        if "tool" in normalized and "yesterday" in normalized:
            parameters["referenced_tool"] = self._resolve_latest("tools")
        optimization_metric = self._infer_optimization_metric(normalized)
        if optimization_metric:
            parameters.setdefault("optimization_metric", optimization_metric)
        parameters["browser_actions"] = self._derive_browser_actions(normalized)
        return parameters

    def _resolve_latest(self, namespace: str) -> object:
        record = self.memory.latest(namespace)
        if record:
            return record.get("value")
        return {"namespace": namespace, "status": "unknown"}

    def _extract_url(self, text: str) -> str:
        tokens = text.split()
        for token in tokens:
            if token.startswith("http") or token.startswith("www"):
                return token.strip(".,")
        return ""

    def _extract_endpoint(self, text: str) -> str:
        for token in text.split():
            if "/" in token and not token.startswith("http"):
                return token.strip(",")
        return ""

    def _derive_browser_actions(self, normalized: str) -> List[str]:
        actions: List[str] = []
        if "login" in normalized or "log in" in normalized:
            actions.append("authenticate")
        if "fill" in normalized or "form" in normalized:
            actions.append("fill_form")
        if "navigate" in normalized or "go to" in normalized:
            actions.append("navigate")
        return actions

    def _infer_optimization_metric(self, normalized: str) -> Optional[str]:
        if any(phrase in normalized for phrase in ["latency", "response time", "faster", "speed"]):
            return "latency"
        if any(keyword in normalized for keyword in ["throughput", "qps", "rps", "traffic"]):
            return "throughput"
        if any(keyword in normalized for keyword in ["memory", "size", "footprint", "lighter", "smaller"]):
            return "size"
        if "cost" in normalized:
            return "cost"
        return None


class AmbiguityScanner:
    """Detect ambiguous phrasing and request clarification when needed."""

    def __init__(self, threshold: float = 0.5) -> None:
        self.threshold = threshold
        self.pronoun_pattern = re.compile(r"\b(it|that|this)\b")

    def scan(self, intent: IntentResult, parameters: Dict[str, object], text: str) -> List[str]:
        questions: List[str] = []
        normalized = text.lower()
        if intent.confidence < self.threshold:
            questions.append("Please clarify the exact outcome you want and priority constraints.")
        if self.pronoun_pattern.search(normalized) and not self._has_grounded_target(parameters):
            questions.append("Which artifact or service does 'it/that' refer to?")
        if "optimize" in normalized and "optimization_metric" not in parameters and "metric" not in normalized:
            questions.append("Which optimization metric should be used (latency, throughput, size)?")
        if "form" in normalized and not parameters.get("target_website"):
            questions.append("Which website hosts the form to fill?")
        return questions

    def _has_grounded_target(self, parameters: Dict[str, object]) -> bool:
        anchored_keys = {"target_website", "file_path", "endpoint", "latest_artifact", "referenced_tool"}
        return any(parameters.get(key) for key in anchored_keys)


class IntentEngine:
    """Orchestrates classification, goal extraction, parameter resolution, and disambiguation."""

    def __init__(
        self,
        memory: MemoryManager,
        world_model: WorldModel,
        tool_registry: ToolRegistry,
        ambiguity_threshold: float = 0.5,

        plugins: Optional[Iterable[IntentEnginePlugin]] = None,

    ) -> None:
        self.classifier = IntentClassifier(world_model)
        self.extractor = GoalExtractor(memory, world_model, tool_registry)
        self.resolver = ParameterResolver(memory, world_model)
        self.scanner = AmbiguityScanner(threshold=ambiguity_threshold)
        self.world_model = world_model
        self.memory = memory
        self.plugins: List[IntentEnginePlugin] = list(plugins or [])

    def run(self, text: str) -> NormalizedGoal:
        intent = self.classifier.classify(text)
        goal_type, metadata = self.extractor.extract(text, intent)
        parameters = self.resolver.resolve(text, metadata)
        for plugin in self.plugins:
            enriched = plugin.enhance_parameters(text, intent, parameters)
            if enriched:
                parameters.update(enriched)
        ambiguities = self.scanner.scan(intent, parameters, text)
        
        for plugin in self.plugins:
            plugin_ambiguities = plugin.adjust_ambiguities(text, intent, parameters, ambiguities)
            if plugin_ambiguities:
                ambiguities = plugin_ambiguities
        preferences = ["Professional", "Helpful", "Conversational", "Concise"]
        for plugin in self.plugins:
            plugin_preferences = plugin.adjust_preferences(text, intent, parameters, preferences)
            if plugin_preferences:
                preferences = self._merge_preferences(preferences, plugin_preferences)

        preferences = ["Professional", "Helpful", "Conversational", "Concise"]

        context = {
            "world": metadata.get("resources", []),
            "tools": metadata.get("tools", {}),
            "recent_turns": metadata.get("recent_turns", []),
        }
        normalized = NormalizedGoal(
            type=goal_type,
            domain=intent.domain,
            parameters=parameters,
            constraints=metadata.get("constraints", []) if isinstance(metadata, dict) else [],
            preferences=preferences,
            context=context,
            source_intent=intent,
            ambiguities=ambiguities,
            raw_text=text,
        )
        self.memory.store_fact(
            "normalized_goals",
            key=None,
            value={"goal": normalized.as_goal_statement(), "ambiguities": ambiguities},
            metadata={"intent": intent.intent, "domain": intent.domain},
        )
        return normalized

    def _merge_preferences(self, base: List[str], additions: List[str]) -> List[str]:
        merged: List[str] = []
        seen = set()
        for pref in [*base, *additions]:
            if pref not in seen:
                merged.append(pref)
                seen.add(pref)
        return merged


class PreferenceLearningPlugin(IntentEnginePlugin):
    """Lightweight plugin that captures tone hints and reuses them in future turns."""

    def __init__(self, memory: MemoryManager, namespace: str = "conversation.preferences") -> None:
        self.memory = memory
        self.namespace = namespace

    def enhance_parameters(
        self, text: str, intent: IntentResult, parameters: Dict[str, object]
    ) -> Dict[str, object]:
        return {}

    def adjust_preferences(
        self,
        text: str,
        intent: IntentResult,
        parameters: Dict[str, object],
        base_preferences: List[str],
    ) -> List[str]:
        normalized = text.lower()
        learned: List[str] = []
        record = self.memory.recall_recent(limit=1, namespace=self.namespace)
        if record:
            latest_preferences = record[0].get("value", {})
            if isinstance(latest_preferences, dict):
                learned = list(latest_preferences.get("preferences", []))
        if any(keyword in normalized for keyword in ["casual", "friendly", "approachable", "warm"]):
            learned.append("Casual")
        merged = self._merge_preferences(base_preferences, learned)
        self.memory.store_fact(
            self.namespace,
            key=None,
            value={"preferences": merged, "intent": intent.intent, "text": text},
            metadata={"domain": intent.domain},
        )
        return merged

    def adjust_ambiguities(
        self,
        text: str,
        intent: IntentResult,
        parameters: Dict[str, object],
        ambiguities: List[str],
    ) -> List[str]:
        return ambiguities

    def _merge_preferences(self, base: List[str], additions: List[str]) -> List[str]:
        merged: List[str] = []
        seen = set()
        for pref in [*base, *additions]:
            if pref not in seen:
                merged.append(pref)
                seen.add(pref)
        return merged
