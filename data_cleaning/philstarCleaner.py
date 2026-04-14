import json
import os
import re
from datetime import datetime, timezone, timedelta


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

    # Remove Philstar boilerplate footers not part of content
    # - Lines starting with "For more information" (case-insensitive)
    # - Lines starting with "Editor's Note" or "Editor’s Note" (ASCII and Unicode apostrophes)
    lines = text.split("\n")
    filtered = []
    footer_patterns = [
        r"(?i)^for\s+more\s+information\b",
        r"(?i)^for\s+more\s+details\b",
        r"(?i)^for\s+inquiries\b",
        r"(?i)^to\s+learn\s+more\b",
        r"(?i)^visit\s+www\.",
        r"(?i)^follow\s+@",
        r"(?i)^tickets\s+for\s+upcoming\s+events\b",
        r"(?i)^related:\b",
        r"(?i)^buy\s+tickets\s+here\b",
        r"(?i)^editor['’]s\s+note\b",
        r"(?i)^editors\s+note\b",  # variant without apostrophe
        r"(?i)^editors['’]\s+note\b",  # plural possessive
        r"(?i)^this\s+article\s+is\s+for\s+general\s+information\b",
        r"(?i)^the\s+views\s+and\s+opinions\b",
    ]
    for line in lines:
        lstrip = line.lstrip()
        if any(re.match(pat, lstrip) for pat in footer_patterns):
            continue
        filtered.append(line)
    text = "\n".join(filtered)

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


def normalize_publish_date(date_str):
    """
    Normalize publish_date to ISO-8601 UTC (YYYY-MM-DDTHH:MM:SSZ).
    If timezone is missing, assume +08:00 before converting to UTC.
    """
    if not isinstance(date_str, str):
        return date_str
    raw = date_str.strip()
    try:
        dt = datetime.fromisoformat(raw)
    except Exception:
        return raw
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
    utc_dt = dt.astimezone(timezone.utc)
    return utc_dt.isoformat()


def clean_article(article: dict) -> dict:
    """
    Clean and standardize a single Philstar article dictionary for real-time processing.
    """
    cleaned = article.copy()

    # Convert author field from string to array
    if "author" in cleaned:
        cleaned["author"] = normalize_author(cleaned["author"])
    # Clean text fields
    if "content" in cleaned:
        cleaned["content"] = remove_location_prefix(cleaned["content"])
        cleaned["content"] = clean_text_content(cleaned["content"])

    if "title" in cleaned:
        cleaned["title"] = clean_text_content(cleaned["title"])

    # Normalize publish date to UTC ISO string (rename publishDate to publish_date)
    if "publishDate" in cleaned:
        cleaned["publish_date"] = normalize_publish_date(cleaned["publishDate"])
        cleaned.pop("publishDate", None)

    # Normalize labels to ALL CAPS hyphen-separated
    if "source" in cleaned:
        cleaned["source"] = normalize_label(cleaned["source"])
    if "type" in cleaned:
        cleaned["type"] = normalize_label(cleaned["type"])

    # Rename sourceBias to source_bias
    if "sourceBias" in cleaned:
        cleaned["source_bias"] = normalize_label(cleaned["sourceBias"])
        cleaned.pop("sourceBias", None)

    if cleaned.get("source_bias") in (None, ""):
        cleaned["source_bias"] = "LEFT-CENTER"

    return cleaned


def clean_philstar_articles(input_path, output_path):
    """
    Clean articles JSON and save ONLY to processed file.
    """
    if output_path is None:
        raise ValueError("output_path is required to avoid modifying raw data")

    # Read RAW file (read-only)
    with open(input_path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    # Clean articles
    cleaned_articles = [clean_article(article) for article in articles]

    # Write ONLY to processed file
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cleaned_articles, f, indent=2, ensure_ascii=False)

    print(f"✓ Saved cleaned articles to: {output_path}")
    print(f"✓ Processed {len(cleaned_articles)} articles")

    return len(cleaned_articles)


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
        os.path.dirname(__file__), "../data/raw/articlesPhilstar.json"
    )
    processed_file = os.path.join(
        os.path.dirname(__file__), "../data/processed/articlesPhilstar.json"
    )

    # Scan for issues first
    print("SCANNING FOR TEXT CLEANING ISSUES...")
    scan_articles_for_issues(raw_file, sample_size=100)

    # Clean the articles and save to both locations
    print("\nCLEANING ARTICLES...")
    count = clean_philstar_articles(raw_file, processed_file)
    print(f"✓ Cleaning complete: {count} articles processed")
