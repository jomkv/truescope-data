from pathlib import Path
import json
from collections import Counter

BASE_DIR = Path(__file__).resolve().parent.parent
A_PATH = BASE_DIR / "outputs/politifact-factcheck2.json"
B_PATH = BASE_DIR / "outputs/politifact-factcheck-raw-final.json"
OUT_PATH = BASE_DIR / "outputs/politifact_synced.json"


def normalize_url(u: str | None) -> str | None:
    """Normalize URL by removing trailing slash."""
    if not u:
        return u
    u = u.strip()
    if u.endswith("/"):
        u = u[:-1]
    return u


def build_b_lookup(b_list: list[dict]) -> dict[str, dict]:
    """Build lookup dictionary from B by URL."""
    lookup: dict[str, dict] = {}
    for item in b_list:
        url = item.get("url")
        if not url:
            continue
        lookup[url] = item
        # Also register normalized URL
        nurl = normalize_url(url)
        if nurl and nurl != url and nurl not in lookup:
            lookup[nurl] = item
    return lookup


def main():
    print("Loading files...")
    A = json.loads(Path(A_PATH).read_text(encoding="utf-8"))
    B = json.loads(Path(B_PATH).read_text(encoding="utf-8"))

    print(f"A (source) count: {len(A)}")
    print(f"B (target) count: {len(B)}")

    # Build B lookup by URL
    b_by_url = build_b_lookup(B)

    merged = []
    matched = 0
    unmatched_urls = []

    # For each record in A, get authors and publish_date from B
    for a in A:
        a_url = a.get("url")
        b = b_by_url.get(a_url) or b_by_url.get(normalize_url(a_url))

        if b:
            matched += 1
            # Take all content from A, but authors and publish_date from B
            record = {
                "title": a.get("title"),
                "content": a.get("content"),
                "publish_date": b.get("publish_date"),  # From B
                "url": a.get("url"),
                "source": a.get("source"),
                "type": a.get("type"),
                "source_bias": a.get("source_bias"),
                "claim": a.get("claim"),
                "verdict": a.get("verdict"),
                "authors": b.get("authors", []),  # From B
            }
        else:
            unmatched_urls.append(a_url)
            # No match in B, keep A as-is
            record = {
                "title": a.get("title"),
                "content": a.get("content"),
                "publish_date": a.get("publish_date"),
                "url": a.get("url"),
                "source": a.get("source"),
                "type": a.get("type"),
                "source_bias": a.get("source_bias"),
                "claim": a.get("claim"),
                "verdict": a.get("verdict"),
                "authors": a.get("authors", []),
            }
            raise Exception(f"No match for A URL {a_url}")
        merged.append(record)

    # Summary
    print("\nSummary")
    print(f"Matched A->B:     {matched}")
    print(f"Unmatched in A:   {len(unmatched_urls)}")
    print(f"Output records:   {len(merged)} (should equal A count: {len(A)})")

    if unmatched_urls[:5]:
        print("\nSample unmatched URLs (A not in B):")
        for u in unmatched_urls[:5]:
            print("  -", u)

    # Save
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to: {OUT_PATH}")
    if len(merged) == len(A):
        print("✓ Output count matches A count")
    else:
        print("⚠ Count mismatch")


if __name__ == "__main__":
    main()
