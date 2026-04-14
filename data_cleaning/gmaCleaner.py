import json
import os
import re
from datetime import datetime, timezone, timedelta

MONTH_MAP = {
    "enero": 1,
    "pebrero": 2,
    "febrero": 2,
    "marso": 3,
    "abril": 4,
    "mayo": 5,
    "hunyo": 6,
    "hulyo": 7,
    "agosto": 8,
    "agustu": 8,
    "setyembre": 9,
    "septiembre": 9,
    "oktubre": 10,
    "nobyembre": 11,
    "noviembre": 11,
    "disyembre": 12,
    "diciembre": 12,
}


def load_json_array_lenient(file_path):
    """
    Load a JSON array from file in a lenient way, skipping malformed segments.
    This helps when the raw JSON has occasional structural issues.
    """
    decoder = json.JSONDecoder()
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

    items = []
    idx = 0
    length = len(text)

    # Skip leading whitespace and optional opening bracket
    while idx < length and text[idx].isspace():
        idx += 1
    if idx < length and text[idx] == "[":
        idx += 1

    while idx < length:
        # Skip whitespace and commas between items
        while idx < length and text[idx].isspace():
            idx += 1
        if idx < length and text[idx] == ",":
            idx += 1
            continue
        if idx < length and text[idx] == "]":
            break

        try:
            obj, next_idx = decoder.raw_decode(text, idx)
            items.append(obj)
            idx = next_idx
        except json.JSONDecodeError:
            # Skip one character and continue to attempt recovery
            idx += 1
            continue

    return items


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
    Normalize article text: preserve newlines, collapse spaces, trim edges; replace tabs with spaces.
    """
    if not isinstance(text, str):
        return text

    # Preserve newlines; normalize CRLF and collapse consecutive newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{2,}", "\n", text)
    # Replace tab representations with spaces
    text = text.replace("\t", " ")
    text = text.replace("\\t", " ")

    # Unescape common backslash artifacts and strip stray backslashes
    text = text.replace('\\"', '"')
    text = text.replace("\\\\", "\\")
    text = re.sub(r"\\+", " ", text)

    # Remove recurring boilerplate blocks (GMA wellness promo footer)
    boilerplates = [
        "Need a wellness break? Sign up for The Boost! Stay up-to-date with the latest health and wellness reads. Please enter a valid email address Your email is safe with us",
        "Need a wellness break? Sign up for The Boost!",
        "Stay up-to-date with the latest health and wellness reads.",
        "Please enter a valid email address",
        "Your email is safe with us",
    ]
    for bp in boilerplates:
        # Remove the boilerplate and any duplicates of it
        while bp in text:
            text = text.replace(bp, " ")

    # Truncate at wire service signatures (Reuters/AFP/AP/etc.) if they are at the end of the article
    sig = re.search(
        r"[—\-]{1,2}\s*((Reuters)|(Agence France-Presse)|(AFP)|(Associated Press)|(AP)|(CNN Philippines)|(CNN)|(BBC))\s*$",
        text,
        flags=re.IGNORECASE,
    )
    if sig:
        text = text[: sig.start()]

    # Remove end credits (e.g., "—Jiselle Anne Casucian/RF, GMA Integrated News") if they are at the end
    gma_credit = re.search(
        r"[—\-]\s*[^\n]{0,200}?((GMA Integrated News)|(GMA News)|(GMA News Online)|(GMA Regional TV))\s*$",
        text,
        flags=re.IGNORECASE,
    )
    if gma_credit:
        text = text[: gma_credit.start()]

    # We removed dangerous regexes that formerly stripped "Other Stories" and trailing lists
    # because the scraper now robustly drops those from the DOM via CSS selectors before text extraction.

    # Remove section headers that indicate sidebar/footer content
    remove_patterns = [
        r"\s*More Videos\s*",
        r"\s*Related.*Articles?\s*",
        r"\s*Most Popular\s*",
        r"\s*Tags:.*",
        r"\s*Filtered by:.*",
    ]
    for pattern in remove_patterns:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)

    # Collapse repeated spaces
    text = re.sub(r" +", " ", text)

    return text.strip()


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

        # Strip leading "Sinulat ni" prefix (with optional colon)
        text = re.sub(r"(?i)^sinulat\s+ni\s*:?\s*", "", text)

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
    Supports strings like "Enero 3, 2022 7:20pm GMT+08:00".
    Falls back to original if parsing fails.
    """
    if not isinstance(date_str, str):
        return date_str

    raw = date_str.strip()

    # Already ISO? parse and convert to UTC
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
        utc_dt = dt.astimezone(timezone.utc)
        return utc_dt.isoformat()
    except Exception:
        pass

    # Handle Tagalog/Spanish month format
    m = re.match(
        r"(?i)\s*([a-zñ]+)\s+(\d{1,2}),?\s+(\d{4})\s+(\d{1,2}):(\d{2})\s*(am|pm)?\s*(gmt)?\s*([+-]?\d{1,2}:?\d{2})?",
        raw,
    )
    if m:
        month_name = m.group(1).lower()
        day = int(m.group(2))
        year = int(m.group(3))
        hour = int(m.group(4))
        minute = int(m.group(5))
        ampm = m.group(6)
        tz_part = m.group(8)

        month = MONTH_MAP.get(month_name)
        if not month:
            return raw

        if ampm:
            ampm = ampm.lower()
            if ampm == "pm" and hour != 12:
                hour += 12
            if ampm == "am" and hour == 12:
                hour = 0

        # Normalize timezone to tzinfo
        if tz_part:
            tz_clean = tz_part.replace(":", "")
            sign = 1
            if tz_clean.startswith("-"):
                sign = -1
            digits = tz_clean if tz_clean[0].isdigit() else tz_clean[1:]
            digits = digits.rjust(4, "0")[:4]
            hours = int(digits[:2])
            minutes = int(digits[2:])
            tzinfo = timezone(sign * timedelta(hours=hours, minutes=minutes))
        else:
            tzinfo = timezone(timedelta(hours=8))

        try:
            dt = datetime(year, month, day, hour, minute, tzinfo=tzinfo)
            utc_dt = dt.astimezone(timezone.utc)
            return utc_dt.isoformat()
        except Exception:
            return raw

    return raw


def clean_article(article: dict) -> dict:
    """
    Clean and standardize a single GMA article dictionary for real-time processing.
    """
    cleaned = article.copy()

    # Normalize author field
    if "author" in cleaned:
        cleaned["author"] = normalize_author(cleaned["author"])

    # Clean text fields
    if "content" in cleaned:
        cleaned["content"] = remove_location_prefix(cleaned["content"])
        cleaned["content"] = clean_text_content(cleaned["content"])

    if "title" in cleaned:
        cleaned["title"] = clean_text_content(cleaned["title"])

    # Normalize publish_date (rename publishDate to publish_date)
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

    if "verdict" in cleaned:
        cleaned["verdict"] = normalize_label(cleaned["verdict"])

    # Set source_bias default (processed-only enrichment)
    if cleaned.get("source_bias") in (None, ""):
        cleaned["source_bias"] = "LEFT-CENTER"

    return cleaned


def clean_gma_articles(input_path, output_path):
    """
    Clean articlesGMA.json and save ONLY to the processed file.
    """
    if output_path is None:
        raise ValueError("output_path is required to avoid modifying raw data")

    # Load RAW file (read-only)
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            articles = json.load(f)
    except json.JSONDecodeError:
        print("Warning: JSON malformed; attempting lenient load...")
        articles = load_json_array_lenient(input_path)

    # Clean articles
    cleaned_articles = [clean_article(article) for article in articles]

    # Ensure processed directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Write ONLY to processed file
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cleaned_articles, f, indent=2, ensure_ascii=False)

    print(f"✓ Saved cleaned articles to: {output_path}")
    print(f"✓ Processed {len(cleaned_articles)} articles")

    return len(cleaned_articles)

    # Ensure processed directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Write ONLY to processed file
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(articles, f, indent=2, ensure_ascii=False)

    print(f"✓ Saved cleaned articles to: {output_path}")
    print(f"✓ Processed {len(articles)} articles")

    return len(articles)


if __name__ == "__main__":
    raw_file = os.path.join(os.path.dirname(__file__), "../data/raw/articlesGMA.json")
    processed_file = os.path.join(
        os.path.dirname(__file__), "../data/processed/articlesGMA.json"
    )

    count = clean_gma_articles(raw_file, processed_file)
    print(f"✓ Cleaning complete: {count} articles processed")
