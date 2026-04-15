import json
import os
import re
from datetime import datetime, timezone, timedelta
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from data_cleaning.second_cleaning import (
    date_extractor,
    format_date,
    verdict_normalizer,
)


def remove_location_prefix(text):
    """
    Remove location/dateline prefix from the start of content.
    Examples: "MANILA – ", "DAVAO CITY – ", "QUEZON CITY — "
    """
    if not isinstance(text, str):
        return text

    # Match location prefix at start: CAPS WORDS followed by dash and space
    # Handles en-dash (–), em-dash (—), and regular hyphen (-)
    text = re.sub(r"^[A-Z][A-Z\s,.]+(–|—|-|\u2013|\u2014)\s+", "", text)
    return text


def clean_text_content(text):
    """
    Clean text content while preserving newlines; collapse extra spaces and fix tabs.

    Args:
        text: The text to clean

    Returns:
        Cleaned text
    """
    if not isinstance(text, str):
        return text

    # Preserve newlines; normalize CRLF and collapse consecutive newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{2,}", "\n", text)

    # Replace tabs with space
    text = text.replace("\t", " ")
    text = text.replace("\\t", " ")

    # Remove multiple consecutive spaces
    text = re.sub(r" +", " ", text)

    # Remove leading/trailing whitespace
    text = text.strip()

    return text


def normalize_author(author_val):
    """
    Normalize author field into a list of clean names, handling prefixes/suffixes.
    Examples handled:
    - "By John Doe" -> ["John Doe"]
    - "By BERNARD ORR and MARTIN QUIN POLLARD, Reuters" -> ["BERNARD ORR", "MARTIN QUIN POLLARD"]
    - "Jane Doe, John Smith" -> ["Jane Doe", "John Smith"]
    """
    names = []

    if isinstance(author_val, list):
        candidates = author_val
    elif isinstance(author_val, str):
        candidates = [author_val]
    else:
        return author_val

    for cand in candidates:
        if not isinstance(cand, str):
            continue
        text = cand.strip()

        # Strip leading By/ BY /
        text = re.sub(r"(?i)^by\s+", "", text)

        # Remove trailing source tags like ", Reuters" or "- Reuters"
        text = re.sub(r"(?i)[,\-]\s*reuters\s*$", "", text).strip()

        # Split on ' and ' and commas
        parts = []
        for piece in re.split(r",|\band\b", text, flags=re.IGNORECASE):
            p = piece.strip()
            if p:
                parts.append(p)

        names.extend(parts)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for n in names:
        if n not in seen:
            seen.add(n)
            unique.append(n)

    return unique if unique else author_val


def normalize_label(value):
    """
    Format labels like source/type/source_bias/verdict:
    - Uppercase
    - Words separated by '-'
    """
    if isinstance(value, str):
        label = value.strip()
        label = re.sub(r"[\s_]+", "-", label)
        label = re.sub(r"-+", "-", label)
        return label.upper()
    return value


def _is_fact_check(article: dict) -> bool:
    """Heuristic to classify Snopes fact-check vs news with stricter guards for NEWS."""
    url = (article.get("url") or "").lower()
    type_val = article.get("type") or ""
    type_upper = type_val.upper() if isinstance(type_val, str) else ""
    verdict_val = article.get("verdict")
    verdict_upper = verdict_val.upper() if isinstance(verdict_val, str) else verdict_val

    # Explicit NEWS stays NEWS even if the URL contains /fact-check (e.g., collections pages)
    if type_upper.startswith("NEWS"):
        return False

    # Fact-check types are authoritative
    if "FACT" in type_upper:
        return True

    # Any explicit verdict means it's a fact-check
    if verdict_upper not in (None, "", "NONE"):
        return True

    # URL heuristic only when type is missing/empty to avoid NEWS bleed-through
    if not type_upper and ("/fact-check" in url or "/factcheck" in url):
        return True

    return False


def clean_article(article: dict) -> dict:
    """
    Clean a single Snopes article dictionary.

    Args:
        article: The raw article dictionary

    Returns:
        The cleaned article dictionary
    """
    cleaned = article.copy()

    # Convert author field from string to array
    if "author" in cleaned:
        cleaned["author"] = normalize_author(cleaned["author"])
    elif "author" in cleaned:
        cleaned["author"] = normalize_author(cleaned["author"])
        cleaned.pop("author", None)
    else:
        cleaned["author"] = []

    # Clean text fields
    if "content" in cleaned:
        cleaned["content"] = remove_location_prefix(cleaned["content"])
        cleaned["content"] = clean_text_content(cleaned["content"])

    if "title" in cleaned:
        cleaned["title"] = clean_text_content(cleaned["title"])

    # Normalize publish date to UTC ISO string (using second-layer date_extractor)
    if "publishDate" in cleaned:
        cleaned["publish_date"] = date_extractor.normalize_publish_date(
            cleaned["publishDate"]
        )
        cleaned.pop("publishDate", None)

    # Standardize source and type labels
    if "source" in cleaned:
        cleaned["source"] = normalize_label(cleaned["source"])
    if "type" in cleaned:
        cleaned["type"] = normalize_label(cleaned["type"])

    # Rename sourceBias to source_bias
    if "sourceBias" in cleaned:
        cleaned["source_bias"] = normalize_label(cleaned["sourceBias"])
        cleaned.pop("sourceBias", None)

    # Normalize verdict using second-layer verdict_normalizer
    if "verdict" in cleaned:
        # Pass claim text for NLP context if it's a long verdict
        cleaned["verdict"] = verdict_normalizer.normalize_verdict(
            cleaned["verdict"], cleaned.get("claim")
        )

    if cleaned.get("source_bias") in (None, ""):
        cleaned["source_bias"] = "LEFT-CENTER"

    # Remove old camelCase field names if they exist (extra safety)
    cleaned.pop("publishDate", None)
    cleaned.pop("sourceBias", None)

    # Final type adjustment based on verdict presence if it's a fact-check
    if _is_fact_check(cleaned):
        verdict_val = cleaned.get("verdict")
        if verdict_val in (None, "", "NONE"):
            cleaned["type"] = "FACT-CHECK-NO-VERDICT"

    return cleaned


def clean_snopes_data(
    input_path, fact_output_path, fact_no_verdict_output_path, news_output_path
):
    """
    Clean Snopes articles and split into fact-check vs news outputs.
    Fact-checks are further split into with-verdict and no-verdict buckets.
    Raw file is never modified.

    Args:
        input_path: Path to the RAW JSON file (read-only)
        fact_output_path: Path to save CLEANED fact-check JSON
        news_output_path: Path to save CLEANED news JSON
    """
    if not fact_output_path or not fact_no_verdict_output_path or not news_output_path:
        raise ValueError(
            "fact_output_path, fact_no_verdict_output_path, and news_output_path are required to avoid modifying raw data"
        )

    # Read RAW file (read-only)
    with open(input_path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    fact_checks = []
    fact_checks_no_verdict = []
    news_items = []

    # Clean articles
    for raw_article in articles:
        article = clean_article(raw_article)

        # Classify
        if _is_fact_check(article):
            if article.get("type") == "FACT-CHECK-NO-VERDICT":
                fact_checks_no_verdict.append(article)
            else:
                fact_checks.append(article)
        else:
            news_items.append(article)

    # Ensure processed directory exists
    os.makedirs(os.path.dirname(fact_output_path), exist_ok=True)
    os.makedirs(os.path.dirname(news_output_path), exist_ok=True)

    with open(fact_output_path, "w", encoding="utf-8") as f:
        json.dump(fact_checks, f, indent=2, ensure_ascii=False)
    with open(fact_no_verdict_output_path, "w", encoding="utf-8") as f:
        json.dump(fact_checks_no_verdict, f, indent=2, ensure_ascii=False)
    with open(news_output_path, "w", encoding="utf-8") as f:
        json.dump(news_items, f, indent=2, ensure_ascii=False)

    print(
        f"✓ Saved fact-checks (with verdict) to: {fact_output_path} ({len(fact_checks)})"
    )
    print(
        f"✓ Saved fact-checks (no verdict) to: {fact_no_verdict_output_path} ({len(fact_checks_no_verdict)})"
    )
    print(f"✓ Saved news to: {news_output_path} ({len(news_items)})")

    return len(articles)


def scan_articles_for_issues(file_path, sample_size=100):
    """
    Scan articles for text cleaning issues like escaped newlines, extra whitespace, HTML entities, etc.

    Args:
        file_path: Path to the JSON file to scan
        sample_size: Number of articles to sample (None for all)
    """
    # Read the JSON file
    with open(file_path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    # Limit sample size
    articles_to_scan = articles[:sample_size] if sample_size else articles

    # Scan for various text cleaning issues
    issues = {
        "escaped_newlines": 0,
        "escaped_tabs": 0,
        "double_spaces": 0,
        "html_entities": 0,
        "extra_whitespace": 0,
        "special_unicode": 0,
    }

    sample_issues = {
        "escaped_newlines": [],
        "escaped_tabs": [],
        "html_entities": [],
    }

    for idx, article in enumerate(articles_to_scan):
        content = article.get("content", "")
        title = article.get("title", "")

        # Check for escaped newlines
        if "\\n" in content or "\\n" in title:
            issues["escaped_newlines"] += 1
            if len(sample_issues["escaped_newlines"]) < 2:
                sample_issues["escaped_newlines"].append((idx, content[:100]))

        # Check for escaped tabs
        if "\\t" in content or "\\t" in title:
            issues["escaped_tabs"] += 1
            if len(sample_issues["escaped_tabs"]) < 2:
                sample_issues["escaped_tabs"].append((idx, content[:100]))

        # Check for double spaces
        if "  " in content:
            issues["double_spaces"] += 1

        # Check for HTML entities
        if (
            "&nbsp;" in content
            or "&quot;" in content
            or "&amp;" in content
            or "&#" in content
        ):
            issues["html_entities"] += 1
            if len(sample_issues["html_entities"]) < 2:
                sample_issues["html_entities"].append((idx, content[:100]))

        # Check for extra whitespace at start/end
        if content != content.strip():
            issues["extra_whitespace"] += 1

        # Check for special problematic characters
        if "\u200b" in content or "\u200c" in content or "\u200d" in content:
            issues["special_unicode"] += 1

    print(f"\n{'='*50}")
    print("SCANNING RESULTS (First {0} articles):".format(len(articles_to_scan)))
    print("=" * 50)
    for issue_type, count in sorted(issues.items()):
        print(f"{issue_type}: {count} occurrences")

    if any(issues.values()):
        print(f"\n{'='*50}")
        print("SAMPLE ISSUES:")
        print("=" * 50)
        for issue_type, samples in sample_issues.items():
            if samples:
                print(f"\n{issue_type}:")
                for idx, text in samples:
                    print(f"  Article {idx}: {text}...")

    # Check content sample
    print(f"\n{'='*50}")
    print("CONTENT SAMPLE (first 300 chars from article 0):")
    print("=" * 50)
    content_sample = articles[0]["content"]
    print(f"{content_sample[:300]}\n")

    return issues


if __name__ == "__main__":
    # Define file paths
    raw_file = os.path.join(
        os.path.dirname(__file__), "../data/raw/articlesSnopes.json"
    )
    fact_output = os.path.join(
        os.path.dirname(__file__), "../data/processed/articlesSnopesFactChecks.json"
    )
    fact_no_verdict_output = os.path.join(
        os.path.dirname(__file__),
        "../data/processed/articlesSnopesFactChecksNoVerdict.json",
    )
    news_output = os.path.join(
        os.path.dirname(__file__), "../data/processed/articlesSnopesNews.json"
    )

    # Scan for issues first
    print("SCANNING FOR TEXT CLEANING ISSUES...")
    scan_articles_for_issues(raw_file, sample_size=100)

    # Clean the articles and save to both locations
    print("\nCLEANING ARTICLES...")
    count = clean_snopes_data(
        raw_file, fact_output, fact_no_verdict_output, news_output
    )
    print(f"✓ Cleaning complete: {count} articles processed")
