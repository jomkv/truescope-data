from dataclasses import dataclass, field


@dataclass
class ArticleData:
    doc_id: str
    title: str
    content: str
    verdict: str
    publish_date: str
    url: str
