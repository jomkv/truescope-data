from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class RawData:
    """
    Data class to represent raw data retreived from scraping our sources.
    """

    title: str
    content: str
    publish_date: str  # iso date string
    url: str
    source: str
    type: str
    source_bias: Optional[str] = None
    claim: Optional[str] = None
    verdict: Optional[str] = None
    authors: List[str] = field(default_factory=list)
