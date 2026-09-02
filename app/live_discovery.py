from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Protocol

from app.account_bootstrap import BootstrapResult, SubprocessWechatURLLauncher, WechatURLLauncher, bootstrap_public_account
from app.account_index import PublicAccountIndex
from app.credential_scanner import CaptureCandidate, ScanReport, scan_credentials
from app.history_seed import locate_state_history_seeds
from app.launcher_bridge import SearchEvidence
from app.live_transport import UrllibHistoryTransport, candidate_from_history_seed, history_seed_from_candidate
from app.providers import AuthenticatedHistoryProvider, HistoryTransport, ProviderError
from app.public_accounts import DiscoveryResult

Bootstrapper = Callable[[str], BootstrapResult]
TransportFactory = Callable[[CaptureCandidate], HistoryTransport]
ScanFn = Callable[..., ScanReport]


class PublicAccountNavigator(Protocol):
    def search_public_account(self, account_name: str) -> SearchEvidence: ...


class LiveDiscoveryService:
    def __init__(
        self,
        state_dir: Path,
        *,
        bootstrapper: Bootstrapper | None = None,
        transport_factory: TransportFactory | None = None,
        launcher: WechatURLLauncher | None = None,
        ui_navigator: PublicAccountNavigator | None = None,
        scan_fn: ScanFn = scan_credentials,
        ui_timeout_seconds: float = 5.0,
        ui_poll_seconds: float = 0.5,
        account_index: PublicAccountIndex | None = None,
    ) -> None:
        if ui_timeout_seconds <= 0:
            raise ValueError("ui_timeout_seconds_out_of_range")
        if ui_poll_seconds < 0:
            raise ValueError("ui_poll_seconds_out_of_range")
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
        self._ui_navigator = ui_navigator
        self._scan_fn = scan_fn
        self.ui_timeout_seconds = float(ui_timeout_seconds)
        self.ui_poll_seconds = float(ui_poll_seconds)
        self._account_index = account_index or PublicAccountIndex(self.state_dir)

    def __repr__(self) -> str:
        return "LiveDiscoveryService(state_dir='<private>')"

    @staticmethod
    def _candidate_fingerprint(candidate: CaptureCandidate) -> str:
        return str(candidate.safe_summary()["candidate_fingerprint"])

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

    def _scan(
        self,
        target_biz: str | None,
        *,
        max_scan_seconds: float | None = None,
    ) -> ScanReport:
        web_root = self.state_dir / ".xwechat" / "radium" / "web"
        return self._scan_fn(
            target_biz,
            roots=[web_root],
            since_minutes=60,
            max_files=5000,
            max_total_bytes=512 * 1024 * 1024,
            max_directories=20_000,
            max_scan_seconds=max_scan_seconds or min(3.0, self.ui_timeout_seconds),
        )

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

    def _ui_search_candidates(self, account_name: str, target_biz: str) -> list[CaptureCandidate]:
        if self._ui_navigator is None:
            return []
        try:
            evidence = self._ui_navigator.search_public_account(account_name)
        except (ValueError, OSError):
            return []
        if not evidence.dispatch_attempted or not evidence.search_submitted:
            return []

        deadline = time.monotonic() + self.ui_timeout_seconds
        while True:
            report = self._scan(target_biz)
            candidates = self._valid_candidates(report.candidates, target_biz)
            if candidates:
                return candidates
            if time.monotonic() >= deadline:
                return []
            if self.ui_poll_seconds:
                time.sleep(min(self.ui_poll_seconds, max(0.0, deadline - time.monotonic())))

    def _resolve_biz_by_ui_delta(self, account_name: str) -> tuple[str, list[CaptureCandidate]]:
        if self._ui_navigator is None:
            raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "ui_navigator_unavailable")

        baseline = self._scan(None)
        baseline_fingerprints = {
            self._candidate_fingerprint(candidate)
            for candidate in baseline.candidates
        }

        try:
            evidence = self._ui_navigator.search_public_account(account_name)
        except (ValueError, OSError) as exc:
            raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "ui_search_dispatch_failed") from exc
        if not evidence.dispatch_attempted or not evidence.search_submitted:
            raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "ui_search_dispatch_failed")

        deadline = time.monotonic() + self.ui_timeout_seconds
        while True:
            report = self._scan(None)
            newly_observed: list[CaptureCandidate] = []
            for candidate in report.candidates:
                try:
                    history_seed_from_candidate(candidate)
                except ProviderError:
                    continue
                fingerprint = self._candidate_fingerprint(candidate)
                if fingerprint not in baseline_fingerprints:
                    newly_observed.append(candidate)

            grouped: dict[str, list[CaptureCandidate]] = {}
            for candidate in newly_observed:
                candidate_biz = candidate.fields.get("biz", "")
                if candidate_biz:
                    grouped.setdefault(candidate_biz, []).append(candidate)

            if len(grouped) == 1:
                resolved_biz = next(iter(grouped))
                return resolved_biz, self._valid_candidates(grouped[resolved_biz], resolved_biz)
            if len(grouped) > 1:
                raise ProviderError("ACCOUNT_IDENTITY_AMBIGUOUS", "multiple_new_account_identities")
            if time.monotonic() >= deadline:
                raise ProviderError("ACCOUNT_NOT_FOUND", "account_identity_not_observed")
            if self.ui_poll_seconds:
                time.sleep(min(self.ui_poll_seconds, max(0.0, deadline - time.monotonic())))

    def _recent_known_biz(self, account_name: str, target_biz: str, limit: int) -> DiscoveryResult:
        history_candidates: list[CaptureCandidate] = []
        for seed in locate_state_history_seeds(self.state_dir, target_biz):
            try:
                history_candidates.append(candidate_from_history_seed(seed))
            except ProviderError:
                continue

        result, saw_login_required, last_retryable = self._attempt_candidates(
            history_candidates,
            account_name,
            target_biz,
            limit,
        )
        if result is not None:
            return result

        bootstrap = self._bootstrapper(target_biz)
        bootstrap_candidates = (
            self._valid_candidates(bootstrap.candidates, target_biz)
            if bootstrap.credential_observed and bootstrap.candidates
            else []
        )
        refreshed, refresh_login_required, refresh_error = self._attempt_candidates(
            bootstrap_candidates,
            account_name,
            target_biz,
            limit,
        )
        if refreshed is not None:
            return refreshed
        saw_login_required = saw_login_required or refresh_login_required
        last_retryable = refresh_error or last_retryable

        ui_candidates = self._ui_search_candidates(account_name, target_biz)
        ui_result, ui_login_required, ui_error = self._attempt_candidates(
            ui_candidates,
            account_name,
            target_biz,
            limit,
        )
        if ui_result is not None:
            return ui_result
        saw_login_required = saw_login_required or ui_login_required
        last_retryable = ui_error or last_retryable

        if saw_login_required:
            raise ProviderError("LOGIN_REQUIRED", "all_credential_candidates_stale")
        if last_retryable is not None:
            raise ProviderError(last_retryable.code, "all_credential_candidates_failed")
        raise ProviderError("HISTORY_SURFACE_UNAVAILABLE", "credential_candidate_not_observed")

    def _remember(self, account_name: str, biz: str) -> None:
        try:
            self._account_index.remember(account_name, biz)
        except (OSError, ValueError):
            pass

    def recent_articles(self, account_name: str, biz: str | None, limit: int) -> DiscoveryResult:
        normalized_account = account_name.strip()
        if not normalized_account:
            raise ValueError("account_name_required")
        if not 1 <= limit <= 100:
            raise ValueError("limit_out_of_range")

        if biz is None:
            indexed_biz = self._account_index.resolve(normalized_account)
            if indexed_biz:
                try:
                    indexed_result = self._recent_known_biz(normalized_account, indexed_biz, limit)
                except ProviderError as exc:
                    if exc.code == "PAGINATION_INCOMPLETE":
                        raise
                else:
                    self._remember(normalized_account, indexed_biz)
                    return indexed_result

            resolved_biz, candidates = self._resolve_biz_by_ui_delta(normalized_account)
            resolved, _saw_login_required, _last_retryable = self._attempt_candidates(
                candidates,
                normalized_account,
                resolved_biz,
                limit,
            )
            if resolved is not None:
                self._remember(normalized_account, resolved_biz)
                return resolved
            fallback = self._recent_known_biz(normalized_account, resolved_biz, limit)
            self._remember(normalized_account, resolved_biz)
            return fallback

        normalized_biz = biz.strip()
        if not normalized_biz or len(normalized_biz) > 256 or any(char.isspace() for char in normalized_biz):
            raise ValueError("invalid_target_biz")
        result = self._recent_known_biz(normalized_account, normalized_biz, limit)
        self._remember(normalized_account, normalized_biz)
        return result
