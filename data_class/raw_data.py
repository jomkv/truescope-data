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
    author: List[str] = field(default_factory=list)
    authors: List[str] = field(default_factory=list)
    source_bias: Optional[str] = None
    claim: Optional[str] = None
    verdict: Optional[str] = None
    doc_id: Optional[str] = None

    # Use 'authors' as the main field, but allow 'author' as an alias for backward compatibility
    @property
    def author(self):
        return self.authors

    @author.setter
    def author(self, value):
        self.authors = value
