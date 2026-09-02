from __future__ import annotations

import secrets
from collections.abc import Callable

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings
from app.runtime import build_codespace_port_url, probe_tcp, summarize_state_dir

TcpProbe = Callable[[str, int, float], bool]


def create_app(settings: Settings, tcp_probe: TcpProbe = probe_tcp) -> FastAPI:
    application = FastAPI(title="WeChat Lite Runtime", version="0.1.0")
    bearer = HTTPBearer(auto_error=False)

    def require_control_token(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    ) -> None:
        if not settings.control_token:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="control_token_not_configured",
            )
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
        if not secrets.compare_digest(credentials.credentials, settings.control_token):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    @application.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/v1/runtime/status", dependencies=[Depends(require_control_token)])
    def runtime_status() -> dict[str, object]:
        return {
            "codespace_name": settings.codespace_name,
            "wechat_web_ready": tcp_probe(
                settings.wechat_host,
                settings.wechat_port,
                settings.probe_timeout,
            ),
            "ui_url": build_codespace_port_url(settings.codespace_name, settings.wechat_port),
            "session_storage": summarize_state_dir(settings.state_dir),
        }

    @application.get("/v1/runtime/ui", dependencies=[Depends(require_control_token)])
    def runtime_ui() -> dict[str, str | None]:
        return {
            "ui_url": build_codespace_port_url(settings.codespace_name, settings.wechat_port),
        }

    return application


app = create_app(Settings.from_env())
