from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.account_bootstrap import BootstrapResult, SubprocessWechatURLLauncher, WechatURLLauncher, bootstrap_public_account
from app.credential_scanner import CaptureCandidate
from app.history_seed import locate_state_history_seeds
from app.live_transport import UrllibHistoryTransport, candidate_from_history_seed, history_seed_from_candidate
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

    def _attempt_candidates(
        self,
        candidates: list[CaptureCandidate],
        account_name: str,
        target_biz: str,
        limit: int,
    ) -> tuple[DiscoveryResult | None, bool, ProviderError | None]:
        saw_login_required = False
        last_retryable: ProviderError | None = None
        for candidate in candidates:
            try:
                seed = history_seed_from_candidate(candidate)
                transport = self._transport_factory(candidate)
                provider = AuthenticatedHistoryProvider(None, transport, seed=seed)
                result = provider.recent_articles(account_name, limit)
                if not result.articles or any(article.biz != target_biz for article in result.articles):
                    raise ProviderError("ACCOUNT_NOT_FOUND", "discovered_article_account_mismatch")
                return result, saw_login_required, last_retryable
            except ProviderError as exc:
                if exc.code == "PAGINATION_INCOMPLETE":
                    raise
                if exc.code in {"LOGIN_REQUIRED", "HISTORY_SURFACE_UNAVAILABLE", "ACCOUNT_NOT_FOUND"}:
                    saw_login_required = saw_login_required or exc.code == "LOGIN_REQUIRED"
                    last_retryable = exc
                    continue
                raise
        return None, saw_login_required, last_retryable

    def recent_articles(self, account_name: str, biz: str, limit: int) -> DiscoveryResult:
        normalized_account = account_name.strip()
        normalized_biz = biz.strip()
        if not normalized_account:
            raise ValueError("account_name_required")
        if not normalized_biz or len(normalized_biz) > 256 or any(char.isspace() for char in normalized_biz):
            raise ValueError("invalid_target_biz")
        if not 1 <= limit <= 100:
            raise ValueError("limit_out_of_range")

        history_candidates: list[CaptureCandidate] = []
        for seed in locate_state_history_seeds(self.state_dir, normalized_biz):
            try:
                history_candidates.append(candidate_from_history_seed(seed))
            except ProviderError:
                continue

        result, saw_login_required, last_retryable = self._attempt_candidates(
            history_candidates,
            normalized_account,
            normalized_biz,
            limit,
        )
        if result is not None:
            return result

        bootstrap = self._bootstrapper(normalized_biz)
        bootstrap_candidates = (
            self._valid_candidates(bootstrap.candidates, normalized_biz)
            if bootstrap.credential_observed and bootstrap.candidates
            else []
        )
        refreshed, refresh_login_required, refresh_error = self._attempt_candidates(
            bootstrap_candidates,
            normalized_account,
            normalized_biz,
            limit,
        )
        if refreshed is not None:
            return refreshed

        saw_login_required = saw_login_required or refresh_login_required
        last_retryable = refresh_error or last_retryable
        if saw_login_required:
            raise ProviderError("LOGIN_REQUIRED", "all_credential_candidates_stale")
        if last_retryable is not None:
            raise ProviderError(last_retryable.code, "all_credential_candidates_failed")
        raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "credential_candidate_not_observed")
