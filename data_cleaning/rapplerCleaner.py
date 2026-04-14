import re
import sys
import os
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

# Add root directory to sys.path for internal imports
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from data_cleaning.clean_text import clean_text
from data_cleaning.generate_doc_id import generate_doc_id
from data_cleaning.second_cleaning import date_extractor, verdict_normalizer


def normalize_verdict(text: str) -> str:
    """Normalize verdict by removing label prefixes, explanatory text, and trailing punctuation"""
    if not text:
        return ""
    # Drop a leading "<label>:" (e.g., "Rating:", "Marka:", "MISLEADING:")
    text = re.sub(r"^\s*[^:]+:\s*", "", text, count=1)

    # Remove everything after the first sentence (ending with .)
    verdict = text.split(".")[0]

    # Remove trailing punctuation (., :, etc.)
    verdict = verdict.rstrip(".:;,!?")

    return verdict.strip()


def standardize_verdict(verdict: str, claim: str = "") -> str:
    """Map verdicts to labels suitable for classification using decentralized normalizer if possible"""
    # Use the centralized normalizer which is more robust
    return verdict_normalizer.normalize_verdict(verdict, claim)


def clean_article(article: dict) -> dict:
    """
    Clean a single Rappler article (News or Fact-Check).
    """
    cleaned = article.copy()

    # Clean text fields
    cleaned["title"] = clean_text(article.get("title", ""))
    cleaned["content"] = clean_text(article.get("content", ""))

    # Handle Fact-Check specific fields
    if (
        article.get("type") == "fact-check"
        or "fact-check" in article.get("url", "").lower()
    ):
        cleaned["type"] = "FACT-CHECK"
        # Claim is usually the title for Rappler fact-checks if not provided
        cleaned["claim"] = clean_text(article.get("claim", article.get("title", "")))
        cleaned["verdict"] = standardize_verdict(
            article.get("verdict", ""), cleaned.get("claim", "")
        )
    else:
        cleaned["type"] = "NEWS"
        cleaned["claim"] = None
        cleaned["verdict"] = None

    # Date normalization
    raw_date = article.get("publish_date")
    cleaned["publish_date"] = date_extractor.normalize_publish_date(raw_date)

    # Metadata
    cleaned["source"] = "RAPPLER"
    cleaned["source_bias"] = "LEFT-CENTER"
    if "author" not in cleaned or cleaned["author"] is None:
        cleaned["author"] = []

    # Generate doc_id for DB unique identification
    cleaned["doc_id"] = generate_doc_id(article.get("url", ""))

    return cleaned
