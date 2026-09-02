import io
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest

from app.credential_scanner import CaptureCandidate
from app.live_transport import UrllibHistoryTransport, history_seed_from_candidate
from app.providers import HistoryPageResponse, ProviderError


def candidate() -> CaptureCandidate:
    return CaptureCandidate(
        request_url=(
            "https://mp.weixin.qq.com/mp/profile_ext?action=getmsg&__biz=BIZ_PUBLIC"
            "&uin=UIN_SECRET&key=KEY_SECRET&pass_ticket=PASS_SECRET"
            "&appmsg_token=TOKEN_SECRET&poc_sid=SID_SECRET&poc_token=POC_SECRET&offset=0"
        ),
        fields={
            "biz": "BIZ_PUBLIC",
            "uin": "UIN_SECRET",
            "key": "KEY_SECRET",
            "pass_ticket": "PASS_SECRET",
            "appmsg_token": "TOKEN_SECRET",
            "poc_sid": "SID_SECRET",
            "poc_token": "POC_SECRET",
        },
        modified_at=123.0,
        source_root=".xwechat/radium/web",
    )


class FakeResponse:
    def __init__(self, body: bytes, url: str, status: int = 200) -> None:
        self.body = body
        self.url = url
        self.status = status
        self.closed = False

    def read(self, amount: int = -1) -> bytes:
        return self.body if amount < 0 else self.body[:amount]

    def geturl(self) -> str:
        return self.url

    def close(self) -> None:
        self.closed = True


def test_candidate_becomes_private_history_seed_without_safe_serialization_leak():
    seed = history_seed_from_candidate(candidate())
    query = parse_qs(urlsplit(seed._raw_url).query)
    assert query["__biz"] == ["BIZ_PUBLIC"]
    assert query["key"] == ["KEY_SECRET"]
    rendered = repr(seed) + repr(seed.safe_summary())
    for secret in ["BIZ_PUBLIC", "UIN_SECRET", "KEY_SECRET", "PASS_SECRET", "TOKEN_SECRET", "SID_SECRET", "POC_SECRET"]:
        assert secret not in rendered


def test_transport_sends_only_same_origin_candidate_context_and_returns_bytes():
    seen = []

    def opener(request, timeout):
        seen.append((request, timeout))
        return FakeResponse(b'{"ret":0}', request.full_url)

    transport = UrllibHistoryTransport(candidate(), opener=opener, timeout_seconds=4.0)
    url = history_seed_from_candidate(candidate())._raw_url.replace("offset=0", "offset=10")
    response = transport.get(url)

    assert isinstance(response, HistoryPageResponse)
    assert response.payload == b'{"ret":0}'
    assert response.live_observation is True
    assert len(seen) == 1
    request, timeout = seen[0]
    assert timeout == 4.0
    parsed = urlsplit(request.full_url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.hostname == "mp.weixin.qq.com"
    assert parsed.path == "/mp/profile_ext"
    assert query["__biz"] == ["BIZ_PUBLIC"]
    assert query["key"] == ["KEY_SECRET"]
    assert request.headers.get("Authorization") is None
    assert request.headers.get("Cookie") is None
    rendered = repr(transport)
    for secret in ["BIZ_PUBLIC", "KEY_SECRET", "PASS_SECRET", "TOKEN_SECRET"]:
        assert secret not in rendered


def test_transport_rejects_host_escape_before_opener_is_called():
    calls = []
    transport = UrllibHistoryTransport(candidate(), opener=lambda request, timeout: calls.append(request))
    with pytest.raises(ProviderError) as exc:
        transport.get("https://evil.example/mp/profile_ext?action=getmsg&__biz=BIZ_PUBLIC&key=KEY_SECRET")
    assert exc.value.code == "HISTORY_SURFACE_UNAVAILABLE"
    assert calls == []


def test_transport_rejects_candidate_auth_context_mismatch_before_network():
    calls = []
    transport = UrllibHistoryTransport(candidate(), opener=lambda request, timeout: calls.append(request))
    bad = history_seed_from_candidate(candidate())._raw_url.replace("KEY_SECRET", "OTHER_SECRET")
    with pytest.raises(ProviderError) as exc:
        transport.get(bad)
    assert exc.value.code == "HISTORY_SURFACE_UNAVAILABLE"
    assert calls == []
    assert "OTHER_SECRET" not in str(exc.value)


def test_transport_maps_http_auth_failure_without_echoing_private_url():
    def opener(request, timeout):
        raise HTTPError(request.full_url, 403, "Forbidden KEY_SECRET", {}, io.BytesIO(b"PRIVATE_BODY"))

    transport = UrllibHistoryTransport(candidate(), opener=opener)
    with pytest.raises(ProviderError) as exc:
        transport.get(history_seed_from_candidate(candidate())._raw_url)
    assert exc.value.code == "LOGIN_REQUIRED"
    rendered = str(exc.value) + repr(exc.value)
    for secret in ["KEY_SECRET", "PASS_SECRET", "PRIVATE_BODY"]:
        assert secret not in rendered


def test_transport_rejects_cross_origin_final_url_and_oversized_payload():
    target = history_seed_from_candidate(candidate())._raw_url
    redirect_transport = UrllibHistoryTransport(
        candidate(),
        opener=lambda request, timeout: FakeResponse(b"x", "https://evil.example/leak"),
    )
    with pytest.raises(ProviderError) as exc:
        redirect_transport.get(target)
    assert exc.value.code == "HISTORY_SURFACE_UNAVAILABLE"

    large_transport = UrllibHistoryTransport(
        candidate(),
        opener=lambda request, timeout: FakeResponse(b"123456789", request.full_url),
        max_response_bytes=8,
    )
    with pytest.raises(ProviderError) as exc2:
        large_transport.get(target)
    assert exc2.value.code == "HISTORY_SURFACE_UNAVAILABLE"
