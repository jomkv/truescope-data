import re


def clean_text(text: str | None) -> str | None:
    """Normalize whitespace and line breaks in text"""
    if not text:
        return text

    # Normalize line break characters
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    text = re.sub(r"\n{2,}", "\n", text)
    # Trim/collapse spaces per line, keep newlines
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(lines).strip()
