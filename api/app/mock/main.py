"""Graph 與 GitHub 的 mock 伺服器。只給本機示範與評測用，不要對外開放。

uvicorn app.mock.main:default_app --factory --port 8391

- Graph：  /login/{tenant}/oauth2/v2.0/token、/v1.0/...
- GitHub： /github/...
- 故障注入與重置：/_mock/...
"""

import os
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.mock import github, graph
from app.mock.state import Faults, Store

READER_ROLES = {"User.Read.All", "Group.Read.All", "GroupMember.Read.All", "AuditLog.Read.All",
                "RoleManagement.Read.Directory"}
# 寫入 App 也要 User.Read.All：官方文件寫明改 accountEnabled 最小權限是 User.EnableDisableAccount.All + User.Read.All
WRITER_ROLES = {"User.Read.All", "User.EnableDisableAccount.All", "User.RevokeSessions.All", "User.DeleteRestore.All",
                "GroupMember.ReadWrite.All", "RoleManagement.ReadWrite.Directory"}


def create_app(data_dir: Path, env: dict[str, str]) -> FastAPI:
    app = FastAPI(title="keyward mock (Graph + GitHub)", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = Store(data_dir)
    # 憑證一律從環境變數讀，沒設定就啟動失敗
    app.state.graph_clients = {
        env["MOCK_GRAPH_READER_ID"]: (env["MOCK_GRAPH_READER_SECRET"], READER_ROLES),
        env["MOCK_GRAPH_WRITER_ID"]: (env["MOCK_GRAPH_WRITER_SECRET"], WRITER_ROLES),
    }
    app.state.github_tokens = {"read": env["MOCK_GITHUB_READ_TOKEN"], "admin": env["MOCK_GITHUB_ADMIN_TOKEN"]}

    @app.middleware("http")
    async def throttle(request: Request, call_next):
        path = request.url.path
        if path.startswith("/_mock"):
            return await call_next(request)
        store: Store = app.state.store
        store.requests += 1
        f = store.faults
        if f.throttle_every and store.requests % f.throttle_every == 0:
            headers = {"Retry-After": str(f.retry_after)}
            if path.startswith("/github"):
                return JSONResponse({"message": "You have exceeded a secondary rate limit.",
                                     "documentation_url": github.DOCS}, 429, headers=headers)
            return JSONResponse(graph.error_body("TooManyRequests", "Too many requests."), 429, headers=headers)
        return await call_next(request)

    @app.exception_handler(graph.GraphError)
    async def graph_error(_: Request, exc: graph.GraphError):
        return JSONResponse(graph.error_body(exc.code, exc.message), exc.status, headers=exc.headers)

    @app.exception_handler(github.GitHubError)
    async def github_error(_: Request, exc: github.GitHubError):
        return JSONResponse({"message": exc.message, "documentation_url": github.DOCS}, exc.status, headers=exc.headers)

    @app.post("/_mock/reset")
    def reset():
        app.state.store.reset()
        app.state.store.faults = Faults()
        return {"ok": True}

    @app.put("/_mock/faults")
    async def set_faults(request: Request):
        app.state.store.faults = Faults(**(await request.json()))
        return asdict(app.state.store.faults)

    @app.get("/_mock/stats")
    def stats():
        s: Store = app.state.store
        return {"requests": s.requests, "writes": s.writes, "applied_writes": s.applied_writes, "version": s.version}

    @app.get("/health")
    def health():
        return {"ok": True}

    app.include_router(graph.router)
    app.include_router(github.router)
    return app


def default_app() -> FastAPI:
    data_dir = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parents[3] / "data")) / "synthetic"
    return create_app(data_dir, dict(os.environ))
