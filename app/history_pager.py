from __future__ import annotations

import html
import json
from datetime import datetime
from urllib.parse import parse_qsl, parse_qs, urlencode, urlsplit, urlunsplit

from app.history_seed import HistorySeed
from app.public_accounts import ArticleRecord, CHINA_TZ, normalize_article

_CONTROL_KEYS = {"action", "offset", "count", "f", "is_ok", "scene"}


class ProfileExtAuthError(ValueError):
    pass


class ProfileExtResponseError(ValueError):
    pass


def _validate_seed(seed: HistorySeed) -> None:
    parsed = urlsplit(seed._raw_url)
    if parsed.scheme != "https" or parsed.hostname != "mp.weixin.qq.com" or parsed.path != "/mp/profile_ext":
        raise ValueError("invalid_history_seed")


def build_page_url(seed: HistorySeed, offset: int, count: int = 10) -> str:
    _validate_seed(seed)
    if offset < 0:
        raise ValueError("offset_must_be_non_negative")
    if count < 1 or count > 10:
        raise ValueError("count_out_of_range")

    parsed = urlsplit(seed._raw_url)
    pairs = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key not in _CONTROL_KEYS]
    pairs.extend(
        [
            ("action", "getmsg"),
            ("f", "json"),
            ("offset", str(offset)),
            ("count", str(count)),
            ("is_ok", "1"),
            ("scene", "124"),
        ]
    )
    return urlunsplit(("https", "mp.weixin.qq.com", "/mp/profile_ext", urlencode(pairs), ""))


def _decode_general_msg_list(value: object) -> dict[str, object]:
    try:
        if isinstance(value, str):
            decoded = json.loads(value)
        elif isinstance(value, dict):
            decoded = value
        else:
            raise ValueError
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError("invalid_general_msg_list") from exc
    if not isinstance(decoded, dict):
        raise ValueError("invalid_general_msg_list")
    return decoded


def _truthy_flag(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "none"}
    return bool(value)


def _article_raw(
    item: dict[str, object],
    *,
    account_name: str,
    published_at: object,
    observed_at: datetime,
) -> dict[str, object] | None:
    title = str(item.get("title") or "").strip()
    raw_url = str(item.get("content_url") or item.get("url") or "").strip()
    if not title or not raw_url:
        return None
    url = html.unescape(raw_url)
    if url.startswith("/"):
        url = "https://mp.weixin.qq.com" + url
    query = parse_qs(urlsplit(url).query, keep_blank_values=True)
    biz = query.get("__biz", [None])[0]
    return {
        "account_name": account_name,
        "biz": biz,
        "title": title,
        "url": url,
        "published_at": published_at,
        "observed_at": observed_at,
        "source": "authenticated_wechat",
        "verified_account": True,
    }


def _validate_profile_ext_ret(outer: dict[str, object]) -> None:
    raw_ret = outer.get("ret", 0)
    try:
        ret = int(raw_ret)
    except (TypeError, ValueError) as exc:
        raise ProfileExtResponseError("profile_ext_invalid_ret") from exc
    if ret == 0:
        return
    if ret == -3:
        raise ProfileExtAuthError("profile_ext_login_required")
    raise ProfileExtResponseError("profile_ext_request_rejected")


def parse_profile_ext_page(payload: bytes, account_name: str) -> tuple[list[ArticleRecord], bool]:
    try:
        outer = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_profile_ext_payload") from exc
    if not isinstance(outer, dict):
        raise ValueError("invalid_profile_ext_payload")

    _validate_profile_ext_ret(outer)
    general = _decode_general_msg_list(outer.get("general_msg_list"))
    entries = general.get("list") or []
    if not isinstance(entries, list):
        raise ValueError("invalid_general_msg_list")

    observed_at = datetime.now(tz=CHINA_TZ)
    records: list[ArticleRecord] = []
    position = 1
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        comm = entry.get("comm_msg_info") or {}
        ext = entry.get("app_msg_ext_info") or {}
        if not isinstance(comm, dict) or not isinstance(ext, dict):
            continue
        published_at = comm.get("datetime")

        main_raw = _article_raw(
            ext,
            account_name=account_name,
            published_at=published_at,
            observed_at=observed_at,
        )
        if main_raw is not None:
            records.append(normalize_article(main_raw, position))
            position += 1

        multi = ext.get("multi_app_msg_item_list") or []
        if isinstance(multi, list):
            for child in multi:
                if not isinstance(child, dict):
                    continue
                child_raw = _article_raw(
                    child,
                    account_name=account_name,
                    published_at=child.get("datetime") or published_at,
                    observed_at=observed_at,
                )
                if child_raw is None:
                    continue
                records.append(normalize_article(child_raw, position))
                position += 1

    return records, _truthy_flag(outer.get("can_msg_continue"))
