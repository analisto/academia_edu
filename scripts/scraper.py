#!/usr/bin/env python3
"""
academia.edu full-scale scraper.

Pipeline:
  1. Seed: scrape https://www.academia.edu/ -> university subdomains.
  2. Per subdomain: scrape https://{sub}.academia.edu/ -> /Departments/{Name} URLs.
  3. Per department: paginate -> profile URLs.
  4. Per profile: parse embedded JSON (user_id, dept, university, photo, dates)
                  and <meta name="description"> (followers/following/papers counters).
  5. Per user_id: GET /v0/users/{id}/details + /v0/certifications/ranks/author_ranks/{id}.
  6. Append a row to data/data.csv (streaming, resumable via data/checkpoint.json).

Stack: asyncio + curl_cffi.AsyncSession (Cloudflare bypass via Chrome TLS impersonation)
       + aiohttp (used for the first seed fetch; falls back to curl_cffi if blocked)
       + aiofiles (non-blocking CSV writes).

Run:   python3 scripts/scraper.py
Resume on re-run: profiles already in checkpoint.json are skipped.
"""

import asyncio
import json
import logging
import re
import signal
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiofiles
import aiohttp
from curl_cffi.requests import AsyncSession

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUT_CSV = DATA_DIR / "data.csv"
CHECKPOINT = DATA_DIR / "checkpoint.json"
LOG_FILE = DATA_DIR / "scraper.log"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# --- Tunables ---
GLOBAL_CONCURRENCY = 30
PER_HOST_CONCURRENCY = 4
MAX_DEPT_PAGES = 50
RETRY_LIMIT = 4
RETRY_BASE_DELAY = 2.0
REQUEST_TIMEOUT = 30
IMPERSONATE = "chrome"
CHECKPOINT_EVERY = 25

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

# --- Shared state ---
done_user_ids: set[int] = set()
csv_lock = asyncio.Lock()
ckpt_lock = asyncio.Lock()
global_sem: Optional[asyncio.Semaphore] = None
host_sems: dict[str, asyncio.Semaphore] = {}


def _host_sem(host: str) -> asyncio.Semaphore:
    sem = host_sems.get(host)
    if sem is None:
        sem = host_sems[host] = asyncio.Semaphore(PER_HOST_CONCURRENCY)
    return sem


# --- HTTP ---
async def fetch(session: AsyncSession, url: str, host: str) -> Optional[str]:
    """GET with retry/backoff. Returns body text or None."""
    assert global_sem is not None
    async with global_sem, _host_sem(host):
        for attempt in range(RETRY_LIMIT):
            try:
                r = await session.get(url, impersonate=IMPERSONATE, timeout=REQUEST_TIMEOUT)
                if r.status_code == 200:
                    return r.text
                if r.status_code in (404, 403, 410):
                    return None
                log.warning("HTTP %d %s (attempt %d/%d)", r.status_code, url, attempt + 1, RETRY_LIMIT)
            except Exception as e:
                log.warning("ERR %s: %s (attempt %d/%d)", url, e, attempt + 1, RETRY_LIMIT)
            await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))
        return None


# --- Discovery parsers ---
_SUB_PAT = re.compile(r'https?://([a-z0-9][a-z0-9\-]+)\.academia\.edu')
_EXCLUDE_SUBS = {"www", "a", "0", "support", "static", "s3", "m"}


def discover_subdomains(html_text: str) -> set[str]:
    subs = set(_SUB_PAT.findall(html_text or "")) - _EXCLUDE_SUBS
    return {s for s in subs if not s.startswith(("academia-",))}


def discover_department_urls(html_text: str, subdomain: str) -> set[str]:
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


def discover_profile_urls(html_text: str, subdomain: str) -> set[str]:
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
        # crude length sanity-check (profile slugs are typically >2 chars)
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


# --- IO ---
async def write_row(row: dict):
    row["scraped_at"] = datetime.now(timezone.utc).isoformat()
    async with csv_lock:
        new_file = not OUT_CSV.exists()
        async with aiofiles.open(OUT_CSV, "a", encoding="utf-8", newline="") as f:
            if new_file:
                await f.write(",".join(CSV_FIELDS) + "\n")
            cells = []
            for k in CSV_FIELDS:
                v = row.get(k, "")
                if v is None:
                    v = ""
                s = str(v).replace('"', '""').replace("\r", " ").replace("\n", " ")
                if any(c in s for c in ',"'):
                    s = f'"{s}"'
                cells.append(s)
            await f.write(",".join(cells) + "\n")


async def save_checkpoint():
    async with ckpt_lock:
        async with aiofiles.open(CHECKPOINT, "w", encoding="utf-8") as f:
            await f.write(json.dumps({"user_ids": sorted(done_user_ids)}))


def load_checkpoint():
    global done_user_ids
    if CHECKPOINT.exists():
        try:
            with open(CHECKPOINT, "r", encoding="utf-8") as f:
                done_user_ids = set(json.load(f).get("user_ids", []))
        except Exception:
            done_user_ids = set()
    log.info("Checkpoint: %d user_ids already scraped", len(done_user_ids))


# --- Crawl workers ---
async def process_profile(session: AsyncSession, profile_url: str, subdomain: str) -> bool:
    html_text = await fetch(session, profile_url, subdomain)
    if not html_text:
        return False
    parsed = parse_profile_html(html_text)
    if not parsed:
        return False
    uid = parsed["user_id"]
    if uid in done_user_ids:
        return False
    det, rank = await asyncio.gather(
        fetch_user_details(session, subdomain, uid),
        fetch_user_rank(session, subdomain, uid),
    )
    row = {**parsed, **det, **rank}
    await write_row(row)
    done_user_ids.add(uid)
    if len(done_user_ids) % CHECKPOINT_EVERY == 0:
        await save_checkpoint()
        log.info("Progress: %d users in CSV (last: %s)", len(done_user_ids), parsed.get("display_name"))
    return True


async def crawl_department(session: AsyncSession, dept_url: str, subdomain: str) -> set[str]:
    seen: set[str] = set()
    for page in range(1, MAX_DEPT_PAGES + 1):
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

    profile_urls: set[str] = set()
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
    await save_checkpoint()
    return written


async def discover_universities(http: aiohttp.ClientSession, curl: AsyncSession) -> set[str]:
    body: Optional[str] = None
    # Try aiohttp first (cheap and meets "use aiohttp" requirement); fall back to curl_cffi on Cloudflare.
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
    global global_sem
    global_sem = asyncio.Semaphore(GLOBAL_CONCURRENCY)
    load_checkpoint()

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    async with AsyncSession() as curl, aiohttp.ClientSession() as http:
        subs = await discover_universities(http, curl)
        if not subs:
            log.error("No subdomains discovered, aborting"); return

        total = 0
        for s in sorted(subs):
            if stop.is_set():
                log.warning("Stop signal received, saving checkpoint and exiting")
                break
            try:
                total += await crawl_subdomain(curl, s)
            except Exception:
                log.exception("[%s] crawl failed", s)
        log.info("DONE. %d new users scraped this run. CSV: %s", total, OUT_CSV)
    await save_checkpoint()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.warning("Interrupted by user")
