import re
import sys
import os
from pathlib import Path
from typing import Optional
from datetime import datetime

# Add root directory to sys.path for internal imports
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from data_cleaning.clean_text import clean_text
from data_cleaning.generate_doc_id import generate_doc_id
from data_cleaning.second_cleaning import date_extractor, verdict_normalizer


def clean_date(date: str) -> str:
    """Convert various date formats to ISO format using date_extractor"""
    if not date:
        return None
    # Remove "FIRST PUBLISHED" and "UPDATED" prefixes if they exist
    date_str = re.sub(
        r"(FIRST PUBLISHED|UPDATED)\s+", "", date, flags=re.IGNORECASE
    ).strip()
    return date_extractor.normalize_publish_date(date_str)


def clean_article(article: dict) -> dict:
    """
    Clean a single FullFact article.
    """
    cleaned = article.copy()

    # Text cleaning
    cleaned["title"] = clean_text(article.get("title", ""))
    cleaned["content"] = clean_text(article.get("content", ""))
    cleaned["claim"] = clean_text(article.get("claim", article.get("title", "")))

    # Verdict normalization (FullFact uses descriptive verdicts)
    cleaned["verdict"] = verdict_normalizer.normalize_verdict(
        article.get("verdict"), cleaned.get("claim")
    )

    # Date normalization
    raw_date = article.get("publish_date")
    cleaned["publish_date"] = clean_date(raw_date)

    cleaned["type"] = "FACT-CHECK"

    # Metadata
    cleaned["source"] = "FULLFACT"
    cleaned["source_bias"] = "LEAST-BIASED"  # From MBFC
    if "author" not in cleaned or cleaned["author"] is None:
        cleaned["author"] = []

    # Generate doc_id for DB unique identification
    # Include claim in doc_id if it's a multi-claim article to ensure unique entries
    unique_key = article.get("url", "")
    if cleaned.get("claim") and cleaned.get("claim") != cleaned.get("title"):
        unique_key += f"#{cleaned['claim'][:50]}"

    cleaned["doc_id"] = generate_doc_id(unique_key)

    return cleaned
