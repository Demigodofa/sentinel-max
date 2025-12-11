"""Symbolic world model describing domains, resources, and dependencies."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set

from sentinel.logging.logger import get_logger
from sentinel.memory.memory_manager import MemoryManager

logger = get_logger(__name__)


@dataclass
class DomainProfile:
    """Structured description of a work domain."""

    name: str
    capabilities: List[str]
    typical_goals: List[str]


@dataclass
class ResourceDescriptor:
    """Resource representation inside the world model."""

    name: str
    type: str
    metadata: Dict[str, str] = field(default_factory=dict)


class WorldModel:
    """Foundation layer describing Sentinel MAX's operating environment."""

    def __init__(self, memory: MemoryManager, namespace: str = "world_model") -> None:
        self.memory = memory
        self.namespace = namespace
        self.domains: Dict[str, DomainProfile] = {}
        self.resource_catalog: Dict[str, ResourceDescriptor] = {}
        self.dependencies: Dict[str, Dict[str, Set[str]]] = {"requires": {}, "produces": {}}
        self._load_cached_state()
        if not self.domains:
            self._seed_defaults()
            self._persist()

    # ------------------------------------------------------------------
    # Domain registry
    # ------------------------------------------------------------------
    def register_domain(self, name: str, capabilities: Iterable[str], typical_goals: Iterable[str]) -> None:
        profile = DomainProfile(name=name, capabilities=list(capabilities), typical_goals=list(typical_goals))
        self.domains[name] = profile
        self._persist()

    # ------------------------------------------------------------------
    # Query interfaces
    # ------------------------------------------------------------------
    def get_domain(self, goal_text: str) -> DomainProfile:
        normalized = goal_text.lower()
        best_match: Optional[DomainProfile] = None
        best_score = -1
        for domain in self.domains.values():
            score = self._score_domain(domain, normalized)
            if score > best_score:
                best_match = domain
                best_score = score
        if best_match:
            logger.debug("WorldModel matched domain '%s' with score %s", best_match.name, best_score)
            return best_match
        return self.domains.get("automation") or next(iter(self.domains.values()))

    def list_capabilities(self, domain: str) -> List[str]:
        profile = self.domains.get(domain)
        return profile.capabilities if profile else []

    def predict_required_resources(self, goal: str) -> List[ResourceDescriptor]:
        domain = self.get_domain(goal)
        resource_order = self._resources_for_domain(domain.name)
        descriptors: List[ResourceDescriptor] = []
        for resource_name in resource_order:
            descriptor = self.resource_catalog.get(resource_name)
            if descriptor:
                descriptors.append(descriptor)
        self._persist()
        return descriptors

    def predict_dependencies(self, goal: str) -> Dict[str, Dict[str, Set[str]]]:
        resources = self.predict_required_resources(goal)
        resource_types = {resource.type: resource.name for resource in resources}
        requires_graph: Dict[str, Set[str]] = {k: set(v) for k, v in self.dependencies["requires"].items()}
        produces_graph: Dict[str, Set[str]] = {k: set(v) for k, v in self.dependencies["produces"].items()}

        def _add(requirements: Dict[str, Set[str]], source: str, target: str) -> None:
            requirements.setdefault(source, set()).add(target)

        if "pipeline" in resource_types and "data_source" in resource_types:
            _add(requires_graph, resource_types["pipeline"], resource_types["data_source"])
        if "code_artifact" in resource_types and "file_resource" in resource_types:
            _add(requires_graph, resource_types["code_artifact"], resource_types["file_resource"])
        if "service" in resource_types and "code_artifact" in resource_types:
            _add(requires_graph, resource_types["service"], resource_types["code_artifact"])
            _add(produces_graph, resource_types["code_artifact"], resource_types["service"])
        if "browser_context" in resource_types and "data_source" in resource_types:
            _add(requires_graph, resource_types["browser_context"], resource_types["data_source"])

        dependencies = {"requires": requires_graph, "produces": produces_graph}
        self.dependencies = dependencies
        self._persist()
        return dependencies

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_cached_state(self) -> None:
        cached = self.memory.query(self.namespace, key="state")
        if cached:
            payload = cached[0].get("value", {})
            domains_raw = payload.get("domains", {})
            self.domains = {
                name: DomainProfile(**data)
                for name, data in domains_raw.items()
                if isinstance(data, dict)
            }
            resources_raw = payload.get("resources", {})
            self.resource_catalog = {
                name: ResourceDescriptor(**data)
                for name, data in resources_raw.items()
                if isinstance(data, dict)
            }
            dependencies = payload.get("dependencies")
            if isinstance(dependencies, dict):
                self.dependencies = {
                    key: {k: set(v) for k, v in value.items()}
                    for key, value in dependencies.items()
                    if key in {"requires", "produces"}
                }

    def _persist(self) -> None:
        payload = {
            "domains": {name: domain.__dict__ for name, domain in self.domains.items()},
            "resources": {name: resource.__dict__ for name, resource in self.resource_catalog.items()},
            "dependencies": {
                relation: {k: sorted(list(v)) for k, v in relations.items()}
                for relation, relations in self.dependencies.items()
            },
        }
        self.memory.store_fact(self.namespace, key="state", value=payload, metadata={"source": "world_model"})

    def _seed_defaults(self) -> None:
        default_domains = [
            DomainProfile("coding", ["analysis", "debugging", "implementation", "testing"], ["fix bug", "refactor", "build tool", "optimize scraper"]),
            DomainProfile("multi-service", ["microservices", "api design", "service composition", "orchestration"], ["build microservice", "compose services", "design api"]),
            DomainProfile("pipelines", ["data ingestion", "transforms", "scheduling", "quality checks"], ["design a data pipeline", "batch processing", "stream processing"]),
            DomainProfile("devops", ["deployment", "monitoring", "infrastructure", "ci/cd"], ["deploy service", "configure ci", "observability"]),
            DomainProfile("web tasks", ["scraping", "extraction", "navigation", "session management"], ["pull prices", "scrape website", "simulate browser", "collect links"]),
            DomainProfile("research", ["literature review", "evidence collection", "summarization", "citation"], ["investigate topic", "compare approaches", "gather references"]),
            DomainProfile("optimization", ["profiling", "performance tuning", "efficiency", "coding"], ["optimize the scraper", "reduce latency", "improve throughput"]),
            DomainProfile("automation", ["workflow orchestration", "scheduling", "eventing", "integration"], ["automate task", "connect systems", "schedule workflow"]),
        ]
        for domain in default_domains:
            self.register_domain(domain.name, domain.capabilities, domain.typical_goals)
        self._seed_resources()

    def _seed_resources(self) -> None:
        resource_templates = [
            ResourceDescriptor("file_resource", "file_resource", {"description": "Local or remote files"}),
            ResourceDescriptor("code_artifact", "code_artifact", {"description": "Source code or binaries"}),
            ResourceDescriptor("service", "service", {"description": "APIs or microservices"}),
            ResourceDescriptor("pipeline", "pipeline", {"description": "Data processing pipeline"}),
            ResourceDescriptor("browser_context", "browser_context", {"description": "Automated browser session"}),
            ResourceDescriptor("data_source", "data_source", {"description": "Databases, APIs, or web sources"}),
        ]
        for descriptor in resource_templates:
            self.resource_catalog[descriptor.name] = descriptor
        self.dependencies = {"requires": {}, "produces": {}}

    def _score_domain(self, domain: DomainProfile, normalized_goal: str) -> int:
        score = 0
        for phrase in domain.typical_goals:
            if phrase in normalized_goal:
                score += 3
        for capability in domain.capabilities:
            if capability in normalized_goal:
                score += 2
        keyword_overrides = {
            "microservice": "multi-service",
            "service": "multi-service",
            "pipeline": "pipelines",
            "deploy": "devops",
            "scrape": "web tasks",
            "scraper": "web tasks",
            "optimize": "optimization",
            "automation": "automation",
            "browser": "web tasks",
        }
        matched_keywords = [keyword for keyword, domain_name in keyword_overrides.items() if domain.name == domain_name and keyword in normalized_goal]
        if matched_keywords:
            score += 4
        if domain.name == "optimization" and "optimize" in normalized_goal:
            score += 3
        return score

    def _resources_for_domain(self, domain_name: str) -> List[str]:
        mapping = {
            "coding": ["file_resource", "code_artifact"],
            "multi-service": ["code_artifact", "service", "data_source"],
            "pipelines": ["data_source", "pipeline", "file_resource"],
            "devops": ["service", "pipeline", "code_artifact"],
            "web tasks": ["browser_context", "data_source", "code_artifact"],
            "research": ["data_source", "browser_context", "file_resource"],
            "optimization": ["code_artifact", "service", "pipeline", "file_resource"],
            "automation": ["service", "pipeline", "code_artifact", "data_source"],
        }
        return mapping.get(domain_name, ["file_resource", "data_source"])
