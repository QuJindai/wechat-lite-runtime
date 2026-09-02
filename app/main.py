from __future__ import annotations

import secrets
from collections.abc import Callable

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.account_bootstrap import BootstrapResult, SubprocessWechatURLLauncher, bootstrap_public_account
from app.config import Settings
from app.history_seed import probe_history_seed_status
from app.launcher_bridge import HttpWechatURLLauncher
from app.live_discovery import LiveDiscoveryService
from app.providers import ProviderError, PublicAccountProvider
from app.public_accounts import redact_sensitive_text
from app.runtime import build_codespace_port_url, probe_tcp, summarize_state_dir
from app.wechat_probe import probe_state
from app.webview_probe import probe_webview_state

TcpProbe = Callable[[str, int, float], bool]
AccountBootstrapper = Callable[[str], BootstrapResult]


class BootstrapRequest(BaseModel):
    biz: str


class DiscoverRequest(BaseModel):
    account_name: str = Field(min_length=1, max_length=256)
    biz: str = Field(min_length=1, max_length=256)
    limit: int = Field(default=20, ge=1, le=100)


def create_app(
    settings: Settings,
    tcp_probe: TcpProbe = probe_tcp,
    public_account_provider: PublicAccountProvider | None = None,
    account_bootstrapper: AccountBootstrapper | None = None,
    live_discovery_service: LiveDiscoveryService | None = None,
) -> FastAPI:
    application = FastAPI(title="WeChat Lite Runtime", version="0.7.0")
    bearer = HTTPBearer(auto_error=False)

    bridge_launcher = (
        HttpWechatURLLauncher(settings.control_token)
        if settings.control_token
        else SubprocessWechatURLLauncher()
    )

    if account_bootstrapper is None:
        def configured_bootstrapper(biz: str) -> BootstrapResult:
            return bootstrap_public_account(
                biz,
                state_dir=settings.state_dir,
                launcher=bridge_launcher,
            )

        active_bootstrapper: AccountBootstrapper = configured_bootstrapper
    else:
        active_bootstrapper = account_bootstrapper

    active_live_discovery = live_discovery_service or LiveDiscoveryService(
        settings.state_dir,
        launcher=bridge_launcher,
    )

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

    def raise_provider_http_error(exc: ProviderError) -> None:
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

    @application.get("/v1/wechat/history-seed-status", dependencies=[Depends(require_control_token)])
    def wechat_history_seed_status() -> dict[str, object]:
        return probe_history_seed_status(settings.state_dir)

    @application.post("/v1/public-accounts/bootstrap", dependencies=[Depends(require_control_token)])
    def public_account_bootstrap(request: BootstrapRequest) -> dict[str, object]:
        try:
            result = active_bootstrapper(request.biz)
        except ValueError as exc:
            if str(exc) == "invalid_target_biz":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"code": "INVALID_BIZ"},
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_BOOTSTRAP_REQUEST"},
            ) from exc
        return result.safe_summary()

    @application.post("/v1/public-accounts/discover", dependencies=[Depends(require_control_token)])
    def public_account_discover(request: DiscoverRequest) -> dict[str, object]:
        try:
            result = active_live_discovery.recent_articles(
                request.account_name,
                request.biz,
                request.limit,
            )
        except ProviderError as exc:
            raise_provider_http_error(exc)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_DISCOVERY_REQUEST"},
            ) from exc
        return result.to_dict()

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
            raise_provider_http_error(exc)
        return result.to_dict()

    return application


app = create_app(Settings.from_env())
