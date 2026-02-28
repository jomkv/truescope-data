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
    source_bias: str | None = None
