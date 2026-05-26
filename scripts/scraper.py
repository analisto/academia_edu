#!/usr/bin/env python3
"""
academia.edu full-scale scraper — hardened for interruption-safety.

Pipeline:
  1. Seed: scrape https://www.academia.edu/ -> university subdomains.
  2. Per subdomain: scrape https://{sub}.academia.edu/ -> /Departments/{Name} URLs.
  3. Per department: paginate -> profile URLs.
  4. Per profile: parse embedded JSON (user_id, dept, university, photo, dates)
                  and <meta name="description"> (followers/following/papers counters).
  5. Per user_id: GET /v0/users/{id}/details + /v0/certifications/ranks/author_ranks/{id}.
  6. Append a row to data/data.csv (streaming, dedup-safe across crashes).

Crash safety:
  - CSV is the single source of truth. On startup `done_user_ids` is rebuilt by
    scanning data.csv, so a kill -9 between a row write and a checkpoint flush
    can never produce duplicates and can never lose progress.
  - Each row is written + fsync'd under a lock before `done_user_ids` is updated.
  - SIGINT / SIGTERM sets a stop event; in-flight HTTP requests finish, then the
    scraper exits cleanly (typically within REQUEST_TIMEOUT seconds).
  - Failure-rate watchdog: if >50% of the last 60s of requests fail, logs a loud
    warning so a Cloudflare ban isn't silent.

Stack: asyncio + curl_cffi.AsyncSession (Chrome TLS impersonation, bypasses
Cloudflare) + aiohttp (seed fetch, falls back to curl_cffi) + sync fsync for
the CSV (correctness > raw throughput on the writer side).

Run:   python3 scripts/scraper.py
"""

import asyncio
import csv as csvlib
import json
import logging
import os
import re
import signal
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiofiles  # noqa: F401  (kept in stack for compatibility / future async IO)
import aiohttp
from curl_cffi.requests import AsyncSession

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUT_CSV = DATA_DIR / "data.csv"
LOG_FILE = DATA_DIR / "scraper.log"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# --- Tunables ---
GLOBAL_CONCURRENCY = 40
PER_HOST_CONCURRENCY = 6
SUBDOMAIN_CONCURRENCY = 4         # how many universities to crawl in parallel
MAX_DEPT_PAGES = 50
RETRY_LIMIT = 4
RETRY_BASE_DELAY = 2.0
REQUEST_TIMEOUT = 30
IMPERSONATE = "chrome"
FAILURE_WINDOW_SEC = 60
FAILURE_RATE_THRESHOLD = 0.5
FAILURE_MIN_SAMPLES = 20

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("scraper")

CSV_FIELDS = [
    "subdomain", "university_id", "university_name",
    "department_id", "department_name", "department_url",
    "user_id", "page_name", "display_name",
    "first_name", "middle_initials", "last_name",
    "profile_url", "photo_url", "has_photo", "created_at",
    "followers_count", "following_count", "papers_count",
    "about", "public_email",
    "author_rank", "bragworthy",
    "scraped_at",
]

# --- Shared runtime state ---
done_user_ids: set = set()
seen_profile_urls: set = set()  # short-circuit re-fetches on resume
csv_lock = asyncio.Lock()
csv_fh = None                          # type: Optional[object]  # sync file handle
csv_writer = None                      # csv.DictWriter
stop_event: Optional[asyncio.Event] = None
global_sem: Optional[asyncio.Semaphore] = None
host_sems: dict = {}
# Sliding-window failure tracker: list of (timestamp, ok_bool)
recent_results: deque = deque()
results_lock = asyncio.Lock()
last_watchdog_warn: float = 0.0


def _host_sem(host: str) -> asyncio.Semaphore:
    sem = host_sems.get(host)
    if sem is None:
        sem = host_sems[host] = asyncio.Semaphore(PER_HOST_CONCURRENCY)
    return sem


async def _record_result(ok: bool) -> bool:
    """Returns True if the watchdog wants the caller to back off."""
    global last_watchdog_warn
    now = time.monotonic()
    async with results_lock:
        recent_results.append((now, ok))
        cutoff = now - FAILURE_WINDOW_SEC
        while recent_results and recent_results[0][0] < cutoff:
            recent_results.popleft()
        n = len(recent_results)
        if n >= FAILURE_MIN_SAMPLES:
            failed = sum(1 for _, o in recent_results if not o)
            if failed / n >= FAILURE_RATE_THRESHOLD and now - last_watchdog_warn > 30:
                last_watchdog_warn = now
                log.error(
                    "WATCHDOG: %d/%d requests failed in last %ds (%.0f%%). "
                    "Pausing 60s — likely Cloudflare rate-limit or network issue.",
                    failed, n, FAILURE_WINDOW_SEC, 100 * failed / n,
                )
                return True
    return False


# --- HTTP ---
async def fetch(session: AsyncSession, url: str, host: str) -> Optional[str]:
    """GET with retry/backoff. Returns body text or None. Records success/failure."""
    assert global_sem is not None
    if stop_event is not None and stop_event.is_set():
        return None
    async with global_sem, _host_sem(host):
        for attempt in range(RETRY_LIMIT):
            if stop_event is not None and stop_event.is_set():
                return None
            try:
                # Hard outer cap — curl_cffi's own timeout has been observed to
                # blow past the requested value under load, so we enforce it
                # here in asyncio terms.
                r = await asyncio.wait_for(
                    session.get(url, impersonate=IMPERSONATE, timeout=REQUEST_TIMEOUT),
                    timeout=REQUEST_TIMEOUT + 5,
                )
                if r.status_code == 200:
                    await _record_result(True)
                    return r.text
                if r.status_code in (404, 403, 410):
                    await _record_result(True)  # not a transport failure
                    return None
                log.warning("HTTP %d %s (attempt %d/%d)", r.status_code, url, attempt + 1, RETRY_LIMIT)
            except asyncio.TimeoutError:
                log.warning("TIMEOUT %s (attempt %d/%d)", url, attempt + 1, RETRY_LIMIT)
            except Exception as e:
                log.warning("ERR %s: %s (attempt %d/%d)", url, e, attempt + 1, RETRY_LIMIT)
            await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))
        backoff = await _record_result(False)
        if backoff and stop_event is not None and not stop_event.is_set():
            log.warning("Watchdog backoff: sleeping 60s before resuming")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=60)
            except asyncio.TimeoutError:
                pass
        return None


# --- Discovery parsers ---
_SUB_PAT = re.compile(r'https?://([a-z0-9][a-z0-9\-]+)\.academia\.edu')
_EXCLUDE_SUBS = {"www", "a", "0", "support", "static", "s3", "m"}


def discover_subdomains(html_text: str) -> set:
    subs = set(_SUB_PAT.findall(html_text or "")) - _EXCLUDE_SUBS
    return {s for s in subs if not s.startswith(("academia-",))}


def discover_department_urls(html_text: str, subdomain: str) -> set:
    pat = re.compile(
        rf'https?://{re.escape(subdomain)}\.academia\.edu(/Departments/[A-Za-z0-9_%\-\.]+)'
    )
    paths = set(pat.findall(html_text))
    cleaned = set()
    for p in paths:
        if p.endswith("/Documents"):
            p = p[: -len("/Documents")]
        cleaned.add(f"https://{subdomain}.academia.edu{p}")
    return cleaned


def discover_profile_urls(html_text: str, subdomain: str) -> set:
    pat = re.compile(
        rf'https?://{re.escape(subdomain)}\.academia\.edu/([A-Za-z0-9%\-_]+)(?=["\'?#])'
    )
    raw = set(pat.findall(html_text))
    base = f"https://{subdomain}.academia.edu/"
    out = set()
    for p in raw:
        if not p:
            continue
        if p.startswith(("Departments", "Documents", "v0", "open_search", "search", "register", "login")):
            continue
        if len(p) < 3:
            continue
        out.add(f"{base}{p}")
    return out


# --- Profile HTML parsing ---
_PROFILE_JSON_PAT = re.compile(
    r'"id":(?P<id>\d+),"first_name":(?P<first>(?:null|"[^"]*"))'
    r',"middle_initials":(?P<mid>(?:null|"[^"]*"))'
    r',"last_name":(?P<last>(?:null|"[^"]*"))'
    r',"page_name":"(?P<page>[^"]*)"'
    r',"domain_name":"(?P<domain>[^"]*)"'
    r',"created_at":"(?P<created>[^"]*)"'
    r',"display_name":"(?P<disp>[^"]*)"'
    r',"url":"(?P<url>[^"]*)"'
    r',"photo":"(?P<photo>[^"]*)"'
    r',"has_photo":(?P<haspho>true|false)'
    r',"department":\{"id":(?P<deptid>\d+),"name":"(?P<deptname>[^"]*)","url":"(?P<depturl>[^"]*)"'
    r',"university":\{"id":(?P<univid>\d+),"name":"(?P<univname>[^"]*)"'
)
_META_DESC_PAT = re.compile(r'<meta\s+name="description"\s+content="([^"]+)"')
_FOLLOWERS_PAT = re.compile(r'(\d+)\s+Followers?')
_FOLLOWING_PAT = re.compile(r'(\d+)\s+Following')
_PAPERS_PAT = re.compile(r'(\d+)\s+(?:Research papers?|papers?)')


def _unjson_or_none(s: str) -> Optional[str]:
    if s == "null":
        return None
    return json.loads(s)


def parse_profile_html(html_text: str) -> Optional[dict]:
    m = _PROFILE_JSON_PAT.search(html_text)
    if not m:
        return None
    row: dict = {
        "user_id": int(m.group("id")),
        "first_name": _unjson_or_none(m.group("first")),
        "middle_initials": _unjson_or_none(m.group("mid")),
        "last_name": _unjson_or_none(m.group("last")),
        "page_name": m.group("page"),
        "subdomain": m.group("domain"),
        "created_at": m.group("created"),
        "display_name": json.loads(f'"{m.group("disp")}"') if "\\" in m.group("disp") else m.group("disp"),
        "profile_url": m.group("url"),
        "photo_url": m.group("photo"),
        "has_photo": m.group("haspho") == "true",
        "department_id": int(m.group("deptid")),
        "department_name": m.group("deptname"),
        "department_url": m.group("depturl"),
        "university_id": int(m.group("univid")),
        "university_name": m.group("univname"),
    }
    md = _META_DESC_PAT.search(html_text)
    desc = md.group(1) if md else ""
    fm = _FOLLOWERS_PAT.search(desc)
    fg = _FOLLOWING_PAT.search(desc)
    pp = _PAPERS_PAT.search(desc)
    row["followers_count"] = int(fm.group(1)) if fm else None
    row["following_count"] = int(fg.group(1)) if fg else None
    row["papers_count"] = int(pp.group(1)) if pp else None
    return row


# --- Per-user API calls ---
async def fetch_user_details(session, subdomain, uid):
    url = f"https://{subdomain}.academia.edu/v0/users/{uid}/details?subdomain_param=api"
    body = await fetch(session, url, subdomain)
    if not body:
        return {}
    try:
        d = (json.loads(body) or {}).get("details", {}) or {}
        return {"about": d.get("about") or "", "public_email": d.get("public_email") or ""}
    except Exception as e:
        log.debug("details parse err %d: %s", uid, e)
        return {}


async def fetch_user_rank(session, subdomain, uid):
    url = f"https://{subdomain}.academia.edu/v0/certifications/ranks/author_ranks/{uid}?subdomain_param=api"
    body = await fetch(session, url, subdomain)
    if not body:
        return {}
    try:
        d = json.loads(body) or {}
        return {"author_rank": d.get("value"), "bragworthy": d.get("bragworthy")}
    except Exception as e:
        log.debug("rank parse err %d: %s", uid, e)
        return {}


# --- CSV IO (crash-safe: write + fsync under lock, then update memo) ---
def open_csv_writer():
    """Open csv for append. Writes header if file is new/empty. Sync IO, fsync'd."""
    global csv_fh, csv_writer
    new_file = (not OUT_CSV.exists()) or OUT_CSV.stat().st_size == 0
    csv_fh = open(OUT_CSV, "a", encoding="utf-8", newline="")
    csv_writer = csvlib.DictWriter(csv_fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
    if new_file:
        csv_writer.writeheader()
        csv_fh.flush()
        os.fsync(csv_fh.fileno())


def close_csv_writer():
    global csv_fh
    if csv_fh is not None:
        try:
            csv_fh.flush()
            os.fsync(csv_fh.fileno())
        except Exception:
            pass
        try:
            csv_fh.close()
        except Exception:
            pass
        csv_fh = None


async def write_row(row: dict):
    row = dict(row)  # don't mutate caller
    row["scraped_at"] = datetime.now(timezone.utc).isoformat()
    async with csv_lock:
        # csv.DictWriter handles quoting / unicode correctly. Run in default executor
        # so the fsync doesn't stall the event loop on slow disks.
        def _do_write():
            csv_writer.writerow(row)
            csv_fh.flush()
            os.fsync(csv_fh.fileno())
        await asyncio.get_running_loop().run_in_executor(None, _do_write)


# --- Recovery: rebuild done_user_ids from the CSV itself ---
def recover_done_state() -> tuple:
    """Returns (done_user_ids, seen_profile_urls). CSV is the source of truth."""
    if not OUT_CSV.exists():
        return set(), set()
    ids: set = set()
    urls: set = set()
    bad = 0
    try:
        with open(OUT_CSV, "r", encoding="utf-8", newline="") as f:
            reader = csvlib.DictReader(f)
            for row in reader:
                v = row.get("user_id", "")
                try:
                    ids.add(int(v))
                except (TypeError, ValueError):
                    bad += 1
                u = row.get("profile_url", "")
                if u:
                    urls.add(u)
    except Exception as e:
        log.error("CSV recovery failed: %s — starting from scratch", e)
        return set(), set()
    if bad:
        log.warning("CSV recovery: skipped %d unparseable rows", bad)
    return ids, urls


# --- Crawl workers ---
async def process_profile(session: AsyncSession, profile_url: str, subdomain: str) -> bool:
    if stop_event is not None and stop_event.is_set():
        return False
    # Short-circuit: if we've written this URL before, skip the fetch entirely.
    if profile_url in seen_profile_urls:
        return False
    html_text = await fetch(session, profile_url, subdomain)
    if not html_text:
        return False
    parsed = parse_profile_html(html_text)
    if not parsed:
        return False
    uid = parsed["user_id"]
    if uid in done_user_ids:
        seen_profile_urls.add(profile_url)  # record so next resume skips it
        return False
    det, rank = await asyncio.gather(
        fetch_user_details(session, subdomain, uid),
        fetch_user_rank(session, subdomain, uid),
    )
    row = {**parsed, **det, **rank}
    await write_row(row)
    done_user_ids.add(uid)  # only after the fsync'd CSV write
    seen_profile_urls.add(profile_url)
    n = len(done_user_ids)
    if n % 100 == 0:
        log.info("Progress: %d users in CSV (last: %s)", n, parsed.get("display_name"))
    return True


async def crawl_department(session: AsyncSession, dept_url: str, subdomain: str) -> set:
    seen: set = set()
    for page in range(1, MAX_DEPT_PAGES + 1):
        if stop_event is not None and stop_event.is_set():
            break
        url = dept_url if page == 1 else f"{dept_url}?page={page}"
        body = await fetch(session, url, subdomain)
        if not body:
            break
        new = discover_profile_urls(body, subdomain) - seen
        if not new and page > 1:
            break
        seen |= new
    return seen


async def crawl_subdomain(session: AsyncSession, subdomain: str) -> int:
    if stop_event is not None and stop_event.is_set():
        return 0
    log.info("[%s] homepage", subdomain)
    body = await fetch(session, f"https://{subdomain}.academia.edu/", subdomain)
    if not body:
        log.warning("[%s] homepage unreachable", subdomain)
        return 0
    depts = discover_department_urls(body, subdomain)
    log.info("[%s] %d departments", subdomain, len(depts))
    if not depts:
        return 0

    dept_tasks = [crawl_department(session, d, subdomain) for d in depts]
    dept_results = await asyncio.gather(*dept_tasks, return_exceptions=True)

    profile_urls: set = set()
    for d, res in zip(depts, dept_results):
        if isinstance(res, Exception):
            log.warning("[%s] dept failed %s: %s", subdomain, d, res)
            continue
        profile_urls |= res
    log.info("[%s] %d unique profile URLs", subdomain, len(profile_urls))

    prof_tasks = [process_profile(session, p, subdomain) for p in profile_urls]
    results = await asyncio.gather(*prof_tasks, return_exceptions=True)
    written = sum(1 for r in results if r is True)
    log.info("[%s] %d new users written", subdomain, written)
    return written


async def discover_universities(http: aiohttp.ClientSession, curl: AsyncSession) -> set:
    body: Optional[str] = None
    try:
        async with http.get(
            "https://www.academia.edu/",
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/148.0.0.0 Safari/537.36"
                )
            },
        ) as r:
            if r.status == 200 and r.content_length and r.content_length > 20000:
                body = await r.text()
    except Exception as e:
        log.info("aiohttp seed failed (%s); falling back to curl_cffi", e)
    if not body:
        body = await fetch(curl, "https://www.academia.edu/", "www.academia.edu")
    subs = discover_subdomains(body or "")
    log.info("Discovered %d university subdomains", len(subs))
    return subs


# --- Entrypoint ---
async def main():
    global global_sem, stop_event, done_user_ids, seen_profile_urls
    global_sem = asyncio.Semaphore(GLOBAL_CONCURRENCY)
    stop_event = asyncio.Event()

    done_user_ids, seen_profile_urls = recover_done_state()
    log.info("Recovered %d user_ids and %d profile URLs from CSV",
             len(done_user_ids), len(seen_profile_urls))
    open_csv_writer()

    loop = asyncio.get_running_loop()

    def _sigint():
        if stop_event.is_set():
            log.error("Second signal received; hard-exiting")
            close_csv_writer()
            os._exit(130)
        log.warning("Signal received; stopping after in-flight requests (Ctrl-C again to force-quit)")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _sigint)
        except NotImplementedError:
            pass

    try:
        async with AsyncSession() as curl, aiohttp.ClientSession() as http:
            subs = await discover_universities(http, curl)
            if not subs:
                log.error("No subdomains discovered, aborting"); return

            sub_sem = asyncio.Semaphore(SUBDOMAIN_CONCURRENCY)

            async def _crawl_one(s: str) -> int:
                async with sub_sem:
                    if stop_event.is_set():
                        return 0
                    try:
                        return await crawl_subdomain(curl, s)
                    except Exception:
                        log.exception("[%s] crawl failed", s)
                        return 0

            results = await asyncio.gather(
                *(_crawl_one(s) for s in sorted(subs)),
                return_exceptions=False,
            )
            total = sum(results)
            log.info("DONE. %d new users scraped this run. CSV total: %d. Path: %s",
                     total, len(done_user_ids), OUT_CSV)
    finally:
        close_csv_writer()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.warning("Interrupted by user")
