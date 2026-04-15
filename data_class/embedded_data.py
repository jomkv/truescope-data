from dataclasses import dataclass, field


@dataclass
class EmbeddedData:
    chunk_id: str
    doc_id: str
    chunk_content: str
    embedding: list[int]
    source: str
    type: str
    source_bias: str
