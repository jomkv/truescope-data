from dataclasses import dataclass, field


@dataclass
class ArticleData:
    doc_id: str
    title: str
    content: str
    claim: str | None
    verdict: str | None
    publish_date: str
    url: str
    source: str
    type: str
    author: list[str] | None = None
    source_bias: str | None = None
