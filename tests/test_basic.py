# pyright: reportPrivateUsage=false
"""Smoke tests for the ingestion engine (SQLite per-test temp file)."""

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update

DESKTOP_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    # Isolate each test to a temp SQLite file (shared in-memory DBs don't survive pools).
    from collector.config import get_settings

    get_settings.cache_clear()
    import os

    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    from collector import database

    await database.close_db()
    await database.init_db()

    from collector.main import _limiter, app

    _limiter.reset()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await database.close_db()
    get_settings.cache_clear()


async def test_pixel_returns_svg_with_no_store(client: AsyncClient) -> None:
    r = await client.get("/pixel/my-doc.svg")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert r.headers["Cache-Control"] == "no-store, no-cache, must-revalidate, max-age=0"
    assert r.headers["Pragma"] == "no-cache"
    assert "<svg" in r.text


async def test_pixel_rejects_bad_key(client: AsyncClient) -> None:
    r = await client.get("/pixel/..%2Fetc.svg")
    assert r.status_code in (400, 404)


async def test_heartbeat_accepts_buckets(client: AsyncClient) -> None:
    for t in (15, 30, 60, 120):
        r = await client.post("/heartbeat/my-doc", json={"t": t})
        assert r.status_code == 200, r.text
        assert r.json()["t"] == t


async def test_heartbeat_rejects_bad_bucket(client: AsyncClient) -> None:
    r = await client.post("/heartbeat/my-doc", json={"t": 999})
    assert r.status_code == 422


async def test_embed_has_csp_and_beacon(client: AsyncClient) -> None:
    from collector.config import DEFAULT_EMBED_ORIGINS

    r = await client.get("/embed/my-doc")
    assert r.status_code == 200
    # Ends-with the full allow-list - substring checks can pass on lookalike origins.
    csp = r.headers["Content-Security-Policy"]
    assert csp.endswith("frame-ancestors " + " ".join(DEFAULT_EMBED_ORIGINS) + ";")
    assert "sendBeacon" in r.text
    assert "views" in r.text


async def test_stats_aggregates(client: AsyncClient) -> None:
    from datetime import UTC, datetime

    await client.get("/pixel/readme.svg")
    await client.post("/heartbeat/readme", json={"t": 15})
    data = await _wait_for_views(client, "readme")
    assert data["views"] >= 1
    assert data["dwell"].get("15", 0) >= 1
    # Daily time-series: all test events land "today" (UTC).
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    assert data["daily"][today]["views"] >= 1
    assert data["daily"][today]["uniques"] >= 1
    assert data["daily"][today]["heartbeats"].get("15", 0) >= 1


def test_salt_hash_is_stable_within_epoch() -> None:
    from collector import salt

    s = salt.current_salt()
    assert salt.hash_ip("1.2.3.4", s) == salt.hash_ip("1.2.3.4", s)
    assert salt.hash_ip("1.2.3.4", s) != salt.hash_ip("5.6.7.8", s)


def test_geo_unknown_on_private_ip() -> None:
    from collector.geo import GeoLookup

    g = GeoLookup("/nonexistent/GeoLite2-Country.mmdb")
    assert g.country("127.0.0.1") == "XX"
    assert g.country("not-an-ip") == "XX"


async def _wait_for_views(client: AsyncClient, doc_key: str, minimum: int = 1) -> dict[str, Any]:
    """Pixel ingestion runs as a background task - poll until it lands."""
    data: dict[str, Any] = {}
    for _ in range(20):
        r = await client.get(f"/stats/{doc_key}")
        assert r.status_code == 200
        data = r.json()
        if data["views"] >= minimum:
            break
        await asyncio.sleep(0.1)
    return data


async def test_referrer_stored_origin_only(client: AsyncClient) -> None:
    await client.get(
        "/pixel/ref-test.svg",
        headers={"referer": "https://mail.example.com/read?token=SECRET123&user=bob"},
    )
    data = await _wait_for_views(client, "ref-test")
    refs = [r["referrer"] for r in data["referrers"]]
    assert refs == ["https://mail.example.com"]
    assert "SECRET123" not in str(data)


async def test_referrer_strips_userinfo(client: AsyncClient) -> None:
    await client.get(
        "/pixel/creds.svg",
        headers={"referer": "https://user:s3cret@mail.example.com/inbox"},
    )
    data = await _wait_for_views(client, "creds")
    refs = [r["referrer"] for r in data["referrers"]]
    assert refs == ["https://mail.example.com"]
    assert "s3cret" not in str(data)


async def test_ref_param_accepts_approved_tag(client: AsyncClient) -> None:
    await client.get("/pixel/tag-test.svg?ref=substack")
    data = await _wait_for_views(client, "tag-test")
    refs = [r["referrer"] for r in data["referrers"]]
    assert refs == ["substack"]


async def test_ref_param_rejects_injection(client: AsyncClient) -> None:
    await client.get("/pixel/bad-ref.svg", params={"ref": "<script>alert(1)</script>"})
    data = await _wait_for_views(client, "bad-ref")
    assert data["referrers"] == []  # not a tag, not a URL → dropped


async def test_stats_device_breakdown(client: AsyncClient) -> None:
    # One desktop Chrome, one iPhone Safari → two buckets, desktop wins ties by count.
    await client.get(
        "/pixel/dev.svg",
        headers={"user-agent": DESKTOP_UA},
    )
    await client.get(
        "/pixel/dev.svg",
        headers={"user-agent": DESKTOP_UA},
    )
    await client.get(
        "/pixel/dev.svg",
        headers={"user-agent": MOBILE_UA},
    )
    data = await _wait_for_views(client, "dev", minimum=3)
    devices = {d["device"]: d["count"] for d in data["devices"]}
    assert devices == {"desktop-chrome": 2, "mobile-safari": 1}
    assert len(data["devices"]) == 2


async def test_stats_error_does_not_leak_exception(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy.exc import SQLAlchemyError

    from collector import database

    async def boom(_doc: str, since: str | None = None, to: str | None = None) -> None:
        raise SQLAlchemyError("host=db.internal user=secret")

    monkeypatch.setattr(database, "get_stats", boom)
    r = await client.get("/stats/some-doc")
    assert r.status_code == 500
    assert "secret" not in r.text
    assert "OperationalError" not in r.text


async def test_rate_limit_blocks_flood(client: AsyncClient) -> None:
    # Pixels silently drop over-limit ingests (an <img> can't render a 429);
    # heartbeats return 429. Keyed on the socket IP, so spoofed XFF headers
    # cannot buy new buckets - even with TRUST_PROXY enabled.
    from collector.config import get_settings
    from collector.main import _limiter

    settings = get_settings()
    old_limit, old_trust = _limiter.limit, settings.trust_proxy
    _limiter.limit, settings.trust_proxy = 3, True
    try:
        codes = [
            (
                await client.post(
                    "/heartbeat/flood-doc",
                    json={"t": 15},
                    headers={"X-Forwarded-For": f"10.{i}.0.{i}"},
                )
            ).status_code
            for i in range(6)
        ]
    finally:
        _limiter.limit, settings.trust_proxy = old_limit, old_trust
    assert codes[:3] == [200, 200, 200]
    assert codes.count(429) == 3


def test_rate_limiter_rejects_when_full_and_keeps_existing_keys() -> None:
    # A flood of new IPs must not evict live buckets (that would reset limits),
    # so once full, untracked keys are refused and the first client keeps its budget.
    from collector.main import RateLimiter

    limiter = RateLimiter(limit=2, max_ips=3)
    assert [limiter.allow("a"), limiter.allow("a")] == [True, True]
    assert [limiter.allow("b"), limiter.allow("c")] == [True, True]
    assert limiter.allow("d") is False  # full: brand-new key rejected, not evicted in
    assert limiter.allow("a") is False  # existing key still enforces its own limit
    assert limiter.allow("a") is False


def test_rate_limiter_respects_limit_zero_and_reset() -> None:
    from collector.main import RateLimiter

    unlimited = RateLimiter(limit=0, max_ips=3)
    assert all(unlimited.allow(str(i)) for i in range(10))
    limiter = RateLimiter(limit=1, max_ips=3)
    assert limiter.allow("x")
    assert not limiter.allow("x")
    limiter.reset()
    assert limiter.allow("x")


async def test_heartbeat_ignores_unknown_fields(client: AsyncClient) -> None:
    r = await client.post("/heartbeat/small-doc", json={"t": 60, "extra": "x"})
    assert r.status_code == 200  # pydantic ignores unknown fields; nothing retained


async def test_heartbeat_rejects_oversize_body(client: AsyncClient) -> None:
    r = await client.post("/heartbeat/small-doc", json={"t": 60, "pad": "x" * 100_000})
    assert r.status_code == 413
    assert r.headers["Cache-Control"].startswith("no-store")


async def test_422_carries_no_store(client: AsyncClient) -> None:
    r = await client.post("/heartbeat/my-doc", json={"t": 999})
    assert r.status_code == 422
    assert r.headers["Cache-Control"].startswith("no-store")


@pytest.mark.parametrize("header", ["DNT", "Sec-GPC", "X-Opt-Out"])
async def test_privacy_signal_skips_ingestion(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, header: str
) -> None:
    from collector import database, main

    def unexpected_identity(_request: Any) -> None:
        pytest.fail("Opted-out requests must not resolve an identity")

    monkeypatch.setattr(main, "_identity", unexpected_identity)
    headers = {header: "1"}
    assert (await client.get("/pixel/private.svg", headers=headers)).status_code == 200
    assert (await client.get("/embed/private", headers=headers)).status_code == 200
    response = await client.post("/heartbeat/private", json={"t": 15}, headers=headers)
    assert response.json() == {"ok": True, "tracked": False}
    assert (await database.get_stats("private"))["events"] == 0
    assert main._limiter._hits == {}


async def test_stats_token_gate(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from collector.config import get_settings

    monkeypatch.setenv("STATS_TOKEN", "shh")
    get_settings.cache_clear()
    try:
        assert (await client.get("/stats/my-doc")).status_code == 403
        assert (await client.get("/stats/my-doc?token=wrong")).status_code == 403
        assert (await client.get("/stats/my-doc?token=shh")).status_code == 200
    finally:
        get_settings.cache_clear()


async def test_embed_default_csp_matches_notion_defaults(client: AsyncClient) -> None:
    from collector.config import DEFAULT_EMBED_ORIGINS

    r = await client.get("/embed/my-doc")
    csp = r.headers["Content-Security-Policy"]
    # Baseline source policy plus the default frame-ancestors list.
    assert "default-src 'none'" in csp
    assert "connect-src 'self'" in csp
    assert "form-action 'none'" in csp
    assert "frame-ancestors " + " ".join(DEFAULT_EMBED_ORIGINS) + ";" in csp


async def test_embed_custom_origins_replace_csp(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from collector.config import get_settings

    monkeypatch.setenv(
        "EMBED_ALLOWED_ORIGINS", "https://docs.example.com, https://*.team.example.com"
    )
    get_settings.cache_clear()
    try:
        r = await client.get("/embed/my-doc")
        csp = r.headers["Content-Security-Policy"]
        assert "frame-ancestors https://docs.example.com https://*.team.example.com;" in csp
        assert "https://notion.so" not in csp  # custom list replaces defaults
        # Baseline source policy stays locked down regardless of ancestors.
        assert "img-src 'self' data:; connect-src 'self'" in csp
    finally:
        get_settings.cache_clear()


async def test_embed_empty_origins_block_all_framing(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from collector.config import get_settings

    monkeypatch.setenv("EMBED_ALLOWED_ORIGINS", "")
    get_settings.cache_clear()
    try:
        r = await client.get("/embed/my-doc")
        csp = r.headers["Content-Security-Policy"]
        assert "frame-ancestors 'none';" in csp
        assert "default-src 'none'" in csp  # baseline stays with framing blocked
    finally:
        get_settings.cache_clear()


async def test_privacy_page_carries_locked_csp(client: AsyncClient) -> None:
    r = await client.get("/privacy")
    assert r.status_code == 200
    csp = r.headers["Content-Security-Policy"]
    assert (
        csp == "default-src 'none'; style-src 'unsafe-inline'; form-action 'none'; base-uri 'none'"
    )


async def test_responses_carry_referrer_policy(client: AsyncClient) -> None:
    for path in ("/badge/ref-pol.svg", "/stats/ref-pol", "/embed/ref-pol", "/privacy"):
        r = await client.get(path)
        assert r.status_code in (200, 400)
        assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_embed_rejects_invalid_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    from collector.config import Settings

    for bad in ("http://example.com", "https://*example.com", "example.com", "https://a.com/path"):
        with pytest.raises(ValueError, match="invalid embed origin"):
            Settings(embed_allowed_origins=[bad])


def test_embed_dedupes_origins() -> None:
    from collector.config import Settings

    s = Settings(
        embed_allowed_origins=["https://example.com", "https://example.com", "https://other.com"]
    )
    assert s.embed_allowed_origins == ["https://example.com", "https://other.com"]


async def test_retention_deletes_old_events_only(client: AsyncClient) -> None:
    from datetime import UTC, datetime, timedelta

    from collector import database

    await database.log_event(doc_key="old-doc", ip_hash="a" * 32)
    await database.log_event(doc_key="new-doc", ip_hash="b" * 32)
    async with database.get_engine().begin() as conn:
        old_cutoff = datetime.now(UTC) - timedelta(days=200)
        await conn.execute(
            update(database.Event).where(database.Event.doc_key == "old-doc").values(ts=old_cutoff)
        )
    deleted = await database.delete_old_events(180)
    assert deleted == 1
    stats = await database.get_stats("new-doc")
    assert stats["events"] == 1
    assert (await database.get_stats("old-doc"))["events"] == 0


async def test_retention_zero_disables(client: AsyncClient) -> None:
    from collector import database

    await database.log_event(doc_key="keep-doc", ip_hash="c" * 32)
    assert await database.delete_old_events(0) == 0
    assert (await database.get_stats("keep-doc"))["events"] == 1


async def test_purge_doc_erases_all_events_for_key(client: AsyncClient) -> None:
    from collector import database

    await database.log_event(doc_key="erase-me", ip_hash="d" * 32)
    await database.log_event(
        doc_key="erase-me", ip_hash="e" * 32, kind="heartbeat", dwell_seconds=15
    )
    await database.log_event(doc_key="keep-me", ip_hash="f" * 32)
    deleted = await database.purge_doc("erase-me")
    assert deleted == 2
    assert (await database.get_stats("erase-me"))["events"] == 0
    assert (await database.get_stats("keep-me"))["events"] == 1


def test_retention_days_rejects_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    from collector.config import Settings

    with pytest.raises(ValueError, match="greater than or equal to 0"):
        Settings(retention_days=-1)


async def test_stats_date_range_filters(client: AsyncClient) -> None:
    from datetime import UTC, datetime, timedelta

    from collector import database

    await database.log_event(doc_key="range-doc", ip_hash="a" * 32)
    async with database.get_engine().begin() as conn:
        week_ago = datetime.now(UTC) - timedelta(days=7)
        await conn.execute(
            update(database.Event).where(database.Event.doc_key == "range-doc").values(ts=week_ago)
        )
    await database.log_event(
        doc_key="range-doc", ip_hash="b" * 32, kind="heartbeat", dwell_seconds=15
    )

    data = (await client.get("/stats/range-doc")).json()
    assert data["events"] == 2
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    week_ago_day = (datetime.now(UTC) - timedelta(days=7)).strftime("%Y-%m-%d")
    assert data["daily"][today]["heartbeats"] == {"15": 1}
    assert data["daily"][week_ago_day]["views"] == 1

    since = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
    recent = (await client.get(f"/stats/range-doc?since={since}")).json()
    assert recent["events"] == 1  # heartbeat only, old view excluded
    assert recent["views"] == 0

    to = (datetime.now(UTC) - timedelta(days=5)).strftime("%Y-%m-%d")
    old = (await client.get(f"/stats/range-doc?to={to}")).json()
    assert old["events"] == 1
    assert old["views"] == 1

    both = await client.get(f"/stats/range-doc?since={since}&to={to}")
    assert both.status_code == 400  # since after to is rejected up front


async def test_stats_rejects_bad_date_filters(client: AsyncClient) -> None:
    assert (await client.get("/stats/my-doc?since=not-a-date")).status_code == 400
    assert (await client.get("/stats/my-doc?since=2026-09-30&to=2026-09-01")).status_code == 400


async def test_badge_custom_label_and_color(client: AsyncClient) -> None:
    r = await client.get("/badge/label-doc.svg?label=Testing&labelColor=6A5ACD&color=ABCDEF")
    assert r.status_code == 200
    svg = r.text
    assert ">Testing" in svg or ">Testing<" in svg
    assert "6A5ACD" in svg
    assert "ABCDEF" in svg


async def test_badge_rejects_bad_label_and_color(client: AsyncClient) -> None:
    r = await client.get("/badge/label-doc.svg?label=" + "x" * 41)
    assert r.status_code == 400
    assert (await client.get("/badge/label-doc.svg?color=zzz")).status_code == 400
    assert (await client.get("/badge/label-doc.svg?color=red;fill=url(#x)")).status_code == 400


async def test_embed_theme_param_override(client: AsyncClient) -> None:
    light = await client.get("/embed/theme-doc?theme=light")
    dark = await client.get("/embed/theme-doc?theme=dark")
    assert light.status_code == dark.status_code == 200
    assert light.text != dark.text  # cascade values differ between forced themes
    assert (await client.get("/embed/theme-doc?theme=weird")).status_code == 200


async def test_robots_and_security_txt(client: AsyncClient) -> None:
    r = await client.get("/robots.txt")
    assert r.status_code == 200
    assert "Disallow: /" in r.text
    assert "X-Robots-Tag" in r.headers
    s = await client.get("/.well-known/security.txt")
    assert s.status_code == 200
    assert "Contact:" in s.text
    assert "Expires:" in s.text


async def test_export_jsonl_gated_by_stats_token(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from collector import database
    from collector.config import get_settings

    await database.log_event(doc_key="exp-doc", ip_hash="a" * 32, ua=DESKTOP_UA)
    await database.log_event(
        doc_key="exp-doc", ip_hash="b" * 32, kind="heartbeat", dwell_seconds=15
    )
    await database.log_event(doc_key="other-doc", ip_hash="c" * 32)

    monkeypatch.setenv("STATS_TOKEN", "shh")
    get_settings.cache_clear()
    try:
        assert (await client.get("/export/exp-doc")).status_code == 403
        r = await client.get("/export/exp-doc?token=shh")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/x-ndjson")
        lines = [line for line in r.text.strip().splitlines() if line]
        assert len(lines) == 2
        rows = [json.loads(line) for line in lines]
        assert {row["doc_key"] for row in rows} == {"exp-doc"}
        assert "ip_hash" in rows[0]
        assert "device" in rows[0]
        assert "ua" not in rows[0]
        assert "raw_ip" not in rows[0]

        # Header auth must work too (keeps the token out of access logs).
        r = await client.get("/export/exp-doc", headers={"X-Stats-Token": "shh"})
        assert r.status_code == 200
    finally:
        get_settings.cache_clear()


async def test_public_export_omits_identity(client: AsyncClient) -> None:
    from collector import database

    await database.log_event(doc_key="pub-doc", ip_hash="a" * 32, ua="Mozilla/5.0")
    r = await client.get("/export/pub-doc")
    assert r.status_code == 200
    rows = [json.loads(line) for line in r.text.strip().splitlines() if line]
    assert len(rows) == 1
    assert "ip_hash" not in rows[0]
    assert "ua" not in rows[0]
    assert "device" not in rows[0]
    assert rows[0]["doc_key"] == "pub-doc"


async def test_opt_out_cookie_and_param_skip_ingestion(client: AsyncClient) -> None:
    from collector import database

    # Cookie opt-out
    r = await client.get("/pixel/opt-cookie.svg", headers={"cookie": "statless_opt_out=1"})
    assert r.status_code == 200
    assert (await database.get_stats("opt-cookie"))["events"] == 0

    # Query param opt-out
    r = await client.get("/pixel/opt-param.svg?optout=1")
    assert r.status_code == 200
    assert (await database.get_stats("opt-param"))["events"] == 0


async def test_opt_out_page_and_toggle(client: AsyncClient) -> None:
    # Initial status: active
    r = await client.get("/opt-out")
    assert r.status_code == 200
    assert "Tracking Active" in r.text

    # Submit opt-out
    post_resp = await client.post(
        "/opt-out",
        content=b"action=opt_out",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert post_resp.status_code == 303
    assert "statless_opt_out" in post_resp.headers.get("set-cookie", "")

    # Status with cookie: opted out
    r2 = await client.get("/opt-out", headers={"cookie": "statless_opt_out=1"})
    assert r2.status_code == 200
    assert "Status: Opted Out" in r2.text

    # Opt back in
    post_in = await client.post(
        "/opt-out",
        content=b"action=opt_in",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert post_in.status_code == 303


async def test_opt_out_cookie_https_cross_site(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from collector.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "base_url", "https://analytics.example.com")

    post_resp = await client.post(
        "/opt-out",
        content=b"action=opt_out",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    cookie_header = post_resp.headers.get("set-cookie", "")
    assert "statless_opt_out=1" in cookie_header
    assert "SameSite=none" in cookie_header
    assert "Secure" in cookie_header
    assert "Partitioned" in cookie_header

    post_in = await client.post(
        "/opt-out",
        content=b"action=opt_in",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert post_in.status_code == 303
    clear_cookie = post_in.headers.get("set-cookie", "")
    assert "statless_opt_out=" in clear_cookie
    assert "Max-Age=0" in clear_cookie


async def test_root_index_discovery(client: AsyncClient) -> None:
    r = await client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["service"] == "statless-pages"
    assert "privacy" in data["usage"]
    assert "opt_out" in data["usage"]
    assert data["usage"]["privacy"].endswith("/privacy")
    assert data["usage"]["opt_out"].endswith("/opt-out")


async def test_privacy_page_statutory_notices(client: AsyncClient) -> None:
    r = await client.get("/privacy")
    assert r.status_code == 200
    assert "Legitimate Interests" in r.text
    assert "Article 11(2)" in r.text
    assert "supervisory authority" in r.text
    assert "/opt-out" in r.text


async def test_erasure_requires_stats_token(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from collector import database
    from collector.config import get_settings

    await database.log_event(doc_key="wipe-doc", ip_hash="a" * 32)

    # No STATS_TOKEN configured: nobody (not even with a token) may erase.
    assert (await client.delete("/docs/wipe-doc")).status_code == 403
    assert (await database.count_events("wipe-doc")) == 1

    monkeypatch.setenv("STATS_TOKEN", "shh")
    get_settings.cache_clear()
    try:
        assert (await client.delete("/docs/wipe-doc")).status_code == 403
        assert (await client.delete("/docs/wipe-doc?token=wrong")).status_code == 403
        r = await client.delete("/docs/wipe-doc", headers={"X-Stats-Token": "shh"})
        assert r.status_code == 200
        assert r.json() == {"ok": True, "deleted": 1}
        assert (await database.count_events("wipe-doc")) == 0
        # Erasing again is idempotent.
        r = await client.delete("/docs/wipe-doc?token=shh")
        assert r.json() == {"ok": True, "deleted": 0}
    finally:
        get_settings.cache_clear()


async def test_security_txt_is_configurable(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from collector.config import get_settings

    monkeypatch.setenv("SECURITY_CONTACT", "mailto:sec@example.com")
    monkeypatch.setenv("SECURITY_POLICY", "https://example.com/security")
    get_settings.cache_clear()
    try:
        r = await client.get("/.well-known/security.txt")
        assert r.status_code == 200
        assert "Contact: mailto:sec@example.com" in r.text
        assert "Policy: https://example.com/security" in r.text
    finally:
        get_settings.cache_clear()


async def test_view_dedupe_window(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from collector import database
    from collector.config import get_settings

    monkeypatch.setenv("VIEW_DEDUPE_MINUTES", "5")
    get_settings.cache_clear()
    try:
        await client.get("/pixel/dedupe-doc.svg")  # background task may not run instantly
        await client.get("/pixel/dedupe-doc.svg")
        await client.get("/pixel/dedupe-doc.svg")
        for _ in range(20):
            if (await database.get_view_count("dedupe-doc")) == 1:
                break
            await asyncio.sleep(0.1)
        assert (await database.get_view_count("dedupe-doc")) == 1
    finally:
        get_settings.cache_clear()


async def test_view_dedupe_disabled_by_default(client: AsyncClient) -> None:
    from collector import database

    await client.get("/pixel/dedup2.svg")
    await client.get("/pixel/dedup2.svg")
    await client.get("/pixel/dedup2.svg")
    for _ in range(20):
        if (await database.count_events("dedup2")) == 3:
            break
        await asyncio.sleep(0.1)
    assert (await database.count_events("dedup2")) == 3


def test_secret_salt_is_deterministic_within_rotation_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from collector import salt as salt_mod

    s1 = salt_mod.derive_ephemeral_salt("topsecret")
    s2 = salt_mod.derive_ephemeral_salt("topsecret")
    assert s1 == s2  # stable within the current rotation window


async def test_security_txt_and_robots_no_store(client: AsyncClient) -> None:
    r = await client.get("/robots.txt")
    assert r.headers["Cache-Control"].startswith("no-store")


async def test_bot_user_agent_is_not_tracked(client: AsyncClient) -> None:
    from collector import database

    await client.get(
        "/pixel/bot-doc.svg",
        headers={
            "user-agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
        },
    )
    await client.get("/pixel/bot-doc.svg", headers={"user-agent": "Slackbot-LinkExpanding 1.0"})
    await asyncio.sleep(0.1)
    assert await database.count_events("bot-doc") == 0


async def test_preview_and_prefetch_headers_are_not_tracked(client: AsyncClient) -> None:
    from collector import database

    await client.get("/pixel/prefetch-doc.svg", headers={"sec-purpose": "prefetch"})
    await client.get("/pixel/prefetch-doc.svg", headers={"x-purpose": "preview"})
    await asyncio.sleep(0.1)
    assert await database.count_events("prefetch-doc") == 0


async def test_bot_heartbeat_reports_not_tracked(client: AsyncClient) -> None:
    r = await client.post(
        "/heartbeat/bot-hb", json={"t": 15}, headers={"user-agent": "AhrefsBot/7.0"}
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True, "tracked": False}


async def test_filter_bots_can_be_disabled(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from collector import database
    from collector.config import get_settings

    monkeypatch.setenv("FILTER_BOTS", "false")
    get_settings.cache_clear()
    try:
        await client.get("/pixel/bot-kept.svg", headers={"user-agent": "Googlebot/2.1"})
        for _ in range(20):
            if await database.count_events("bot-kept") >= 1:
                break
            await asyncio.sleep(0.1)
        assert await database.count_events("bot-kept") == 1
    finally:
        get_settings.cache_clear()


async def test_utm_params_become_ref_tag(client: AsyncClient) -> None:
    await client.get(
        "/pixel/utm-doc.svg?utm_source=Newsletter&utm_medium=email&utm_campaign=Launch%202026"
    )
    data = await _wait_for_views(client, "utm-doc")
    assert [r["referrer"] for r in data["referrers"]] == ["newsletter-email-launch-2026"]


async def test_explicit_ref_beats_utm(client: AsyncClient) -> None:
    await client.get("/pixel/utm-ref.svg?ref=explicit&utm_source=newsletter")
    data = await _wait_for_views(client, "utm-ref")
    assert [r["referrer"] for r in data["referrers"]] == ["explicit"]


async def test_overview_lists_docs_and_scopes_by_prefix(client: AsyncClient) -> None:
    from collector import database

    await database.log_event(doc_key="site-a", ip_hash="a" * 32)
    await database.log_event(doc_key="site-a", ip_hash="b" * 32)
    await database.log_event(doc_key="site-a", ip_hash="a" * 32, kind="heartbeat", dwell_seconds=15)
    await database.log_event(doc_key="site_a", ip_hash="e" * 32)
    await database.log_event(doc_key="other-c", ip_hash="d" * 32)

    body = (await client.get("/overview")).json()
    docs = {d["doc"]: d for d in body["docs"]}
    assert body["count"] == 3
    assert docs["site-a"]["views"] == 2
    assert docs["site-a"]["events"] == 3
    assert docs["site-a"]["uniques"] == 2
    assert docs["site-a"]["last_ts"]

    # `_` is a LIKE wildcard: escaping must keep site_ from also matching site-a.
    scoped = (await client.get("/overview?prefix=site_")).json()
    assert {d["doc"] for d in scoped["docs"]} == {"site_a"}


async def test_overview_rejects_bad_prefix_and_gates_token(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from collector.config import get_settings

    assert (await client.get("/overview?prefix=bad..key")).status_code == 400
    monkeypatch.setenv("STATS_TOKEN", "shh")
    get_settings.cache_clear()
    try:
        assert (await client.get("/overview")).status_code == 403
        assert (await client.get("/overview?token=shh")).status_code == 200
    finally:
        get_settings.cache_clear()
