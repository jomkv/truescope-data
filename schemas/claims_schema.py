import uuid
from core.base import Base
from sqlalchemy import Column, ForeignKey, String
try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    from sqlalchemy import Text as Vector

class Claim(Base):
    __tablename__ = "claims"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    doc_id = Column(String, ForeignKey("articles.doc_id"), nullable=False)
    claim_text = Column(String, nullable=False)
    verdict = Column(String, nullable=True)
    # 384 dimensions matching your articles
    embedding = Column(Vector(384), nullable=False)
