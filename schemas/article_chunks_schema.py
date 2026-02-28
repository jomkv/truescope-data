import uuid
from core.base import Base
from sqlalchemy import UUID, Column, String, ForeignKey
from pgvector.sqlalchemy import VECTOR


class ArticleChunks(Base):
    __tablename__ = "article_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id = Column(String, unique=True, nullable=False)
    chunk_content = Column(String, nullable=False)
    doc_id = Column(String, ForeignKey("articles.doc_id"), nullable=False)
    embedding = Column(VECTOR(384), nullable=False)
