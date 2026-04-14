import re
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add root directory to sys.path for internal imports
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from data_cleaning.clean_text import clean_text
from data_cleaning.generate_doc_id import generate_doc_id
from data_cleaning.second_cleaning import date_extractor, verdict_normalizer

def clean_article(article: dict) -> dict:
    """
    Clean a single Poynter article.
    """
    cleaned = article.copy()

    # Clean text fields
    cleaned["title"] = clean_text(article.get("title", ""))
    cleaned["content"] = clean_text(article.get("content", ""))

    # Normalize type
    cleaned["type"] = "FACT-CHECK"
    
    # Claim and Verdict
    cleaned["claim"] = clean_text(article.get("claim", article.get("title", "")))
    cleaned["verdict"] = verdict_normalizer.normalize_verdict(
        article.get("verdict", ""), cleaned.get("claim", "")
    )

    # Date normalization
    raw_date = article.get("publish_date")
    cleaned["publish_date"] = date_extractor.normalize_publish_date(raw_date)

    # Metadata
    cleaned["source"] = "POYNTER"
    cleaned["source_bias"] = "LEAST-BIASED" # Poynter is generally neutral
    
    if "authors" in cleaned:
        cleaned["authors"] = cleaned["authors"]
    elif "author" in cleaned:
        cleaned["authors"] = [cleaned["author"]] if isinstance(cleaned["author"], str) else cleaned["author"]
    else:
        cleaned["authors"] = []

    # Generate doc_id for DB unique identification
    cleaned["doc_id"] = generate_doc_id(article.get("url", ""))

    return cleaned
