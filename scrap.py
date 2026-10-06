import asyncio
import os
import re
import pandas as pd
from pathlib import Path
import aiohttp
from selectolax.lexbor import LexborHTMLParser  # Updated parser backend
from markdownify import markdownify as md
from tqdm.asyncio import tqdm

# Configuration
CSV_PATH = "archive/quotes.csv"        # Path to your input CSV
OUTPUT_DIR = Path("data")       # Directory to store output .md files
CONCURRENCY = 20                # Max parallel requests (adjust based on target rate limits)
TIMEOUT = 15                    # Request timeout in seconds
RETRIES = 2                     # Retry attempts on network/HTTP failures

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

def clean_html_to_markdown(html_bytes: bytes) -> str:
    """Parses raw HTML using Lexbor, removes non-content tags, and converts pure content to Markdown."""
    # Fast C-based Lexbor HTML parsing
    tree = LexborHTMLParser(html_bytes)
    
    # Strip unnecessary noise elements (scripts, styles, navs, footers, etc.)
    for tag in tree.css("script, style, nav, footer, header, iframe, noscript, svg, form"):
        tag.decompose()

    # Extract cleaned HTML body or document root
    body = tree.body or tree.root
    cleaned_html = body.html if body else ""

    if not cleaned_html.strip():
        return "No extractable content found."

    # Convert cleaned HTML structure to clean Markdown text
    markdown_content = md(
        cleaned_html,
        heading_style="ATX",
        strip=["a", "img"]  # Strip hyperlinks and raw images to keep clean text
    )
    
    # Clean up excess blank lines and whitespace
    markdown_content = re.sub(r"\n{3,}", "\n\n", markdown_content).strip()
    return markdown_content

async def fetch_url(session: aiohttp.ClientSession, url: str, semaphore: asyncio.Semaphore) -> str:
    """Fetches web page raw HTML content with retries and concurrency limiting."""
    async with semaphore:
        for attempt in range(1 + RETRIES):
            try:
                async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=TIMEOUT), ssl=False) as response:
                    if response.status == 200:
                        content = await response.read()
                        return clean_html_to_markdown(content)
                    elif response.status in (404, 410):
                        return f"Error: Page not found (HTTP {response.status})"
            except (aiohttp.ClientError, asyncio.TimeoutError):
                if attempt == RETRIES:
                    return "Error: Failed to retrieve content after multiple attempts."
                await asyncio.sleep(1)  # Brief backoff before retry
    return "Error: Unknown failure"

async def process_record(index: int, row: pd.Series, session: aiohttp.ClientSession, semaphore: asyncio.Semaphore):
    """Processes an individual dataset row and saves it to data/<index>.md."""
    file_path = OUTPUT_DIR / f"{index}.md"

    # Extraction variables from CSV
    topic = str(row.get("Topic", "")).strip()
    subtopic = str(row.get("SubTopic", "")).strip()
    url = str(row.get("URL", "")).strip()
    original_text = str(row.get("Text", "")).strip()

    # Fetch and parse web content
    wiki_content = await fetch_url(session, url, semaphore) if url.startswith("http") else "Error: Invalid URL"

    # Assemble Markdown template
    file_content = f"""---
Index: {index}
Topic: {topic}
SubTopic: {subtopic}
URL: {url}
---

# Topic: {topic}
## Subtopic: {subtopic}

### Source URL
{url}

---

## Wiki Content
{wiki_content}

---

## Original Dataset Text
{original_text}
"""

    # Save to data/<index>.md asynchronously using thread executor for disk I/O
    await asyncio.to_thread(file_path.write_text, file_content, encoding="utf-8")

async def main():
    # 1. Ensure output folder exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 2. Load dataset
    print(f"📄 Loading dataset from {CSV_PATH}...")
    df = pd.read_csv(CSV_PATH)
    total_records = len(df)
    print(f"✓ Successfully loaded {total_records} rows.")

    # 3. Setup Async HTTP Session & Semaphore Limit
    semaphore = asyncio.Semaphore(CONCURRENCY)
    connector = aiohttp.TCPConnector(limit=CONCURRENCY, ttl_dns_cache=300)

    print(f"🚀 Starting scraper (Concurrency: {CONCURRENCY} parallel workers)...")

    async with aiohttp.ClientSession(connector=connector) as session:
        # Create asynchronous tasks for all rows
        tasks = [
            process_record(idx, row, session, semaphore)
            for idx, row in df.iterrows()
        ]

        # Execute with a dynamic, real-time progress bar (tqdm)
        for completed_task in tqdm.as_completed(tasks, total=total_records, desc="Scraping progress"):
            await completed_task

    print(f"\n✅ Scraping complete! Files saved in `{OUTPUT_DIR.resolve()}/` directory.")

if __name__ == "__main__":
    asyncio.run(main())