<div align="center">

# statless-pages

**Self-hosted page-view counts - without cookies, fingerprinting, or a third-party JS SDK.**

<p>
  <a href="https://github.com/statless/statless-pages/actions/workflows/ci.yml">
    <img src="https://img.shields.io/github/actions/workflow/status/statless/statless-pages/ci.yml?branch=main&amp;style=flat-square&amp;logo=github&amp;label=CI" alt="CI status on main" />
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-AGPLv3-2563EB?style=flat-square" alt="License: AGPLv3" />
  </a>
</p>

<p>
  <a href="pyproject.toml">
    <img src="https://img.shields.io/badge/Python-3.14%2B-3776AB?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python 3.14 or newer" />
  </a>
  <a href="https://fastapi.tiangolo.com">
    <img src="https://img.shields.io/badge/FastAPI-async-009688?style=flat-square&amp;logo=fastapi&amp;logoColor=white" alt="Built with async FastAPI" />
  </a>
</p>

[Report a bug](https://github.com/statless/statless-pages/issues) · [Request a feature](https://github.com/statless/statless-pages/issues) · [Privacy notice](#privacy--compliance)

</div>

---

Statless Pages is a self-hosted, **cookie-free analytics** collector. It records requests to an invisible SVG pixel or a Notion embed and exposes counts through a JSON API. An optional SVG badge displays the view count; **the badge does not record views**.

## Why statless

- **Small deployment** - one container with SQLite; PostgreSQL optional
- **No third-party SDK** - pixels need no JavaScript; the embed includes its own heartbeat script
- **Approximate analytics** - views, rotating-IP-hash uniques, countries, referrers, and embed dwell buckets at 15/30/60/120 seconds
- **Privacy signals honored** - requests carrying `DNT: 1` or `Sec-GPC: 1` are not recorded
- **Human-first counts** - crawlers, link-preview/unfurl bots, headless browsers, and prefetch fetches are skipped by default (`FILTER_BOTS=false` to keep them)
- **Bounded retention** - events older than `RETENTION_DAYS` (default 180) are auto-deleted
- **Self-hosted storage** - no cookies or fingerprinting; the collector stores salted IP hashes rather than raw IPs

> Dwell buckets measure elapsed time after an embed loads, **not scroll depth or proof of reading**. Image proxies, caching, blocked images, and prefetching affect accuracy. See [platform compatibility](#platform-compatibility).

**Stack:** AGPLv3 · Python 3.14+ · FastAPI · SQLite (default) / PostgreSQL · GeoIP2 · Jinja2

---

## Table of contents

- [Notion pages](#notion-pages)
- [How it compares](#how-it-compares)
- [Quick start](#quick-start)
- [Platform compatibility](#platform-compatibility)
- [Endpoints](#endpoints)
- [Configuration](#configuration)
- [GeoIP2 database](#geoip2-database)
- [Local development](#local-development)
- [Privacy & compliance](#privacy--compliance)
- [Erasure & retention operations](#erasure--retention-operations)
- [Scaling notes](#scaling-notes)
- [License](#license)

---

## Notion pages

Statless is built for **Notion pages first**. Drop one embed into any Notion doc to get a live view count plus dwell time:

1. In Notion, type `/embed` and paste `https://YOUR-HOST/embed/my-page`.
2. The widget renders a live `● N views` badge and beacons dwell at 15s / 30s / 60s / 120s.
3. Read the numbers at `https://YOUR-HOST/stats/my-page`.

The default `frame-ancestors` allow-list already covers `notion.so` and `notion.site`, so no extra configuration is needed. See [Quick start](#quick-start) for full setup, and [Platform compatibility](#platform-compatibility) for every other surface (custom sites, newsletters, READMEs, Obsidian Publish).

---

## How it compares

Statless is deliberately small. It counts page views and embed dwell on surfaces that other trackers ignore - Notion pages, newsletters, and READMEs - without asking visitors to run a third-party script.

| | statless-pages | Plausible CE | Umami | GoatCounter |
|---|---|---|---|---|
| Collection | SVG pixel or iframe embed - **no JS for pixels** | JS snippet | JS snippet | JS snippet or no-JS image pixel |
| Notion embed with dwell time | **Built in** | No | No | No |
| README / Markdown counter | **Built-in SVG badge** | JS traffic badge | No | No |
| Self-host footprint | **One container + SQLite** (Postgres optional) | Postgres + ClickHouse | Node + Postgres/MySQL | One Go binary + SQLite/Postgres |
| License | AGPLv3 | AGPLv3 | MIT | EUPL-1.2 (modified) |

> Competitor capabilities change; verify against each project's docs. Last reviewed 2026-09.

**Not a fit if** you need funnels, session replay, custom events, or a full dashboard - use [Plausible](https://plausible.io), [Umami](https://umami.is), or [GoatCounter](https://www.goatcounter.com) for that. Statless trades those for a tiny footprint and an embed-first design.

---

## Quick start

### Prerequisites

- **Docker Engine or Docker Desktop**, with Docker Compose v2, for the container setup.
- **Git** to clone the repository.
- **Python 3.14+ and uv** only if you prefer [local development](#local-development) without Docker.
- **A public HTTPS host** when embedding on Notion, GitHub, or another hosted platform. Localhost is for testing on your own machine.

**1 · Clone the repository**

```bash
git clone https://github.com/statless/statless-pages.git
cd statless-pages
```

**2 · Start the server**

On macOS or Windows with Docker Desktop:

```bash
docker compose up -d --build
```

On Linux, use your host UID/GID so the non-root container can write to `./data`:

```bash
STATLESS_UID=$(id -u) STATLESS_GID=$(id -g) docker compose up -d --build
```

Check the server at `http://localhost:8000/healthz`. It should return `{"ok":true}`.

**3 · Choose a page key and integration**

Replace `https://YOUR-HOST` in the examples with your collector's public HTTPS address. Set `BASE_URL` to that same address before using the embed.

Pick a `doc_key` per page - any slug like `q3-roadmap`, `launch-post`, or `my-repo-readme` (letters, digits, `-` and `_`, up to 64 characters) - then use one of the integrations below.

### Notion - embed widget (views + dwell time)

1. In Notion, type `/embed`, paste:
   ```
   https://YOUR-HOST/embed/q3-roadmap
   ```
2. The widget shows a live `● N views` badge and fires `navigator.sendBeacon` heartbeats at 15s / 30s / 60s / 120s. Light/dark mode follows the OS.

> **Note:** the embed HTML carries `CSP: frame-ancestors` restricted to `notion.so` / `notion.site` domains by default, so it will not render inside other iframe-based tools (Coda, Confluence, etc.). Use the pixel or badge below there, or set `EMBED_ALLOWED_ORIGINS` (see [configuration](#configuration)) to allow more origins.

### Custom sites - iframe embed (views + dwell time)

On any site you control (Ghost, WordPress, Hugo, static HTML):

1. Add your site's origin to the allow-list, e.g. `EMBED_ALLOWED_ORIGINS="https://example.com"`.
2. Insert the iframe in your template or page:
   ```html
   <iframe src="https://YOUR-HOST/embed/q3-roadmap" style="width:auto;height:28px;border:0"></iframe>
   ```

The widget renders the live badge and sends dwell heartbeats, exactly like the Notion embed. For platforms that sanitize iframes but allow images, use the pixel instead.

### Substack / any newsletter / any HTML - invisible pixel

```html
<img src="https://YOUR-HOST/pixel/launch-post.svg" width="1" height="1" alt="" />
```

The collector sends cache-prevention headers, but image proxies and email clients may still cache, prefetch, or block requests. Counts represent recorded fetches, not guaranteed human opens. Use this snippet wherever the platform permits remote images or raw HTML.

### GitHub README - badge (display only) + pixel (tracking)

```markdown
![views](https://YOUR-HOST/badge/my-repo-readme.svg)
<img src="https://YOUR-HOST/pixel/my-repo-readme.svg" width="1" height="1" alt="" />
```

The badge is a read-only SVG that displays the current count - it does **not** record views. GitHub proxies README images through `camo.githubusercontent.com`, so referrer and country data will not be meaningful there.

### Obsidian Publish - pixel + badge

Obsidian Publish sanitizes note HTML, so treat it like a README rather than a Notion page - use Markdown images, not the iframe:

```markdown
![views](https://YOUR-HOST/badge/my-note.svg)
<img src="https://YOUR-HOST/pixel/my-note.svg" width="1" height="1" alt="" />
```

The pixel records fetches; the badge is display-only. Publish fronts sites with its own CDN, so referrer and country may be degraded the same way GitHub's Camo proxy degrades them.

The `/embed` iframe is **unverified** here - Obsidian strips most raw HTML, so it may not render. If it does, you must add your Publish origin to `EMBED_ALLOWED_ORIGINS`, and because that list **replaces** the Notion defaults, re-list them:

```bash
EMBED_ALLOWED_ORIGINS="https://publish.obsidian.md,https://notes.yourdomain.com,https://notion.so,https://*.notion.so,https://notion.site,https://*.notion.site"
```

Only then would dwell-time heartbeats work on Publish. Test before relying on it.

**4 · Watch it count**

```bash
curl http://localhost:8000/stats/q3-roadmap
```

```json
{
  "doc": "q3-roadmap",
  "events": 42,
  "views": 30,
  "uniques": 18,
  "dwell": {"15": 12, "30": 9, "60": 5, "120": 2},
  "daily": {
    "2026-09-17": {"views": 12, "uniques": 9, "heartbeats": {"15": 5, "60": 2}},
    "2026-09-18": {"views": 18, "uniques": 11, "heartbeats": {"30": 4}}
  },
  "countries": [{"country": "US", "count": 14}, {"country": "DE", "count": 7}],
  "referrers": [{"referrer": "https://news.ycombinator.com", "count": 9}],
  "devices": [{"device": "desktop-chrome", "count": 16}, {"device": "mobile-safari", "count": 9}]
}
```

---

## Platform compatibility

| Platform | Method | Dwell time | Referrer/Country | Notes |
|---|---|---|---|---|
| **Notion** | `/embed` | Yes (heartbeats) | Partial | Works out of the box (default allow-list covers `notion.so` / `notion.site`) |
| **Custom sites** (Ghost, WordPress, Hugo, static HTML) | `<iframe>` embed or pixel | Yes (embed) | Yes | Set `EMBED_ALLOWED_ORIGINS` to your site's origin, then insert `<iframe src="https://YOUR-HOST/embed/KEY"></iframe>` |
| **Substack, Ghost newsletters** | `<img>` pixel | No | Yes | Requires raw HTML blocks or template editing |
| **Coda** | Pixel/badge; embed unverified | No (pixel) | Origin only (`https://coda.io`) | Coda loads content in its own iframes; adding `https://coda.io` to `EMBED_ALLOWED_ORIGINS` removes the server-side block, but whether Coda accepts generic embeds varies - test first. Pixel always works |
| **Confluence** | Pixel/badge; embed unverified | No (pixel) | Varies | Same: add your Confluence origin to `EMBED_ALLOWED_ORIGINS` and test whether it renders the iframe |
| **GitHub README** | Badge + pixel | No | No (GitHub proxies images via Camo) | Badge renders live counts; pixel records the fetch. Markdown sanitizes `<iframe>`, so embeds are impossible here |
| **Obsidian Publish** | Pixel + badge; embed unverified | No (pixel) | Partial (Publish CDN) | Publish sanitizes note HTML; Markdown images render, so pixel + badge work. If the `/embed` iframe renders, add your Publish origin to `EMBED_ALLOWED_ORIGINS` and test |
| **GitLab, Codeberg, plain HTML sites** | Badge + pixel | No | Varies | Same as GitHub; check whether the platform proxies images |

**Key constraints, in one place:**

1. **The embed only frames on allow-listed origins.** Default CSP: `frame-ancestors https://notion.so https://*.notion.so https://notion.site https://*.notion.site`. Set `EMBED_ALLOWED_ORIGINS` to frame anywhere you control - heartbeats (dwell buckets) work there too. `EMBED_ALLOWED_ORIGINS=""` blocks all framing.
2. **Pixels require raw HTML.** Platforms that sanitize `<img>` tags (Notion blocks, Slack, some email clients that strip tracking pixels) will not record.
3. **Image proxies strip attribution.** GitHub (Camo), some corporate mail scanners, and privacy tools proxy or block remote images, degrading referrer/country accuracy.
4. **Dwell time needs JavaScript.** Only embeds (which run the heartbeat script) get dwell buckets; pixels record a single view with no dwell data.

---

## Endpoints

| Method | Route | Notes |
|---|---|---|
| `GET` | `/` | JSON service index listing usage endpoints, `/privacy`, and `/opt-out` |
| `GET` | `/pixel/{doc_key}.svg` | 1×1 transparent SVG. `Cache-Control: no-store …`, `Pragma: no-cache`, `Expires: 0`, `X-Robots-Tag: noindex, nofollow` |
| `GET` | `/embed/{doc_key}` | ~2.8KB HTML embed widget (badge + dwell heartbeats). Optional `?theme=light\|dark` forces a palette (default: follows the OS). `CSP: frame-ancestors` allow-list (Notion domains by default; configurable via `EMBED_ALLOWED_ORIGINS`) |
| `POST` | `/heartbeat/{doc_key}` | JSON `{"t": 15\|30\|60\|120}` via `navigator.sendBeacon`. Bodies > 4 KB get `413`; `429` past the rate limit |
| `GET` | `/badge/{doc_key}.svg` | Counter badge for READMEs. Display-only: does not record views; pair with a pixel if you want fetches counted. Customize with `?label=` (up to 40 characters: letters, digits, spaces, `. _ -`), `?labelColor=RRGGBB`, `?color=RRGGBB` |
| `GET` | `/stats/{doc_key}` | JSON: views, uniques, daily time-series, dwell buckets, top countries/referrers/devices. **Set `STATS_TOKEN` in production** to satisfy GDPR Art. 25(2) (Data Protection by Default) and require `?token=...` or the `X-Stats-Token` header. Filter with `?since=YYYY-MM-DD&to=YYYY-MM-DD` (inclusive UTC dates) |
| `GET` | `/overview` | JSON: per-doc totals for the whole site, busiest first (`doc`, `events`, `views`, `uniques`, `last_ts`). `?prefix=` scopes to a `doc_key` prefix. Same `STATS_TOKEN` gate as `/stats` |
| `GET` | `/export/{doc_key}` | NDJSON dump of raw event rows for one doc (oldest first, streamed; same `STATS_TOKEN` gate). Operator document backup and audit export. When stats are public (no `STATS_TOKEN`), pseudonymous identity fields (`ip_hash`, `device`) are omitted. Note: not an individual GDPR Art. 15/20 data subject export (exporting all events for a doc would disclose other visitors' records, violating Art. 15(4) / Art. 33) |
| `DELETE` | `/docs/{doc_key}` | Document lifecycle purge: hard-delete every stored event for one doc. Requires `STATS_TOKEN` to be configured AND supplied; with no token configured the endpoint refuses (`403`). Individual erasure is governed by GDPR Art. 11(2) as individual visits are non-identifiable |
| `GET` | `/privacy` | Privacy notice with GDPR Art. 13 disclosures: legal basis (Art. 6(1)(f)), stored fields, retention, complaint rights, and opt-out routes |
| `GET` | `/opt-out` | Direct visitor opt-out page & toggle (satisfies French CNIL exemption and GDPR Art. 21 objection) |
| `GET` | `/robots.txt`, `/.well-known/security.txt` | Crawler off-switch (`Disallow: /`) and an RFC 9116 compliant security disclosure template with required `Expires:` line |
| `GET` | `/healthz` | Liveness probe |

`doc_key` may contain letters, digits, `-` and `_` only, and must be 1-64 characters long.

---

## Configuration

For Docker Compose or local development, copy `.env.example` to `.env` and set your variables. The supplied [`docker-compose.yml`](docker-compose.yml) automatically forwards all configuration variables from `.env` to the container.

> **Before going public:** use HTTPS, persist and back up `./data`, set `STATS_TOKEN` (required for GDPR Art. 25(2) Data Protection by Default), and review proxy trust and retention settings. Avoid putting secrets in page keys or sharing token-bearing URLs.

| Var | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/statless.db` | Use `postgresql+asyncpg://user:pass@db:5432/statless` for Postgres |
| `GEOIP_DB_PATH` | `data/GeoLite2-Country.mmdb` | Country resolution; `XX` when missing |
| `SALT_ROTATE_HOURS` | `24` | IP-hash salt rotation window (must be > 0) |
| `RETENTION_DAYS` | `180` | Auto-delete events older than this. `0` disables automatic deletion (you then own the storage-limitation duty) |
| `BASE_URL` | `http://localhost:8000` | Rendered into embed/badge snippets |
| `SECURITY_CONTACT` | `mailto:security@YOUR-DOMAIN.example` | Contact line for `/.well-known/security.txt` - **replace before going public** |
| `SECURITY_POLICY` | *(empty = omitted)* | Optional `Policy:` URL for `/.well-known/security.txt` |
| `SECURITY_EXPIRES` | *(empty = 1 year ahead)* | Optional RFC 3339 timestamp for RFC 9116 `Expires:` in `security.txt` |
| `CONTROLLER_NAME` | *(empty = default)* | Controller organization/name for `/privacy` notice |
| `CONTROLLER_CONTACT` | *(empty = default)* | Controller privacy contact for `/privacy` notice |
| `TRUST_PROXY` | `false` | Honor `X-Forwarded-For` / `X-Real-IP` for IP **hashing/geo** only. Leave off unless behind a proxy that overwrites these headers. |
| `RATE_LIMIT` | `120` | Tracked events per minute per client (0 disables). Over-limit pixels are silently dropped; heartbeats get `429`. |
| `STATS_TOKEN` | *(empty = public)* | When set, `GET /stats`, `GET /overview`, and `GET /export` require token auth. **Set in production for GDPR Art. 25(2) Data Protection by Default.** |
| `EMBED_ALLOWED_ORIGINS` | Notion apex + wildcard domains | Comma-separated `https` origins allowed to frame `/embed`. |
| `VIEW_DEDUPE_MINUTES` | `0` (off) | Collapse repeated views of the same page by the same IP-hash within the window. |
| `FILTER_BOTS` | `true` | Skip crawlers, link-preview bots, and prefetch fetches so counts reflect humans. |
| `SERVER_SECRET` | *(empty = random)* | Derive salts deterministically (`HMAC(secret, date+window)`) for multi-replica consistency. See scaling notes for DPIA trade-offs. |
| `STATLESS_HOST` / `STATLESS_PORT` | `0.0.0.0` / `8000` | Bind for the `statless` entrypoint |
| `STATLESS_UID` / `STATLESS_GID` | `10001` | docker-compose only: run container as host user |

---

## GeoIP2 database

`data/GeoLite2-Country.mmdb` is **not** committed (MaxMind license). Download it free:

1. Create an account at https://www.maxmind.com/en/geolite2/signup
2. Download **GeoLite2 Country** (`.mmdb`), place it at `data/GeoLite2-Country.mmdb`
3. Restart - the DB is loaded once into RAM (`MODE_MEMORY`); lookups never touch disk.

Without the file the service still runs; all countries report as `XX`.

> This product includes GeoLite2 data created by MaxMind, available from https://www.maxmind.com - required attribution notice per the GeoLite2 EULA.

---

## Local development

Requires [uv](https://docs.astral.sh/uv/). `uv.lock` is committed so everyone gets the same dependency versions.

```bash
uv sync --extra dev     # creates .venv from uv.lock
uv run pytest -q        # tests
uv run ruff check collector tests
uv run uvicorn collector.main:app --reload
```

---

## Privacy & compliance

**The short version:** no tracking cookies, no device identifiers, no hardware fingerprinting, no raw IPs or raw User-Agents stored, and requests carrying `DNT: 1`, `Sec-GPC: 1`, or opt-out cookies are dropped before recording. IP hashes rotate every 24h; retention is bounded by default (180 days). The full statutory notice is served at `/privacy`, and a direct opt-out page lives at `/opt-out`.

**Do you need a consent banner?** It depends on your integration and jurisdiction:
- **SVG Pixels:** Pure server-side HTTP GET; does not access terminal storage or run scripts. Under traditional ePrivacy Art. 5(3) interpretations, no banner is needed. (Note: EDPB Guidelines 2/2023 take an expansive view on tracking pixels).
- **Embed Widgets (`/embed`):** Executes client-side JavaScript for dwell-time telemetry (`sendBeacon` and visibility listeners). Under **Germany's TDDDG § 25**, this engages device access rules; using the no-JS pixel is the lower-risk route there without a consent banner.
- **France (CNIL):** CNIL's analytics exemption criteria are supported via the direct visitor opt-out page at `/opt-out`.
- **GDPR Lawful Basis:** Processing pseudonymous IP hashes relies on Legitimate Interests (Art. 6(1)(f)). Operators must conduct a Legitimate Interest Assessment (LIA) and name a controller in `/privacy`.
- **Data Protection by Default (Art. 25(2)):** Configure `STATS_TOKEN` so that page keys and visitor statistics are not publicly indexable.
- **US Privacy Laws:** GPC (`Sec-GPC: 1`) is honored out-of-the-box, supporting state universal opt-out signals (CCPA/CPRA). No personal information is sold or shared.

See [doc/COMPLIANCE.md](doc/COMPLIANCE.md) for the detailed legal audit and DPIA checklist.

---

## Erasure & retention operations

- **Automatic pruning:** events older than `RETENTION_DAYS` (default 180) are deleted daily.
- **Document lifecycle purge:** `DELETE /docs/{doc_key}` (or `await db.purge_doc("key")`) hard-deletes every stored event for one doc key (operator decommissioning). Requires `STATS_TOKEN`.
- **Operator audit export:** `GET /export/{doc_key}` streams an NDJSON dump of event rows for backup and audit. (Not for individual Art. 15/20 data subject requests, as disclosing all events for a page would violate third-party privacy).
- **Individual erasure & access limits:** Because data is pseudonymous under rotating ephemeral salts and no identifiers or raw IPs are stored, individual visitors cannot be identified from stored rows. Individual access and erasure requests are governed by **GDPR Article 11(2)**.

---

## Scaling notes

**Run a single worker** with SQLite by default. The rate limiter is in-memory and SQLite is single-writer.

**If you outgrow it:** move to PostgreSQL, run N replicas, and delegate rate limiting to your proxy. For unique counts across replicas, configure `SERVER_SECRET` so salts derive from `HMAC(secret, date + window)`.

> **DPIA Note on `SERVER_SECRET`:** While ephemeral RAM salts provide forward-secrecy (past hashes become un-correlatable upon rotation), `SERVER_SECRET` derives salts deterministically. Anyone with access to the database and `SERVER_SECRET` could reverse 32-bit IPv4 hashes via brute force. Protect `SERVER_SECRET` accordingly.

---

## License

Distributed under the [AGPLv3](LICENSE). See [`LICENSE`](LICENSE) for more information.
