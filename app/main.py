from __future__ import annotations

import secrets
from collections.abc import Callable

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings
from app.providers import ProviderError, PublicAccountProvider
from app.public_accounts import redact_sensitive_text
from app.runtime import build_codespace_port_url, probe_tcp, summarize_state_dir
from app.wechat_probe import probe_state
from app.webview_probe import probe_webview_state

TcpProbe = Callable[[str, int, float], bool]


def create_app(
    settings: Settings,
    tcp_probe: TcpProbe = probe_tcp,
    public_account_provider: PublicAccountProvider | None = None,
) -> FastAPI:
    application = FastAPI(title="WeChat Lite Runtime", version="0.3.0")
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

    @application.get("/v1/wechat/probe", dependencies=[Depends(require_control_token)])
    def wechat_probe() -> dict[str, object]:
        return probe_state(settings.state_dir)

    @application.get("/v1/wechat/webview-probe", dependencies=[Depends(require_control_token)])
    def wechat_webview_probe() -> dict[str, object]:
        return probe_webview_state(settings.state_dir)

    @application.get(
        "/v1/public-accounts/{account}/recent",
        dependencies=[Depends(require_control_token)],
    )
    def public_account_recent(
        account: str,
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, object]:
        if public_account_provider is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "HISTORY_SURFACE_UNAVAILABLE",
                    "message": "public_account_provider_not_configured",
                },
            )
        try:
            result = public_account_provider.recent_articles(account, limit)
        except ProviderError as exc:
            error_status = {
                "LOGIN_REQUIRED": status.HTTP_409_CONFLICT,
                "ACCOUNT_NOT_FOUND": status.HTTP_404_NOT_FOUND,
                "HISTORY_SURFACE_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
                "PAGINATION_INCOMPLETE": status.HTTP_502_BAD_GATEWAY,
            }.get(exc.code, status.HTTP_502_BAD_GATEWAY)
            raise HTTPException(
                status_code=error_status,
                detail={
                    "code": exc.code,
                    "message": redact_sensitive_text(str(exc)),
                },
            ) from exc
        return result.to_dict()

    return application


app = create_app(Settings.from_env())
