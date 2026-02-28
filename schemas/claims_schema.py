import uuid
from core.base import Base
from sqlalchemy import Column, ForeignKey, String, DateTime, UUID
from pgvector.sqlalchemy import VECTOR


class Claim(Base):
    __tablename__ = "claims"
    # Uniqueness enforced via functional index: uq_doc_claim_hash on (doc_id, md5(claim_text))
    # This avoids btree size limits on very long claim_text values

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_id = Column(String, ForeignKey("articles.doc_id"), nullable=False)
    claim_text = Column(String, nullable=False)
    verdict = Column(String, nullable=True)
    embedding = Column(VECTOR(384), nullable=False)
