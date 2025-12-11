"""FastAPI entry point for Sentinel MAX."""
from __future__ import annotations

try:
    from fastapi import FastAPI
except Exception:  # pragma: no cover - optional dependency
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


from sentinel.controller import SentinelController

app = FastAPI()
controller = SentinelController()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(message: str):
    return {"response": controller.process_input(message)}
