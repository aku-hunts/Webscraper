#!/usr/bin/env python3
"""
super_scraper.py
=================

A free, production-grade, asynchronous documentation scraper built on
asyncio + Playwright. It crawls the official Roblox Creator Documentation
(create.roblox.com/docs) and the Luau language documentation
(luau-lang.org), strips navigation/UI chrome from every page, and writes
the result into a single, delimited plaintext corpus suitable for feeding
to an LLM.

ENGINEERING NOTE -- a discovered optimization
----------------------------------------------
While building this, it turned out that Roblox's Creator Documentation
publishes a clean Markdown copy of every single page at that page's own
URL with ".md" appended (e.g. .../docs/en-us/luau.md), plus a curated
"/docs/llms.txt" index -- a mechanism the docs explicitly describe as
being for AI/code agents. That Markdown is smaller, has zero navigation
noise, and is the actual source content rather than a heuristic
reconstruction of it, so this scraper always tries "<url>.md" first via
a lightweight HTTP call and only falls back to full browser rendering
(the heavy Playwright path this script was originally specified around)
when that fails -- which is always, for sites like luau-lang.org that
don't publish such a file. No site is hard-coded to one path or the
other: every URL is tried the fast way first and gracefully degrades to
full rendering, so the same script is correct for both targets.

Both target domains are documentation intended for public/developer
consumption, and the crawl is deliberately restricted to their /docs
paths only. Roblox's own robots.txt (checked and honored below) disallows
only /dashboard/ and /talent/, not /docs. Roblox's broader Terms of Use
do restrict automated collection elsewhere on the platform (its
catalogue, user profiles, game listings, etc.) -- this script never goes
near any of that; if you repurpose it for other parts of roblox.com,
review those terms yourself first.

SETUP
-----
    pip install playwright
    playwright install chromium

RUN
---
    python super_scraper.py

OUTPUT
------
    roblox_knowledge_base.txt  -- the assembled corpus
    scraping_errors.log        -- full tracebacks for any URL that
                                   failed after all retries
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

# ============================================================================
# CONFIGURATION -- tune these, nothing else needs to change
# ============================================================================

SEED_URLS = [
    "https://create.roblox.com/docs",
    "https://luau-lang.org/",
]

ALLOWED_DOMAINS = {
    "create.roblox.com",
    "luau-lang.org",
}

# Keep the crawl inside documentation paths only -- never the Roblox
# store, dashboard, community, or login surfaces.
ALLOWED_PATH_PREFIXES = {
    "create.roblox.com": ("/docs",),
    "luau-lang.org": ("/",),  # the whole site is documentation
}

MAX_PAGES = 500             # hard ceiling on distinct pages per run.
                             # Roblox's own doc index lists ~2,300 pages;
                             # raise this if you want full coverage in one
                             # run, at the cost of a longer runtime.
MAX_CONCURRENT_WORKERS = 4  # polite concurrency; also caps memory/CPU use
REQUEST_DELAY_RANGE = (1.5, 3.5)  # seconds, randomized delay per worker
                                   # between requests -- keeps us a good
                                   # citizen of the target servers
NAV_TIMEOUT_MS = 45_000
RETRY_ATTEMPTS = 3
RETRY_DELAYS = (3, 6, 12)         # seconds -- matches the spec exactly

OUTPUT_FILE = Path("roblox_knowledge_base.txt")
ERROR_LOG_FILE = Path("scraping_errors.log")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

# Elements that are page furniture, not documentation content.
SELECTORS_TO_STRIP = [
    "nav",
    "footer",
    "aside",
    ".sidebar",
    "[class*='sidebar']",
    "[class*='cookie']",
    "[id*='cookie']",
    "[class*='consent']",
    "[class*='search']",
    "[role='search']",
    "[class*='login']",
    "[class*='signin']",
    "[class*='feedback']",
    "[class*='modal']",
    "[class*='banner']",
    "[class*='toc']",
    "[class*='breadcrumb']",
    "[class*='pagination']",
    "script",
    "style",
    "noscript",
    "svg",
    "iframe",
    "button",
]

# Candidate containers for the "real" documentation body, tried in order
# during extraction. `body` is a deliberate last resort there, but is
# intentionally NOT part of PRIMARY_CONTENT_LOCATOR below (see
# wait_for_content_locator) -- a bare <body> exists almost instantly on
# any page, including a client-rendered SPA before its JS has painted
# anything into it, so waiting on it alone would defeat the purpose of
# waiting at all.
CONTENT_SELECTORS = ["main", "article", ".markdown-body", "[role='main']", "body"]
PRIMARY_CONTENT_LOCATOR = "main, article, .markdown-body, [role='main']"

MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

_robots_cache: dict = {}


# ============================================================================
# LOGGING
# ============================================================================

def setup_logging() -> logging.Logger:
    log = logging.getLogger("super_scraper")
    log.setLevel(logging.INFO)
    log.propagate = False

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
    log.addHandler(console)

    # Independent file: ONLY failures (ERROR level and above) land here,
    # each with its full exception traceback, per the resiliency spec.
    error_file = logging.FileHandler(ERROR_LOG_FILE, mode="w", encoding="utf-8")
    error_file.setLevel(logging.ERROR)
    error_file.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    log.addHandler(error_file)

    return log


logger = setup_logging()


def log_failure(url: str, exc: BaseException) -> None:
    tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.error(f"FAILED after {RETRY_ATTEMPTS} attempts: {url}\n{tb_text}")


# ============================================================================
# ROBOTS.TXT COMPLIANCE
# ============================================================================

async def load_robot_parser(domain: str) -> RobotFileParser:
    if domain in _robots_cache:
        return _robots_cache[domain]
    rp = RobotFileParser()
    rp.set_url(f"https://{domain}/robots.txt")
    try:
        await asyncio.to_thread(rp.read)
    except Exception as exc:
        logger.warning(f"Could not fetch robots.txt for {domain} ({exc}); assuming crawl is allowed")
        rp = RobotFileParser()
        rp.parse([])  # empty ruleset == everything allowed
    _robots_cache[domain] = rp
    return rp


async def is_allowed_by_robots(url: str) -> bool:
    domain = urlparse(url).netloc
    rp = await load_robot_parser(domain)
    return rp.can_fetch(USER_AGENT, url)


# ============================================================================
# URL / LINK HELPERS
# ============================================================================

def is_in_scope(url: str) -> bool:
    parsed = urlparse(url)
    prefixes = ALLOWED_PATH_PREFIXES.get(parsed.netloc)
    if prefixes is None:
        return False
    return any(parsed.path.startswith(p) for p in prefixes)


def normalize_link(href: Optional[str], base_url: str) -> Optional[str]:
    if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
        return None
    absolute = urljoin(base_url, href)
    parsed = urlparse(absolute)
    if parsed.scheme not in ("http", "https"):
        return None
    # Links may point directly at a ".md" variant (Roblox's own docs link
    # to each other that way). Store the canonical, non-".md" form so the
    # frontier never double-counts a page under two different keys --
    # markdown_candidate_url() below independently re-derives the ".md"
    # URL whenever it's time to actually fetch the page.
    path = parsed.path[:-3] if parsed.path.endswith(".md") else parsed.path
    normalized = urlunparse(parsed._replace(path=path, query="", fragment=""))
    return normalized if is_in_scope(normalized) else None


def markdown_candidate_url(url: str) -> Optional[str]:
    """Best-guess Markdown counterpart of a documentation URL, or None if
    the URL has no meaningful path to turn into one (e.g. a bare domain
    root)."""
    parsed = urlparse(url)
    if not parsed.path or parsed.path == "/" or parsed.path.endswith(".md"):
        return None
    new_path = parsed.path.rstrip("/") + ".md"
    return urlunparse(parsed._replace(path=new_path, query="", fragment=""))


# ============================================================================
# TEXT CLEANING
# ============================================================================

def normalize_whitespace(s: str) -> str:
    return re.sub(r"[ \t]+", " ", s).strip()


def strip_html_comments(text: str) -> str:
    return HTML_COMMENT_RE.sub("", text)


def clean_text(raw: str) -> str:
    """Strip tab indents, trailing whitespace, and collapse runs of blank
    lines into single paragraph breaks."""
    if not raw:
        return ""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_markdown_title(markdown_text: str) -> Optional[str]:
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return normalize_whitespace(stripped[2:])
    return None


# ============================================================================
# DATA MODEL
# ============================================================================

@dataclass
class ScrapedPage:
    url: str
    title: str
    content: str


# ============================================================================
# FAST PATH: pre-rendered Markdown export (no browser page needed at all)
# ============================================================================

async def try_fetch_markdown(context: BrowserContext, canonical_url: str) -> Optional[str]:
    """Attempt to fetch a documentation-platform-provided Markdown export
    of this page via a plain HTTP GET (using Playwright's lightweight
    APIRequestContext, not a rendered Page). Returns the Markdown text on
    success, or None if no such export exists / the request failed --
    both are treated identically: "fall back to full rendering"."""
    candidate = markdown_candidate_url(canonical_url)
    if candidate is None:
        return None
    try:
        response = await asyncio.wait_for(
            context.request.get(
                candidate,
                timeout=10_000,
                headers={"Accept": "text/markdown, text/plain;q=0.9, */*;q=0.1"},
            ),
            timeout=15,
        )
    except Exception:
        return None
    if not response.ok:
        return None
    content_type = response.headers.get("content-type", "")
    if "html" in content_type.lower():
        return None  # a 200 that's actually an HTML error/redirect page
    try:
        body = await response.text()
    except Exception:
        return None
    return body if len(body.strip()) >= 40 else None


def extract_links_from_markdown(markdown_text: str, base_url: str) -> list:
    links = []
    for match in MARKDOWN_LINK_RE.finditer(markdown_text):
        link = normalize_link(match.group(1), base_url)
        if link:
            links.append(link)
    return links


# ============================================================================
# FULL PATH: real browser rendering (Playwright) for JS-heavy SPAs
# ============================================================================

async def wait_for_content_locator(page: Page) -> None:
    try:
        await page.wait_for_selector(PRIMARY_CONTENT_LOCATOR, timeout=15_000, state="visible")
    except PlaywrightTimeoutError:
        logger.warning(f"[{page.url}] no primary content container appeared in time; falling back to <body>")
        await page.wait_for_selector("body", timeout=10_000, state="visible")


async def navigate_with_fallback(page: Page, url: str) -> None:
    try:
        await page.goto(url, wait_until="networkidle", timeout=NAV_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        # networkidle can fail to settle on pages with persistent background
        # connections (analytics beacons, long polling, etc.) even once the
        # actual content has finished rendering. Rather than treat that as a
        # hard failure, fall back to confirming the DOM loaded and a real
        # content locator is visible -- the "Visual Trigger Fallback" this
        # is meant to implement.
        logger.warning(
            f"[{url}] networkidle did not settle within {NAV_TIMEOUT_MS / 1000:.0f}s; using fallback wait"
        )
        await page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT_MS)
    await wait_for_content_locator(page)


async def extract_same_site_links(page: Page, base_url: str) -> list:
    raw_hrefs = await page.eval_on_selector_all(
        "a[href]", "elements => elements.map(el => el.getAttribute('href'))"
    )
    links = []
    for href in raw_hrefs:
        link = normalize_link(href, base_url)
        if link:
            links.append(link)
    return links


async def extract_clean_content(page: Page) -> tuple:
    """Strip nav/footer/sidebar/etc. from the LIVE page (not a detached
    clone -- innerText requires layout, which a detached node never gets),
    then read back the title and remaining body text. Link discovery must
    happen before this runs (see process_url) since sidebars are often the
    only place a docs site's full page tree is discoverable."""
    result = await page.evaluate(
        """
        (args) => {
            const { stripSelectors, contentSelectors } = args;

            stripSelectors.forEach(sel => {
                document.querySelectorAll(sel).forEach(el => el.remove());
            });

            let root = null;
            for (const sel of contentSelectors) {
                root = document.querySelector(sel);
                if (root) break;
            }
            if (!root) root = document.body;

            const h1 = document.querySelector('h1');

            return {
                title: (h1 && h1.innerText) || document.title || '',
                text: root ? root.innerText : '',
            };
        }
        """,
        {"stripSelectors": SELECTORS_TO_STRIP, "contentSelectors": CONTENT_SELECTORS},
    )
    title = normalize_whitespace(result.get("title", ""))
    text = clean_text(result.get("text", ""))
    return title, text


# ============================================================================
# PER-URL ORCHESTRATION (markdown fast path -> full render -> retries)
# ============================================================================

async def process_url(url: str, context: BrowserContext, write_queue: asyncio.Queue) -> list:
    """Fetch `url`, write its cleaned content to write_queue, and return
    the same-site documentation links discovered on it (for the crawl
    frontier). Never raises -- all failures are retried with backoff and,
    if still failing after RETRY_ATTEMPTS, logged to scraping_errors.log
    and swallowed so the crawl continues."""

    # --- 1. Try the lightweight Markdown export first -----------------
    markdown_text = await try_fetch_markdown(context, url)
    if markdown_text is not None:
        cleaned = clean_text(strip_html_comments(markdown_text))
        title = extract_markdown_title(markdown_text) or url
        links = extract_links_from_markdown(markdown_text, url)
        await write_queue.put(ScrapedPage(url=url, title=title, content=cleaned))
        logger.info(f"[OK md]   {url} -> {len(cleaned):,} chars, {len(links)} links")
        return links

    # --- 2. Fall back to full browser rendering, with retries ---------
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        page: Optional[Page] = None
        try:
            page = await context.new_page()
            await navigate_with_fallback(page, url)
            # Discover links from the ORIGINAL page, before any DOM
            # cleansing -- a sidebar table-of-contents is often the main
            # way a docs site's page tree is discoverable at all.
            links = await extract_same_site_links(page, url)
            title, text = await extract_clean_content(page)
            if len(text) < 20:
                logger.warning(f"[{url}] extracted content looks suspiciously short ({len(text)} chars)")
            await write_queue.put(ScrapedPage(url=url, title=title or url, content=text))
            logger.info(f"[OK html] {url} -> {len(text):,} chars, {len(links)} links")
            return links
        except Exception as exc:
            if attempt < RETRY_ATTEMPTS:
                delay = RETRY_DELAYS[attempt - 1]
                logger.warning(
                    f"[RETRY {attempt}/{RETRY_ATTEMPTS}] {url} failed "
                    f"({exc.__class__.__name__}: {exc}); waiting {delay}s"
                )
                await asyncio.sleep(delay)
            else:
                log_failure(url, exc)
        finally:
            if page is not None:
                await page.close()
    return []


# ============================================================================
# OUTPUT WRITER (single dedicated task -> no concurrent-write races)
# ============================================================================

async def writer_worker(write_queue: asyncio.Queue, outfile_path: Path) -> None:
    with outfile_path.open("w", encoding="utf-8") as fh:
        while True:
            item = await write_queue.get()
            if item is None:
                write_queue.task_done()
                break
            fh.write(f"--- START OF RESOURCE: {item.title} ({item.url}) ---\n")
            fh.write(item.content)
            fh.write("\n--- END OF RESOURCE ---\n\n")
            fh.flush()
            write_queue.task_done()


# ============================================================================
# CRAWLER
# ============================================================================

async def frontier_worker(
    frontier: asyncio.Queue,
    visited: set,
    visited_lock: asyncio.Lock,
    write_queue: asyncio.Queue,
    context: BrowserContext,
) -> None:
    while True:
        url = await frontier.get()
        try:
            if not await is_allowed_by_robots(url):
                logger.info(f"[SKIP robots.txt] {url}")
                continue
            await asyncio.sleep(random.uniform(*REQUEST_DELAY_RANGE))
            try:
                links = await process_url(url, context, write_queue)
            except Exception as exc:
                # Belt-and-suspenders: process_url already handles its own
                # failures internally, but nothing about a single bad page
                # is ever allowed to take down the whole crawl.
                log_failure(url, exc)
                links = []
            async with visited_lock:
                for link in links:
                    if link not in visited and len(visited) < MAX_PAGES:
                        visited.add(link)
                        frontier.put_nowait(link)
        finally:
            frontier.task_done()


async def crawl(seed_urls: list) -> None:
    frontier: asyncio.Queue = asyncio.Queue()
    write_queue: asyncio.Queue = asyncio.Queue()
    visited: set = set()
    visited_lock = asyncio.Lock()

    for url in seed_urls:
        parsed = urlparse(url)
        normalized = urlunparse(parsed._replace(query="", fragment=""))
        if is_in_scope(normalized) and normalized not in visited:
            visited.add(normalized)
            frontier.put_nowait(normalized)

    writer_task = asyncio.create_task(writer_worker(write_queue, OUTPUT_FILE))

    async with async_playwright() as pw:
        browser: Optional[Browser] = None
        context: Optional[BrowserContext] = None
        try:
            # NOTE ON LIFECYCLE MANAGEMENT: Browser and BrowserContext are
            # NOT usable as `async with` context managers in playwright-
            # python (only the top-level async_playwright() call is --
            # confirmed against the official docs and an open upstream
            # feature request asking for exactly this). try/finally with
            # explicit .close() calls is the correct, safe equivalent, and
            # is what actually prevents the zombie-process/memory-leak
            # failure modes that requirement is about.
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1440, "height": 900},
                locale="en-US",
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            )

            workers = [
                asyncio.create_task(frontier_worker(frontier, visited, visited_lock, write_queue, context))
                for _ in range(MAX_CONCURRENT_WORKERS)
            ]
            await frontier.join()
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
        finally:
            if context is not None:
                await context.close()
            if browser is not None:
                await browser.close()

    await write_queue.put(None)
    await write_queue.join()
    await writer_task


# ============================================================================
# ENTRYPOINT
# ============================================================================

async def main() -> None:
    start = time.monotonic()
    logger.info(f"Starting crawl of: {', '.join(SEED_URLS)}")
    logger.info(
        f"Config: max_pages={MAX_PAGES} concurrency={MAX_CONCURRENT_WORKERS} retry_attempts={RETRY_ATTEMPTS}"
    )
    await crawl(SEED_URLS)
    elapsed = time.monotonic() - start
    logger.info(f"Done in {elapsed:.1f}s. Corpus written to {OUTPUT_FILE.resolve()}")
    logger.info(f"Any failed URLs (with full tracebacks) are in {ERROR_LOG_FILE.resolve()}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.warning("Interrupted by user (Ctrl+C) -- results written so far are already flushed to disk.")
        sys.exit(1)
