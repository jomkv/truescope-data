"""
Date extraction utility to extract only the first (published) date from text-formatted publish_date strings.

Handles formats like: "Published Oct. 7, 2025\nUpdated Oct. 20, 2025"
Converts text dates to ISO 8601 format with timezone.
"""

import re
from datetime import datetime


def extract_published_date(publish_date_str: str) -> str | None:
    """
    Extract only the published date (first date) from a publish_date string.

    Examples:
    - "Published Oct. 7, 2025\nUpdated Oct. 20, 2025" → "Oct. 7, 2025"
    - "Published October 7, 2025" → "October 7, 2025"
    - "2025-10-08T00:00:00+00:00" → returns as-is (already ISO format)

    Args:
        publish_date_str: The publish date string to parse

    Returns:
        First date extracted, or None if no valid date found
    """
    if not publish_date_str or not isinstance(publish_date_str, str):
        return None

    # If it's already ISO format, return as-is
    if "T" in publish_date_str and ("+" in publish_date_str or "Z" in publish_date_str):
        return publish_date_str.replace("Z", "+00:00")

    # 1. First, check for "Published ..." or "stated on ..." pattern to be precise
    match = re.search(
        r"(?:Published|stated on)\s+(.+?)(?:\s+in|\nUpdated|$|:)",
        publish_date_str,
        re.IGNORECASE,
    )
    if match:
        snippet = match.group(1).strip()
    else:
        snippet = publish_date_str.strip()

    # 2. Extract the first date-like pattern (Month Day, Year) from the snippet (or full string)
    # This handles "March 7, 2025", "Oct. 7, 2025", etc.
    months = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    date_pattern = rf"({months}\.?\s+\d{{1,2}},?\s+\d{{4}})"

    date_match = re.search(date_pattern, snippet, re.IGNORECASE)
    if date_match:
        return date_match.group(1).strip()

    return snippet


def text_date_to_iso(date_str: str) -> str | None:
    """
    Convert text-format date to ISO 8601 format with UTC timezone.

    Examples:
    - "Oct. 7, 2025" → "2025-10-07T00:00:00+00:00"
    - "October 7, 2025" → "2025-10-07T00:00:00+00:00"
    - "June 27, 2022" → "2022-06-27T00:00:00+00:00"
    - "Sept. 30, 2025" → "2025-09-30T00:00:00+00:00"

    Args:
        date_str: Text format date (e.g., "Oct. 7, 2025")

    Returns:
        ISO format datetime string with UTC timezone, or None if parsing fails
    """
    if not date_str or not isinstance(date_str, str):
        return None

    try:
        # Remove periods after month abbreviation if present
        clean_date = date_str.replace(".", "")

        # Handle "Sept" which should be treated as "Sep"
        clean_date = clean_date.replace("Sept", "Sep")

        # Try common date formats used in news articles
        formats = [
            "%B %d, %Y",  # "October 07, 2025"
            "%b %d, %Y",  # "Oct 07, 2025"
            "%B %d %Y",  # "October 07 2025"
            "%b %d %Y",  # "Oct 07 2025"
            "%d %B %Y",  # "07 October 2025" (FullFact style)
            "%d %b %Y",  # "07 Oct 2025"
        ]

        parsed_date = None
        for fmt in formats:
            try:
                parsed_date = datetime.strptime(clean_date, fmt)
                break
            except ValueError:
                continue

        if parsed_date:
            # Convert to ISO format with UTC timezone
            return parsed_date.isoformat() + "+00:00"

    except Exception:
        pass

    return None


def normalize_publish_date(publish_date_str: str) -> str | None:
    """
    Normalize publish_date to ISO format, extracting only the first (published) date.

    Workflow:
    1. If already ISO format → return as-is
    2. If "Published ... Updated ..." format → extract only "Published" date
    3. Convert text date to ISO format with UTC timezone

    Examples:
    - "Published Oct. 7, 2025\nUpdated Oct. 20, 2025" → "2025-10-07T00:00:00+00:00"
    - "2025-10-08T00:00:00+00:00" → "2025-10-08T00:00:00+00:00"
    - "October 7, 2025" → "2025-10-07T00:00:00+00:00"

    Args:
        publish_date_str: Raw publish date string from JSON

    Returns:
        ISO format datetime string with UTC timezone, or None if invalid
    """
    if not publish_date_str or not isinstance(publish_date_str, str):
        return None

    # If already ISO format, return as-is
    if "T" in publish_date_str and ("+" in publish_date_str or "Z" in publish_date_str):
        return publish_date_str.replace("Z", "+00:00")

    # Extract first date if it's a "Published ... Updated ..." format
    first_date = extract_published_date(publish_date_str)
    if not first_date:
        return None

    # Try to parse text format to ISO
    iso_date = text_date_to_iso(first_date)
    return iso_date


if __name__ == "__main__":
    # Test cases
    test_cases = [
        "Published Oct. 7, 2025\nUpdated Oct. 20, 2025",
        "2025-10-08T00:00:00+00:00",
        "Published June 27, 2022\nUpdated June 30, 2023",
        "Published October 7, 2025",
        "Oct. 7, 2025",
    ]

    print("=" * 70)
    print("Testing normalize_publish_date():")
    print("=" * 70)
    for test in test_cases:
        result = normalize_publish_date(test)
        print(f"\nInput:  {test}")
        print(f"Output: {result}")
