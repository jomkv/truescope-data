from dataclasses import dataclass, field


@dataclass
class EmbeddedData:
    chunk_id: str
    doc_id: str
    embedding: list[int]
    source: str
    type: str
    source_bias: str
