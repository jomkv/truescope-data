import os
import sys
import re
from pathlib import Path
from typing import Optional

# Add root directory to sys.path to allow imports from other modules
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from data_cleaning.clean_text import clean_text
from data_cleaning.generate_doc_id import generate_doc_id
from data_cleaning.second_cleaning import date_extractor, verdict_normalizer


def extract_date_from_url(url: str) -> Optional[str]:
    """
    Extract publication date from Politifact URL: /factchecks/YYYY/MMM/DD/
    Example: https://www.politifact.com/factchecks/2026/feb/25/nc-trrue-conservatives-pac/
    """
    if not url:
        return None

    match = re.search(
        r"/factchecks/(\d{4})/([a-z]{3,4})/(\d{1,2})/", url, re.IGNORECASE
    )
    if match:
        year, month_abbr, day = match.groups()
        # Mapping for reliable date_extractor parsing
        month_map = {
            "jan": "January",
            "feb": "February",
            "mar": "March",
            "apr": "April",
            "may": "May",
            "jun": "June",
            "jul": "July",
            "aug": "August",
            "sep": "September",
            "sept": "September",
            "oct": "October",
            "nov": "November",
            "dec": "December",
        }
        month = month_map.get(month_abbr.lower(), month_abbr)
        return f"{month} {day}, {year}"
    return None


def parse_date_with_spanish(date_str: str) -> str:
    """
    Parse date string handling Spanish months before passing to date_extractor.
    Example: 'enero 24, 2025' -> 'January 24, 2025'
    """
    if not date_str:
        return None

    spanish_months = {
        "enero": "January",
        "febrero": "February",
        "marzo": "March",
        "abril": "April",
        "mayo": "May",
        "junio": "June",
        "julio": "July",
        "agosto": "August",
        "septiembre": "September",
        "octubre": "October",
        "noviembre": "November",
        "diciembre": "December",
    }

    date_lower = date_str.strip().lower()
    for spanish, english in spanish_months.items():
        if spanish in date_lower:
            # Replace case-insensitively
            date_str = date_str.replace(spanish.capitalize(), english)
            date_str = date_str.replace(spanish, english)
            break

    # Now use our centralized date extractor
    return date_extractor.normalize_publish_date(date_str)


def clean_article(article: dict) -> dict:
    """
    Clean a single Politifact article.
    Matches the schema required for DB insertion (RawData).
    """
    cleaned = article.copy()

    # Basic text cleaning using centralized utilities
    cleaned["title"] = clean_text(article.get("title", ""))
    cleaned["content"] = clean_text(article.get("content", ""))

    # Claim is usually the title in Politifact articles
    cleaned["claim"] = clean_text(article.get("claim", article.get("title", "")))

    # Use centralized verdict normalizer (standardizes True, Mostly-True, Pants-on-fire, etc.)
    cleaned["verdict"] = verdict_normalizer.normalize_verdict(
        article.get("verdict"), cleaned.get("claim")
    )

    # Fixed metadata for Politifact
    cleaned["author"] = article.get("author", article.get("author", []))
    cleaned["source"] = "POLITIFACT"
    cleaned["type"] = (
        "FACT-CHECK" if article.get("verdict") else "FACT-CHECK-NO-VERDICT"
    )
    cleaned["source_bias"] = "LEFT-CENTER"

    # Date normalization: URL date (Publication) is preferred over text date (Claim)
    url_date = extract_date_from_url(article.get("url", ""))
    raw_date = article.get("publish_date")

    # Use URL date if found (more accurate for publication sorting)
    effective_date = url_date if url_date else raw_date
    cleaned["publish_date"] = parse_date_with_spanish(effective_date)

    # Add doc_id for DB unique identification
    cleaned["doc_id"] = generate_doc_id(article.get("url", ""))

    return cleaned
