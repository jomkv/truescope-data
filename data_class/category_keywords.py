from dataclasses import dataclass
from typing import List


@dataclass
class CategoryKeywords:
    """Keyword management for article categorization"""

    politics: List[str]
    social_issues: List[str]
    news: List[str]
    government_entities: List[str]
