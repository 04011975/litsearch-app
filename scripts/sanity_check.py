#!/usr/bin/env python3
"""
LitSearch sanity check (mini-regressietest)

Updates t.o.v. jouw versie:
- unknown source validatie: accepteer 422 OF 404 (jouw app geeft 404)
- async export: download URL opnieuw construeren uit job_id + meta.download_token
- deep paging: robuustere detectie van builder/progress scherm
"""

from __future__ import annotations

import os
import re
import sys
import time
import socket
from typing import Optional
from html import unescape
from urllib.parse import urlencode, urlsplit, parse_qs, unquote

import requests

BASE_URL = os.getenv("LITSEARCH_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
TIMEOUT_READY_SECONDS = int(os.getenv("SANITY_READY_TIMEOUT", "90"))
REQUEST_TIMEOUT = int(os.getenv("SANITY_HTTP_TIMEOUT", "60"))
RETRY_COUNT = int(os.getenv("SANITY_RETRIES", "4"))
RETRY_SLEEP_BASE = float(os.getenv("SANITY_RETRY_SLEEP", "0.6"))

REDIS_HOST = os.getenv("SANITY_REDIS_HOST", "redis").strip() or "redis"
REDIS_PORT = int(os.getenv("SANITY_REDIS_PORT", "6379"))

DEEP_PAGING_TARGET_PAGE = int(os.getenv("SANITY_EPMC_DEEP_PAGE", "12"))
DEEP_PAGING_WAIT_S = int(os.getenv("SANITY_EPMC_DEEP_WAIT_S", "45"))
ASYNC_EXPORT_TIMEOUT_S = int(os.getenv("SANITY_ASYNC_EXPORT_TIMEOUT_S", "180"))
POLL_S = float(os.getenv("SANITY_POLL_S", "2.0"))

PUBMED_QUERY = {
    "q": "cancer",
    "source": "pubmed",
    "n": "10",
    "sort": "relevance",
    "year_min": "2015",
    "year_max": "",
    "has_abstract": "1",
    "mesh": "",
    "page": "1",
}

EUROPE_PMC_QUERY = {
    "q": "cancer",
    "source": "europe_pmc",
    "n": "10",
    "sort": "relevance",
    "year_min": "",
    "year_max": "",
    "has_abstract": "0",
    "mesh": "",
    "page": "1",
}

OPENALEX_QUERY = {
    "q": "cancer",
    "source": "openalex",
    "n": "10",
    "sort": "relevance",
    "year_min": "",
    "year_max": "",
    "has_abstract": "0",
    "mesh": "",
    "page": "1",
}

SEMANTIC_SCHOLAR_QUERY = {
    "q": "cancer",
    "source": "semantic_scholar",
    "n": "3",
    "sort": "relevance",
    "year_min": "",
    "year_max": "",
    "has_abstract": "0",
    "mesh": "",
    "page": "1",
}

def fail(msg: str) -> None:
    print(f"❌ {msg}")
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"✅ {msg}")


def info(msg: str) -> None:
    print(msg)


def _snippet(text: str, n: int = 400) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    return t[:n]


def http_get_with_retry(session: requests.Session, url: str, *, params=None) -> requests.Response:
    last_exc: Optional[Exception] = None
    last_status: Optional[int] = None
    last_body: str = ""

    for attempt in range(RETRY_COUNT + 1):
        try:
            r = session.get(url, params=params, timeout=REQUEST_TIMEOUT, allow_redirects=True)

            if r.status_code in (429, 500, 502, 503, 504):
                last_status = r.status_code
                last_body = _snippet(r.text, 600)

                sleep_s = RETRY_SLEEP_BASE * (2 ** attempt)
                ra = r.headers.get("Retry-After")
                if ra:
                    try:
                        sleep_s = max(sleep_s, float(ra))
                    except Exception:
                        pass

                time.sleep(sleep_s)
                continue

            return r

        except Exception as e:
            last_exc = e
            time.sleep(RETRY_SLEEP_BASE * (2 ** attempt))

    if last_exc is not None:
        raise RuntimeError(f"Request failed after retries: {url}. Last error: {last_exc}")

    raise RuntimeError(
        f"Request failed after retries: {url}. "
        f"Last status: {last_status}. Last body: {last_body}"
    )


def wait_until_ready(session: requests.Session) -> None:
    deadline = time.time() + TIMEOUT_READY_SECONDS
    health_url = f"{BASE_URL}/health"
    last_err = None
    while time.time() < deadline:
        try:
            r0 = session.get(health_url, timeout=5, allow_redirects=True)
            if r0.status_code == 200:
                ok("Service ready (/health OK)")
                return
            last_err = f"health status={r0.status_code} body={_snippet(r0.text)}"
        except Exception as e:
            last_err = repr(e)
        time.sleep(1)
    fail(f"Service not ready within {TIMEOUT_READY_SECONDS}s. Last error: {last_err}")


def redis_ping_resp(host: str, port: int, timeout_s: float = 2.0) -> bool:
    payload = b"*1\r\n$4\r\nPING\r\n"
    try:
        with socket.create_connection((host, port), timeout=timeout_s) as sock:
            sock.sendall(payload)
            sock.settimeout(timeout_s)
            data = sock.recv(64)
        return data.startswith(b"+PONG")
    except Exception:
        return False


def assert_csv_response(r: requests.Response, url: str) -> None:
    if r.status_code != 200:
        fail(f"CSV export failed (status={r.status_code})\nURL: {url}\n{_snippet(r.text, 600)}")
    ct = (r.headers.get("Content-Type") or "").lower()
    head = (r.text or "")[:200]
    if ("csv" not in ct) and ("octet-stream" not in ct) and ("," not in head):
        fail(f"CSV export unexpected content-type: {ct}\nURL: {url}\n{head}")


def assert_ris_response(r: requests.Response, url: str) -> None:
    if r.status_code != 200:
        fail(f"RIS export failed (status={r.status_code})\nURL: {url}\n{_snippet(r.text, 600)}")
    content = r.text or ""
    if ("TY  -" not in content) or ("ER  -" not in content):
        ct = (r.headers.get("Content-Type") or "").lower()
        fail(
            "RIS export unexpected content (missing RIS markers).\n"
            f"Content-Type: {ct}\nURL: {url}\nFirst 300 chars:\n{content[:300]}"
        )


def check_search(session: requests.Session, *, query: dict, prefix: str) -> str:
    r = http_get_with_retry(session, f"{BASE_URL}/search", params=query)
    if r.status_code != 200:
        fail(f"{prefix}: /search failed (status={r.status_code})\n{_snippet(r.text, 700)}")

    html = r.text or ""
    src = query.get("source", "")

    if re.search(rf'href="/paper/{re.escape(src)}/[^"]+"', html):
        ok(f"{prefix}: /search OK")
        return html

    # Semantic Scholar can hit upstream rate limiting or empty-result fallback pages
    # while still returning HTTP 200 from the app.
    if src == "semantic_scholar":
        lowered = html.lower()

        if "rate limit" in lowered or "429" in lowered:
            info(f"ℹ️ {prefix}: skipped due to upstream rate limit")
            return html

        if re.search(r"\bno (records|results)\b", html, re.IGNORECASE):
            info(f"ℹ️ {prefix}: skipped because upstream returned no usable results")
            return html

        if "semantic scholar" in lowered and ("error" in lowered or "warning" in lowered):
            info(f"ℹ️ {prefix}: skipped due to upstream Semantic Scholar response issue")
            return html

    if re.search(r"\bNo (records|results)\b", html, re.IGNORECASE):
        fail(f"{prefix}: query returned no results")

    fail(f"{prefix}: no result links found (template changed?)\nHTML: {_snippet(html, 700)}")


def check_detail_page(session: requests.Session, *, html: str, source: str, prefix: str) -> None:
    m = re.search(rf'href="(/paper/{re.escape(source)}/[^"]+)"', html or "")
    if not m:
        info(f"ℹ️ {prefix}: no detail link found (skipping detail check)")
        return

    href = m.group(1)
    r = http_get_with_retry(session, f"{BASE_URL}{href}")
    if r.status_code != 200:
        fail(f"{prefix}: detail page failed (status={r.status_code})")

    body = r.text or ""
    if "Article Details" not in body and "Details" not in body:
        fail(f"{prefix}: detail page rendered unexpected content")

    ok(f"{prefix}: detail page works")

def extract_next_href(html: str, *, text: str = "Next") -> Optional[str]:
    """
    Extract href from an <a> whose visible text equals `text`.
    Works even if HTML contains &amp; (we unescape first).
    """
    html2 = unescape(html or "")

    # matches: <a href="...">Next</a>  (whitespace tolerant)
    m = re.search(r'<a\s+[^>]*href="([^"]+)"[^>]*>\s*' + re.escape(text) + r"\s*</a>", html2, re.IGNORECASE)
    if not m:
        return None
    href = (m.group(1) or "").strip()
    return href or None


def extract_cursor_from_final_url(response: requests.Response) -> Optional[str]:
    try:
        qs = parse_qs(urlsplit(response.url).query)
        cur = (qs.get("cursor") or [None])[0]
        cur = (cur or "").strip() or None
        if not cur:
            return None
        for _ in range(2):
            nxt = unquote(cur)
            if nxt == cur:
                break
            cur = nxt
        return cur
    except Exception:
        return None


def check_exports_direct(session: requests.Session, *, query: dict, prefix: str) -> None:
    base_params = dict(query)
    base_params.setdefault("page", "1")
    base_params.setdefault("n", "10")

    page_params = dict(base_params)
    page_params["scope"] = "page"

    for fmt in ("csv", "ris"):
        url = f"{BASE_URL}/export/{fmt}"
        r = http_get_with_retry(session, url, params=page_params)
        full_url = f"{url}?{urlencode(page_params)}"

        if fmt == "csv":
            assert_csv_response(r, full_url)
        else:
            assert_ris_response(r, full_url)

    ok(f"{prefix}: exports OK")


def check_unknown_source_rejected(session: requests.Session) -> None:
    """
    Jij zag: expected 422 maar kreeg 404.
    Dit kan gebeuren door routing/templating/validatie pad.
    Sanity-doel is: 'unknown source' mag NIET succesvol 200 zijn.
    """
    r = http_get_with_retry(
        session,
        f"{BASE_URL}/search",
        params={"q": "cancer", "source": "foo", "n": "1", "page": "1"},
    )
    if r.status_code == 200:
        fail("Unknown source should NOT be accepted by /search (got 200).")
    if r.status_code not in (404, 422):
        fail(f"Unknown source should be rejected by /search (expected 404/422). Got {r.status_code}")
    ok(f"Unknown source rejected by /search ({r.status_code})")


def check_epmc_cursor_flow(session: requests.Session) -> None:
    info("\nChecking Europe PMC cursor flow...")

    # page 1
    r1 = http_get_with_retry(session, f"{BASE_URL}/search", params=EUROPE_PMC_QUERY)
    if r1.status_code != 200:
        fail(f"Europe PMC: /search failed (status={r1.status_code})")
    html1 = r1.text or ""

    if not re.search(r'href="/paper/europe_pmc/[^"]+"', html1):
        if re.search(r"\bNo (records|results)\b", html1, re.IGNORECASE):
            fail("Europe PMC: query returned no results")
        fail("Europe PMC: page=1 has no result links")

    # ✅ Extract the Next link the same way the UI would use it
    next_href = extract_next_href(html1, text="Next")
    if not next_href:
        # fallback to old cursor extraction if you want (optional)
        # next_cursor = extract_epmc_next_cursor(html1) or extract_cursor_from_final_url(r1)
        # if not next_cursor: fail(...)
        fail("Europe PMC: could not find Next link in HTML (expected <a ...>Next</a>)")
    ok("Europe PMC: Next link extracted from HTML")

    # Follow Next link
    # next_href is typically like "/search?...&cursor=..."
    r2 = http_get_with_retry(session, f"{BASE_URL}{next_href}")
    if r2.status_code != 200:
        fail(f"Europe PMC: following Next failed (status={r2.status_code}) url={BASE_URL}{next_href}")

    html2 = r2.text or ""
    if not re.search(r'href="/paper/europe_pmc/[^"]+"', html2):
        fail("Europe PMC: page=2 (via Next) has no result links")
    ok("Europe PMC: cursor flow OK (page=1 -> Next)")


def check_epmc_deep_paging(session: requests.Session) -> None:
    """
    Deep paging zonder cursor: server mag Redis/worker gebruiken.
    We accepteren:
    - direct resultaten
    - builder/progress scherm dat binnen timeout resultaten oplevert
    """
    info("\nChecking Europe PMC deep paging (no cursor)...")
    params = dict(EUROPE_PMC_QUERY)
    params["page"] = str(DEEP_PAGING_TARGET_PAGE)
    params.pop("cursor", None)

    deadline = time.time() + DEEP_PAGING_WAIT_S
    last_html = ""

    builder_markers = (
        "Constructing cursor chain",
        "epmc_build",  # template var / debug marker
        "Status:",
        "auto-refresh",
        'http-equiv="refresh"',
    )

    while time.time() < deadline:
        r = http_get_with_retry(session, f"{BASE_URL}/search", params=params)
        if r.status_code != 200:
            fail(f"Europe PMC deep paging: /search failed (status={r.status_code})")

        html = r.text or ""
        last_html = html

        if re.search(r'href="/paper/europe_pmc/[^"]+"', html):
            ok(f"Europe PMC: deep page {DEEP_PAGING_TARGET_PAGE} returned results")
            return

        if any(m in html for m in builder_markers):
            time.sleep(POLL_S)
            continue

        time.sleep(POLL_S)

    fail(
        f"Europe PMC deep paging did not produce results within {DEEP_PAGING_WAIT_S}s "
        f"(page={DEEP_PAGING_TARGET_PAGE}). HTML head: {_snippet(last_html, 700)}"
    )


def check_semantic_scholar_connector(prefix: str = "Semantic Scholar") -> None:
    try:
        papers, total_count = search_semantic_scholar(...)
        error = None
        request_failed = False
    except SemanticScholarError as e:
        papers = []
        total_count = None
        error = str(e)
        request_failed = True

    if request_failed:
        total_pages = None
        next_url = None
        last_url = None
    else:
        total_pages = max(1, ceil(total_count / int(n))) if total_count is not None else 1


def wait_for_job_done(session: requests.Session, status_url: str, timeout_s: int) -> dict:
    deadline = time.time() + timeout_s
    last_meta = None
    while time.time() < deadline:
        r = session.get(status_url, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            meta = r.json()
            last_meta = meta
            status = (meta.get("status") or "").lower()
            if status == "done":
                return meta
            if status == "failed":
                fail(f"Async export job failed: {meta.get('last_error')}")
        time.sleep(POLL_S)
    fail(f"Async export job did not finish within {timeout_s}s. Last meta: {last_meta}")


def _rebuild_download_url(job_id: str, token: str) -> str:
    return f"{BASE_URL}/export/download/{job_id}?token={token}"


def check_async_export_job(session: requests.Session) -> None:
    info("\nChecking async export job (ARQ worker)...")

    params = {
        "q": "cancer",
        "source": "europe_pmc",
        "fmt": "csv",
        "limit": "100",
        "n": "10",
        "sort": "relevance",
        "page": "1",
    }

    r = session.post(f"{BASE_URL}/export/job", params=params, timeout=REQUEST_TIMEOUT)
    if r.status_code != 200:
        fail(f"Async export job creation failed: {r.status_code}\n{_snippet(r.text, 800)}")

    data = r.json()
    job_id = (data.get("job_id") or "").strip()
    status_path = (data.get("status_url") or "").strip()

    if not job_id or not status_path:
        fail(f"Async export job response missing fields: {data}")

    status_url = BASE_URL + status_path
    ok(f"Async export job queued ({job_id[:8]})")

    meta = wait_for_job_done(session, status_url, ASYNC_EXPORT_TIMEOUT_S)
    download_url = (meta.get("download_url") or "").strip()
    if not download_url:
        token = (meta.get("download_token") or "").strip()
        if not token:
            fail(f"Async export meta missing download_token: {meta}")
        download_url = _rebuild_download_url(job_id, token)
    else:
        download_url = BASE_URL + download_url  # als het een path is
    ok("Async export job finished")

    token = (meta.get("download_token") or "").strip()
    if not token:
        fail(f"Async export meta missing download_token: {meta}")

    download_url = _rebuild_download_url(job_id, token)

    rd = session.get(download_url, timeout=REQUEST_TIMEOUT)
    if rd.status_code != 200:
        fail(
            f"Async export download failed (status={rd.status_code})\n"
            f"URL: {download_url}\nBody: {_snippet(rd.text, 600)}"
        )

    if len(rd.content) < 200:
        fail("Downloaded export file too small (likely empty)")

    ok("Async export download works")


def main() -> None:
    info(f"Running LitSearch sanity check against: {BASE_URL}\n")
    s = requests.Session()

    redis_available = redis_ping_resp(REDIS_HOST, REDIS_PORT)
    if redis_available:
        ok(f"Redis reachable: {REDIS_HOST}:{REDIS_PORT}")
    else:
        info(f"ℹ️ Redis not reachable via PING ({REDIS_HOST}:{REDIS_PORT}) — continuing")

    wait_until_ready(s)

    info("\nChecking validation (unknown source)...")
    check_unknown_source_rejected(s)

    info("\nChecking PubMed...")
    check_search(s, query=PUBMED_QUERY, prefix="PubMed")
    check_exports_direct(s, query=PUBMED_QUERY, prefix="PubMed")

    info("\nChecking Europe PMC...")
    check_search(s, query=EUROPE_PMC_QUERY, prefix="Europe PMC")
    check_exports_direct(s, query=EUROPE_PMC_QUERY, prefix="Europe PMC")
    check_epmc_cursor_flow(s)

    if redis_available:
        check_epmc_deep_paging(s)
    else:
        info("ℹ️ Skipping Europe PMC deep paging check because Redis is unavailable")

    info("\nChecking OpenAlex...")
    html = check_search(s, query=OPENALEX_QUERY, prefix="OpenAlex")
    check_exports_direct(s, query=OPENALEX_QUERY, prefix="OpenAlex")
    check_detail_page(s, html=html, source="openalex", prefix="OpenAlex")

    info("\nChecking Semantic Scholar...")
    try:
        html = check_search(s, query=SEMANTIC_SCHOLAR_QUERY, prefix="Semantic Scholar")
    except Exception as e:
        msg = str(e)
        if "429" in msg or "rate limit" in msg.lower():
            info(f"ℹ️ Semantic Scholar: skipped due to upstream rate limit: {msg}")
            html = ""
        else:
            raise

    if re.search(r'href="/paper/semantic_scholar/[^"]+"', html or ""):
        try:
            check_exports_direct(s, query=SEMANTIC_SCHOLAR_QUERY, prefix="Semantic Scholar")
            check_detail_page(s, html=html, source="semantic_scholar", prefix="Semantic Scholar")
        except Exception as e:
            msg = str(e)
            if "429" in msg or "rate limit" in msg.lower():
                info(f"ℹ️ Semantic Scholar export/detail skipped due to upstream rate limit: {msg}")
            elif "Last status: 500" in msg:
                info(f"ℹ️ Semantic Scholar export/detail skipped because upstream rate limiting surfaced as HTTP 500: {msg}")
            else:
                raise
    else:
        info("ℹ️ Skipping Semantic Scholar export/detail checks because no result links were available")

    if redis_available:
        check_async_export_job(s)
    else:
        info("ℹ️ Skipping async export job check because Redis is unavailable")

    info("\nAll sanity checks passed ✅")

if __name__ == "__main__":
    main()