import uuid
from core.base import Base
from sqlalchemy import Column, String, ForeignKey
try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    from sqlalchemy import Text as Vector

class ArticleChunks(Base):
    __tablename__ = "article_chunks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    chunk_id = Column(String, unique=True, nullable=False)
    chunk_content = Column(String, nullable=False)
    doc_id = Column(String, ForeignKey("articles.doc_id"), nullable=False)
    # 384 dimensions for pgvector
    embedding = Column(Vector(384), nullable=False)
