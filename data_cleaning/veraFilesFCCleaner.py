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


def clean_article(article: dict) -> dict:
    """
    Clean and standardize a single Vera Files article dictionary for real-time processing.
    """
    cleaned = article.copy()

    # Standardize author (list) to match RawData schema
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
        cleaned["content"] = remove_cross_references(cleaned["content"])

    if "title" in cleaned:
        cleaned["title"] = clean_text_content(cleaned["title"])
        cleaned["title"] = clean_title(cleaned["title"])

    # Clean claim field
    if "claim" in cleaned:
        cleaned["claim"] = clean_claim(cleaned["claim"])

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

    return cleaned


def clean_title(text):
    """
    Clean title by removing prefixes like "VERA FILES FACT CHECK: ".
    """
    if not isinstance(text, str):
        return text

    title = text.strip()
    # Remove common prefixes
    title = re.sub(r"(?i)^vera\s+files\s+fact\s+check:\s*", "", title)
    title = re.sub(r"(?i)^fact\s+check:\s*", "", title)

    return title.strip()


def remove_cross_references(text):
    """
    Remove lines containing "READ/SEE/READ MORE VERA FILES FACT CHECK:" or similar patterns.
    Also removes these patterns inline within text.
    """
    if not isinstance(text, str):
        return text

    # Remove entire lines matching the pattern
    lines = text.split("\n")
    filtered = [
        ln
        for ln in lines
        if not re.search(
            r"(?i)(read\s+(more\s+)?|see)\s*(vera\s+files\s+)?(fact\s+)?check:",
            ln.strip(),
        )
    ]
    result = "\n".join(filtered)

    # Also remove inline patterns like "(Read more VERA FILES FACT CHECK: ... )"
    # This handles patterns within parentheses or inline
    result = re.sub(
        r"(?i)\(?(read\s+(more\s+)?|see)\s*(vera\s+files\s+)?(fact\s+)?check:\s*[^)]*\)?",
        "",
        result,
    )

    return result


def clean_claim(text):
    """
    Clean claim field by stripping header (byline, date, etc.) and footer (copyright, terms).
    """
    if not isinstance(text, str):
        return text

    lines = text.strip().split("\n")

    # Strip header lines (Try, BY AUTHOR, dates, Read this FACT CHECK, pipes, etc.)
    while lines:
        line = lines[0].strip()
        # Skip: Try, pipes, empty, author line (BY ...), date patterns, FACT CHECK headers, HTML tags
        if (
            line == "Try"
            or line == "|"
            or line == ""
            or re.match(r"^[a-z]+>", line)  # HTML opening tag like p>, div>, etc.
            or re.match(r"^</[a-z]+>", line)  # HTML closing tag
            or re.match(r"(?i)^by\s+", line)
            or re.match(
                r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}",
                line,
            )
            or re.match(
                r"^\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", line
            )
            or re.match(r"(?i)^read\s+this\s+fact\s+check", line)
        ):
            lines.pop(0)
        else:
            break

    # Strip footer lines (copyright, terms, newsletter signup)
    while lines:
        line = lines[-1].strip()
        # Skip: empty, copyright, terms, "All Rights Reserved", newsletter signup, Poynter/ICCN code
        if (
            line == ""
            or "©" in line
            or re.match(r"(?i).*all rights reserved", line)
            or re.match(r"(?i).*terms of service", line)
            or re.match(r"(?i).*privacy", line)
            or re.match(r"(?i).*receive fresh perspectives", line)
            or re.match(r"(?i).*verafiles.*inc", line)
            or re.match(r"(?i).*international fact.?checking network", line)
            or re.match(r"(?i).*guided by", line)
            or re.match(r"(?i).*poynter", line)
        ):
            lines.pop()
        else:
            break

    return "\n".join(lines).strip()


def clean_frontpage_articles(input_path, output_path, no_verdict_output_path=None):
    """
    Clean articles JSON and save to processed file.

    Optionally writes fact-checks with missing verdicts to a separate file.

    Raw file is never modified.

    Args:
        input_path: Path to the RAW JSON file (read-only)
        output_path: Path to save CLEANED JSON (required)
        no_verdict_output_path: Optional path to save fact-checks without verdict
    """
    if output_path is None:
        raise ValueError("output_path is required to avoid modifying raw data")

    # Read RAW file (read-only)
    with open(input_path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    cleaned_articles = []
    fact_checks_no_verdict = []

    # Clean articles
    for article in articles:
        cleaned = clean_article(article)

        # Classify by verdict
        type_upper = cleaned.get("type", "")
        type_upper = type_upper.upper() if isinstance(type_upper, str) else ""
        verdict_val = cleaned.get("verdict")
        verdict_missing = verdict_val in (None, "", "NONE")
        is_fact_check = "FACT" in type_upper

        if is_fact_check and verdict_missing and no_verdict_output_path:
            cleaned["type"] = "FACT-CHECK-NO-VERDICT"
            fact_checks_no_verdict.append(cleaned)
        else:
            cleaned_articles.append(cleaned)

    # Ensure processed directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Write processed file (fact-checks with verdict + any non-fact-checks)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cleaned_articles, f, indent=2, ensure_ascii=False)

    if no_verdict_output_path:
        os.makedirs(os.path.dirname(no_verdict_output_path), exist_ok=True)
        with open(no_verdict_output_path, "w", encoding="utf-8") as f:
            json.dump(fact_checks_no_verdict, f, indent=2, ensure_ascii=False)
        print(
            f"✓ Saved fact-checks without verdict to: {no_verdict_output_path} ({len(fact_checks_no_verdict)})"
        )

    print(f"✓ Saved cleaned articles to: {output_path} ({len(cleaned_articles)})")
    print(f"✓ Processed {len(articles)} articles total")

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
        os.path.dirname(__file__), "../data/raw/articlesVerafilesFC.json"
    )
    processed_file = os.path.join(
        os.path.dirname(__file__), "../data/processed/articlesVerafilesFC.json"
    )
    no_verdict_file = os.path.join(
        os.path.dirname(__file__), "../data/processed/articlesVerafilesFCNoVerdict.json"
    )

    # Scan for issues first
    print("SCANNING FOR TEXT CLEANING ISSUES...")
    scan_articles_for_issues(raw_file, sample_size=100)

    # Clean the articles and save to both locations
    print("\nCLEANING ARTICLES...")
    count = clean_frontpage_articles(raw_file, processed_file, no_verdict_file)
    print(f"✓ Cleaning complete: {count} articles processed")
