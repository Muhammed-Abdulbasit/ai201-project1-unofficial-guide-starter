"""
ingest.py — Milestone 3: Document Ingestion + Chunking

Loads the RateMyProfessors professor pages listed in sources.txt, cleans the
review text, and splits it into chunks of CHUNK_SIZE characters with
CHUNK_OVERLAP characters of overlap (per planning.md).

Why GraphQL instead of scraping HTML:
    RateMyProfessors is a React/Relay app. The page HTML server-side renders
    only the FIRST 5 reviews for a professor (inside window.__RELAY_STORE__).
    The site's public GraphQL endpoint returns ALL reviews, so we use it to get
    the complete corpus. No headless browser is required — this is plain HTTP.

Outputs:
    documents/<legacyId>_<First>_<Last>.txt   one readable raw document per professor
    chunks.json                               all chunks + metadata, ready for embedding

Usage:
    python ingest.py
"""

import base64
import html
import json
import re
import time
from pathlib import Path

import requests

# --- Configuration (from planning.md > Chunking Strategy) -------------------
# An RMP comment caps at 350 chars, but each chunk also carries an attribution
# header ("Professor X | Dept | Course") plus a Tags/Grade suffix so the
# professor's name survives into every chunk for grounded retrieval. With those
# additions the longest assembled review is ~508 chars, so a 550-char window
# keeps 100% of reviews in a single chunk (no review is split mid-sentence).
CHUNK_SIZE = 550      # characters — fits comment + attribution header in one chunk
CHUNK_OVERLAP = 50    # characters — context carried across boundaries on any longer doc

SOURCES_FILE = Path(__file__).parent / "sources.txt"
DOCUMENTS_DIR = Path(__file__).parent / "documents"
CHUNKS_FILE = Path(__file__).parent / "chunks.json"

GRAPHQL_URL = "https://www.ratemyprofessors.com/graphql"
# Well-known public Basic-auth token RMP ships in its own front-end bundle
# (base64 of "test:test"). It gates the public read-only GraphQL API.
RMP_AUTH_TOKEN = "dGVzdDp0ZXN0"
REQUEST_DELAY = 1.0   # seconds between professors — be polite to the server

RATINGS_QUERY = """
query RatingsListQuery($id: ID!, $count: Int!, $cursor: String) {
  node(id: $id) {
    ... on Teacher {
      firstName
      lastName
      department
      numRatings
      avgRating
      avgDifficulty
      wouldTakeAgainPercent
      school { name }
      ratings(first: $count, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        edges {
          node {
            comment
            class
            date
            clarityRating
            difficultyRating
            wouldTakeAgain
            grade
            ratingTags
          }
        }
      }
    }
  }
}
"""


# --- Loading ----------------------------------------------------------------
def read_sources(path=SOURCES_FILE):
    """Return the list of professor URLs from sources.txt (skips comments/blanks)."""
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def legacy_id_from_url(url):
    """Extract the numeric professor id from a /professor/<id> URL."""
    match = re.search(r"/professor/(\d+)", url)
    if not match:
        raise ValueError(f"Could not find a professor id in URL: {url}")
    return match.group(1)


def graphql_id(legacy_id):
    """RMP GraphQL node id is base64('Teacher-<legacyId>')."""
    return base64.b64encode(f"Teacher-{legacy_id}".encode()).decode()


def fetch_professor(legacy_id, session):
    """Fetch a professor's metadata and ALL of their reviews via GraphQL.

    Returns a dict with professor fields and a 'reviews' list, or None if the
    professor could not be loaded.
    """
    node_id = graphql_id(legacy_id)
    headers = {
        "Authorization": "Basic " + RMP_AUTH_TOKEN,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    }

    reviews = []
    teacher = None
    cursor = None

    # Paginate until every review is collected.
    while True:
        variables = {"id": node_id, "count": 100, "cursor": cursor}
        resp = session.post(
            GRAPHQL_URL,
            headers=headers,
            data=json.dumps({"query": RATINGS_QUERY, "variables": variables}),
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()

        node = (payload.get("data") or {}).get("node")
        if not node:
            print(f"  ! No data returned for professor {legacy_id} "
                  f"(errors: {payload.get('errors')})")
            return None

        if teacher is None:
            teacher = node

        ratings = node.get("ratings") or {}
        for edge in ratings.get("edges", []):
            reviews.append(edge["node"])

        page = ratings.get("pageInfo") or {}
        if page.get("hasNextPage") and page.get("endCursor"):
            cursor = page["endCursor"]
            time.sleep(REQUEST_DELAY)
        else:
            break

    return {
        "legacy_id": legacy_id,
        "first_name": teacher.get("firstName") or "",
        "last_name": teacher.get("lastName") or "",
        "department": teacher.get("department") or "",
        "school": (teacher.get("school") or {}).get("name") or "",
        "num_ratings": teacher.get("numRatings"),
        "avg_rating": teacher.get("avgRating"),
        "avg_difficulty": teacher.get("avgDifficulty"),
        "would_take_again_percent": teacher.get("wouldTakeAgainPercent"),
        "reviews": reviews,
    }


# --- Cleaning ---------------------------------------------------------------
def clean_text(text):
    """Normalize a raw review string for embedding.

    - Unescape HTML entities (&amp; -> &, &#39; -> ')
    - Collapse all runs of whitespace (incl. newlines/tabs) to single spaces
    - Strip leading/trailing whitespace
    """
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def format_tags(raw_tags):
    """RMP returns rating tags as a '--'-delimited string. Make it readable."""
    if not raw_tags:
        return ""
    tags = [t.strip() for t in raw_tags.split("--") if t.strip()]
    return ", ".join(tags)


def build_review_text(prof, review):
    """Build the text unit that gets chunked for one review.

    A short attribution header is prepended so the professor's name survives
    into every chunk — this keeps retrieval and source attribution grounded
    even when a chunk is read in isolation.
    """
    name = f"{prof['first_name']} {prof['last_name']}".strip()
    header_bits = [f"Professor {name}"]
    if prof["department"]:
        header_bits.append(prof["department"])
    course = clean_text(review.get("class") or "")
    if course:
        header_bits.append(f"Course {course}")
    header = " | ".join(header_bits)

    comment = clean_text(review.get("comment") or "")
    tags = format_tags(review.get("ratingTags") or "")
    grade = clean_text(review.get("grade") or "")

    extras = []
    if tags:
        extras.append(f"Tags: {tags}")
    if grade and grade.lower() not in ("", "not", "n/a"):
        extras.append(f"Grade received: {grade}")

    parts = [f"{header}. {comment}"]
    if extras:
        parts.append(" ".join(extras))
    return " ".join(parts).strip()


# --- Chunking ---------------------------------------------------------------
def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Split text into overlapping fixed-size character windows.

    Returns a list of chunk strings. A chunk is at most `chunk_size` characters;
    each subsequent chunk starts `chunk_size - overlap` characters after the
    previous one, so consecutive chunks share `overlap` characters of context.
    """
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    text = text.strip()
    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    chunks = []
    step = chunk_size - overlap
    start = 0
    n = len(text)
    while start < n:
        chunk = text[start:start + chunk_size]
        chunks.append(chunk)
        if start + chunk_size >= n:
            break
        start += step
    return chunks


# --- Persistence ------------------------------------------------------------
def safe_filename(prof):
    name = f"{prof['first_name']}_{prof['last_name']}".strip("_")
    name = re.sub(r"[^A-Za-z0-9_]+", "", name) or "professor"
    return f"{prof['legacy_id']}_{name}.txt"


def write_raw_document(prof, url):
    """Write a human-readable raw document for one professor to documents/."""
    DOCUMENTS_DIR.mkdir(exist_ok=True)
    path = DOCUMENTS_DIR / safe_filename(prof)
    full_name = f"{prof['first_name']} {prof['last_name']}".strip()

    lines = [
        f"Professor: {full_name}",
        f"Department: {prof['department']}",
        f"School: {prof['school']}",
        f"Source: {url}",
        f"Overall rating: {prof['avg_rating']} | Difficulty: {prof['avg_difficulty']} "
        f"| Would take again: {prof['would_take_again_percent']}% | Reviews: {prof['num_ratings']}",
        "=" * 70,
        "",
    ]
    for i, review in enumerate(prof["reviews"], start=1):
        course = clean_text(review.get("class") or "n/a")
        date = (review.get("date") or "").split(" ")[0]
        lines.append(f"[Review {i}] Course: {course} | Date: {date}")
        lines.append(clean_text(review.get("comment") or ""))
        tags = format_tags(review.get("ratingTags") or "")
        if tags:
            lines.append(f"Tags: {tags}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# --- Pipeline ---------------------------------------------------------------
def main():
    urls = read_sources()
    print(f"Loaded {len(urls)} source URL(s) from {SOURCES_FILE.name}")

    session = requests.Session()
    all_chunks = []
    chunk_id = 0
    professors_loaded = 0

    for url in urls:
        legacy_id = legacy_id_from_url(url)
        print(f"\nFetching professor {legacy_id} ...")
        try:
            prof = fetch_professor(legacy_id, session)
        except requests.RequestException as exc:
            print(f"  ! Request failed for {url}: {exc}")
            continue

        if prof is None:
            continue

        full_name = f"{prof['first_name']} {prof['last_name']}".strip()
        print(f"  -> {full_name} ({prof['department']}) | "
              f"{len(prof['reviews'])} reviews loaded")

        doc_path = write_raw_document(prof, url)
        professors_loaded += 1

        # Chunk one review at a time so review boundaries are respected.
        for review_idx, review in enumerate(prof["reviews"]):
            review_text = build_review_text(prof, review)
            for piece_idx, chunk in enumerate(chunk_text(review_text)):
                all_chunks.append({
                    "id": f"chunk-{chunk_id}",
                    "text": chunk,
                    "metadata": {
                        "professor": full_name,
                        "department": prof["department"],
                        "school": prof["school"],
                        "course": clean_text(review.get("class") or ""),
                        "date": (review.get("date") or "").split(" ")[0],
                        "source_url": url,
                        "legacy_id": prof["legacy_id"],
                        "review_index": review_idx,
                        "chunk_index": piece_idx,
                        "source_document": doc_path.name,
                    },
                })
                chunk_id += 1

        time.sleep(REQUEST_DELAY)

    CHUNKS_FILE.write_text(
        json.dumps(all_chunks, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # --- Summary ---
    print("\n" + "=" * 50)
    print("Ingestion + chunking complete.")
    print(f"  Professors loaded : {professors_loaded}/{len(urls)}")
    print(f"  Raw documents     : {DOCUMENTS_DIR}/")
    print(f"  Total chunks      : {len(all_chunks)}")
    if all_chunks:
        sizes = [len(c["text"]) for c in all_chunks]
        print(f"  Chunk size (chars): min {min(sizes)} | "
              f"avg {sum(sizes) // len(sizes)} | max {max(sizes)}")
        print(f"  Chunks written to : {CHUNKS_FILE.name}")


if __name__ == "__main__":
    main()
