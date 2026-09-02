from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.account_bootstrap import BootstrapResult, SubprocessWechatURLLauncher, WechatURLLauncher, bootstrap_public_account
from app.credential_scanner import CaptureCandidate
from app.live_transport import UrllibHistoryTransport, history_seed_from_candidate
from app.providers import AuthenticatedHistoryProvider, HistoryTransport, ProviderError
from app.public_accounts import DiscoveryResult

Bootstrapper = Callable[[str], BootstrapResult]
TransportFactory = Callable[[CaptureCandidate], HistoryTransport]


class LiveDiscoveryService:
    def __init__(
        self,
        state_dir: Path,
        *,
        bootstrapper: Bootstrapper | None = None,
        transport_factory: TransportFactory | None = None,
        launcher: WechatURLLauncher | None = None,
    ) -> None:
        self.state_dir = Path(state_dir)
        if bootstrapper is None:
            active_launcher = launcher or SubprocessWechatURLLauncher()

            def configured_bootstrapper(biz: str) -> BootstrapResult:
                return bootstrap_public_account(
                    biz,
                    state_dir=self.state_dir,
                    launcher=active_launcher,
                )

            self._bootstrapper = configured_bootstrapper
        else:
            self._bootstrapper = bootstrapper
        self._transport_factory = transport_factory or (lambda candidate: UrllibHistoryTransport(candidate))

    def __repr__(self) -> str:
        return "LiveDiscoveryService(state_dir='<private>')"

    @staticmethod
    def _valid_candidates(candidates: list[CaptureCandidate], target_biz: str) -> list[CaptureCandidate]:
        valid: list[CaptureCandidate] = []
        matching = [candidate for candidate in candidates if candidate.fields.get("biz") == target_biz]
        for candidate in sorted(matching, key=lambda item: item.modified_at, reverse=True):
            try:
                history_seed_from_candidate(candidate)
            except ProviderError:
                continue
            valid.append(candidate)
        return valid

    @classmethod
    def _select_candidate(cls, candidates: list[CaptureCandidate], target_biz: str) -> CaptureCandidate:
        valid = cls._valid_candidates(candidates, target_biz)
        if valid:
            return valid[0]
        raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "matching_credential_candidate_not_observed")

    def recent_articles(self, account_name: str, biz: str, limit: int) -> DiscoveryResult:
        normalized_account = account_name.strip()
        normalized_biz = biz.strip()
        if not normalized_account:
            raise ValueError("account_name_required")
        if not normalized_biz or len(normalized_biz) > 256 or any(char.isspace() for char in normalized_biz):
            raise ValueError("invalid_target_biz")
        if not 1 <= limit <= 100:
            raise ValueError("limit_out_of_range")

        bootstrap = self._bootstrapper(normalized_biz)
        if not bootstrap.credential_observed or not bootstrap.candidates:
            raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "credential_candidate_not_observed")

        candidates = self._valid_candidates(bootstrap.candidates, normalized_biz)
        if not candidates:
            raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "matching_credential_candidate_not_observed")

        saw_login_required = False
        last_retryable: ProviderError | None = None
        for candidate in candidates:
            try:
                seed = history_seed_from_candidate(candidate)
                transport = self._transport_factory(candidate)
                provider = AuthenticatedHistoryProvider(None, transport, seed=seed)
                result = provider.recent_articles(normalized_account, limit)
                if not result.articles or any(article.biz != normalized_biz for article in result.articles):
                    raise ProviderError("ACCOUNT_NOT_FOUND", "discovered_article_account_mismatch")
                return result
            except ProviderError as exc:
                if exc.code == "PAGINATION_INCOMPLETE":
                    raise
                if exc.code in {"LOGIN_REQUIRED", "HISTORY_SURFACE_UNAVAILABLE", "ACCOUNT_NOT_FOUND"}:
                    saw_login_required = saw_login_required or exc.code == "LOGIN_REQUIRED"
                    last_retryable = exc
                    continue
                raise

        if saw_login_required:
            raise ProviderError("LOGIN_REQUIRED", "all_credential_candidates_stale")
        if last_retryable is not None:
            raise ProviderError(last_retryable.code, "all_credential_candidates_failed")
        raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "credential_candidate_not_observed")
