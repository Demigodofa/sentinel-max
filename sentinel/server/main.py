"""FastAPI entry point for Sentinel MAX."""
from __future__ import annotations

import importlib.util
from typing import Any, Dict, Optional

if importlib.util.find_spec("fastapi") and importlib.util.find_spec("pydantic"):
    from fastapi import FastAPI
    from pydantic import BaseModel
else:  # pragma: no cover - optional dependency shim
    class FastAPI:  # type: ignore
        def __init__(self, *_, **__):
            self.routes = []

        def get(self, *_args, **_kwargs):  # pragma: no cover - mock
            def decorator(func):
                return func

            return decorator

        def post(self, *_args, **_kwargs):
            def decorator(func):
                return func

            return decorator

    class BaseModel:  # type: ignore  # pragma: no cover - mock
        pass

from sentinel.controller import SentinelController

app = FastAPI()
controller = SentinelController()


class QueryRequest(BaseModel):  # pragma: no cover - simple data holder
    query: str
    top_k: Optional[int] = 3
    namespace: Optional[str] = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(message: str):
    return {"response": controller.process_input(message)}


@app.get("/memory/symbolic")
def get_symbolic_memory() -> Dict[str, Any]:
    return controller.memory.symbolic.export_state()


@app.get("/memory/vector")
def get_vector_memory() -> Dict[str, Any]:
    return controller.memory.vector.export_state()


@app.post("/memory/query")
def query_memory(request: QueryRequest) -> Dict[str, Any]:
    results = controller.memory.semantic_search(
        request.query, top_k=request.top_k or 3, namespace=request.namespace
    )
    return {"results": results}
