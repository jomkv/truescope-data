from core.base import Base
from sqlalchemy import Column, String, DateTime

class Article(Base):
    __tablename__ = "articles"

    doc_id = Column(String, primary_key=True)
    publish_date = Column(DateTime, nullable=True) # Matches your local 'timestamp without time zone'
    title = Column(String, nullable=True)
    content = Column(String, nullable=True)
    url = Column(String, nullable=True)
    source = Column(String, nullable=True)
    type = Column(String, nullable=True)
    source_bias = Column(String, nullable=True)
