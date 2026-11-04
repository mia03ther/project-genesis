"""The Security Lab's HTTP API (FastAPI). It exposes predefined mission actions only.

There is deliberately no endpoint that forwards RPC calls, sends arbitrary
transactions, runs code or touches keys: the browser can open the case, read
evidence by id, ask for a hint, pick a strategy by id, replay, reset and
download the report. Every input is validated twice: by its declared shape
here and against the mission content in :mod:`genesis.lab.session`.

The server is meant for one local player. It binds to loopback, rejects
requests whose ``Host`` header is not local (a DNS-rebinding guard), and
sends a strict Content-Security-Policy with the bundled frontend.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Request
from fastapi import Path as PathParam
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from genesis import __version__
from genesis.harness.chain import AnvilChain, AnvilProcess, JsonRpcClient
from genesis.harness.manifest import ScenarioManifest, load_manifest
from genesis.harness.runner import ScenarioRunner
from genesis.lab.content import MissionContent, load_mission
from genesis.lab.requests import RequestLedger
from genesis.lab.session import MissionError, MissionSession
from genesis.models import GenesisError

DEFAULT_SCENARIO = "wrong-recipient"
LOCAL_HOSTS = ("127.0.0.1", "localhost")
_ID = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
    "form-action 'none'; frame-src https://app.remix.live https://remix.ethereum.org"
)


@dataclass(frozen=True)
class LabConfig:
    scenarios_dir: Path = Path("scenarios")
    scenario: str = DEFAULT_SCENARIO
    anvil_executable: str = "anvil"
    #: Use an already running local Anvil node instead of starting one.
    rpc_url: str | None = None
    #: The built frontend (``frontend/dist``) to serve at ``/``, if any.
    static_dir: Path | None = None
    allowed_hosts: tuple[str, ...] = field(default=LOCAL_HOSTS)


class ChoiceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    choice: str = Field(min_length=1, max_length=64, pattern=_ID)


EvidenceId = Annotated[str, PathParam(min_length=1, max_length=64, pattern=_ID)]


class LabService:
    """The chain connection and the single mission session, behind one lock."""

    def __init__(self, manifest: ScenarioManifest, content: MissionContent, chain: AnvilChain,
                 node: dict[str, Any]) -> None:  # fmt: skip
        self.manifest = manifest
        self.content = content
        self.runner = ScenarioRunner(manifest, chain)
        self.node = node
        self.lock = threading.Lock()
        self.session: MissionSession | None = None

    def new_session(self) -> MissionSession:
        session = MissionSession(self.manifest, self.content, self.runner, self.node)
        session.start()
        self.session = session
        return session

    def current(self) -> MissionSession:
        if self.session is None:
            raise MissionError("no-session", "start the mission first", 404)
        return self.session


@dataclass
class _Runtime:
    service: LabService | None = None
    error: str | None = None
    process: AnvilProcess | None = None


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app(config: LabConfig | None = None, *, chain: AnvilChain | None = None) -> FastAPI:
    """Build the API. Pass ``chain`` to use an existing chain adapter (tests); otherwise
    a private Anvil node is started on a loopback port for the lifetime of the app."""
    config = config if config is not None else LabConfig()
    scenario_dir = config.scenarios_dir / config.scenario
    manifest = load_manifest(scenario_dir)
    content = load_mission(scenario_dir, manifest)
    runtime = _Runtime()
    ledger = RequestLedger()
    mutation_lock = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            if chain is not None:
                runtime.service = LabService(manifest, content, chain, {"client_version": chain.client_version()})
            else:
                url = config.rpc_url
                if url is None:
                    runtime.process = AnvilProcess(config.anvil_executable, chain_id=manifest.environment.chain_id)
                    url = runtime.process.start()
                adapter = AnvilChain(JsonRpcClient(url))
                runtime.service = LabService(manifest, content, adapter, {"client_version": adapter.require_anvil()})
        except GenesisError as failure:
            runtime.error = str(failure)
        yield
        if runtime.process is not None:
            runtime.process.stop()

    app = FastAPI(
        title="GENESIS Security Lab",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.middleware("http")
    async def request_consistency(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if not request.url.path.startswith("/api/session"):
            return await call_next(request)
        async with mutation_lock:
            if request.method != "POST":
                response = await call_next(request)
                response.headers["X-Lab-Version"] = ledger.version
                return response
            key = request.headers.get("Idempotency-Key")
            expected = request.headers.get("X-Lab-Version")
            if key is not None and (not key or len(key) > 128 or not key.isascii()):
                return _error(422, "invalid-key", "Idempotency-Key must be 1 to 128 ASCII characters")
            fingerprint = ledger.fingerprint(request.method, request.url.path, await request.body())
            if key is not None:
                cached = ledger.lookup(key, fingerprint)
                if cached is not None:
                    return cached
            if expected is not None and expected != ledger.version:
                response = _error(409, "stale-state", "The experiment changed. Refresh GET /api/session before acting.")
                response.headers["X-Lab-Version"] = ledger.version
                return response
            response = await call_next(request)
            # Even errors can follow a partially executed chain action. Never silently retry them.
            ledger.revision += 1
            iterator = getattr(response, "body_iterator", None)
            if iterator is not None:
                body = b"".join([chunk.encode() if isinstance(chunk, str) else chunk async for chunk in iterator])
            else:
                body = bytes(response.body)
            headers = dict(response.headers)
            headers["X-Lab-Version"] = ledger.version
            if key is not None:
                ledger.remember(key, fingerprint, body, response.status_code, headers)
            return Response(body, status_code=response.status_code, headers=headers)

    # Host validation must wrap retry receipts too, rather than being bypassed by a cache hit.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(config.allowed_hosts))

    def service() -> LabService:
        if runtime.service is None:
            raise MissionError(
                "chain-unavailable",
                f"the local chain is not available: {runtime.error or 'still starting'}. "
                "Install Foundry so that 'anvil' is on PATH, then restart the lab.",
                503,
            )
        return runtime.service

    def act(action: Callable[[LabService], Any]) -> Any:
        try:
            lab = service()
            with lab.lock:
                return action(lab)
        except MissionError as failure:
            return _error(failure.status, failure.code, str(failure))
        except GenesisError as failure:  # chain or environment failures
            return _error(502, "chain-error", str(failure))

    @app.get("/api/health")
    def health() -> Any:
        if runtime.service is None:
            return JSONResponse(status_code=503, content={"status": "unavailable", "error": runtime.error})
        return {"status": "ready", "chain": {"chain_id": manifest.environment.chain_id, **runtime.service.node}}

    @app.get("/api/mission")
    def mission() -> Any:
        return {
            "id": content.id,
            "title": content.title,
            "tagline": content.tagline,
            "estimated_minutes": content.estimated_minutes,
            "briefing": list(content.briefing),
            "objectives": list(content.objectives),
            "trust_boundary": {
                "title": content.trust_boundary.title,
                "summary": content.trust_boundary.summary,
                "disclaimer": content.trust_boundary.disclaimer,
                "steps": [
                    {"actor": step.actor, "trust": step.trust, "note": step.note}
                    for step in content.trust_boundary.steps
                ],
            },
            # Feedback, and therefore which strategy is safe, stays on the server until graded.
            "choices": [{"id": c.id, "label": c.label, "detail": c.detail} for c in content.choices],
            "hints_total": len(content.hints),
            "scenario": {
                "id": manifest.scenario.id,
                "version": manifest.scenario.version,
                "title": manifest.scenario.title,
                "manifest_digest": manifest.digest(),
                "variants": [{"id": v.id, "title": v.title} for v in manifest.variants],
            },
        }

    @app.post("/api/session")
    def start_session() -> Any:
        return act(lambda lab: lab.new_session().state())

    @app.get("/api/session")
    def session_state() -> Any:
        return act(lambda lab: lab.current().state())

    @app.post("/api/session/evidence/{evidence_id}")
    def inspect(evidence_id: EvidenceId) -> Any:
        return act(lambda lab: lab.current().inspect(evidence_id))

    @app.post("/api/session/hints")
    def hint() -> Any:
        return act(lambda lab: lab.current().hint())

    @app.post("/api/session/choice")
    def choose(body: ChoiceBody) -> Any:
        return act(lambda lab: lab.current().choose(body.choice))

    @app.post("/api/session/replay")
    def replay() -> Any:
        return act(lambda lab: lab.current().replay())

    @app.post("/api/session/reset")
    def reset() -> Any:
        return act(lambda lab: lab.current().reset())

    @app.get("/api/session/report")
    def report() -> Any:
        return act(lambda lab: lab.current().report())

    if config.static_dir is not None and (config.static_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=config.static_dir, html=True), name="ui")

    return app
