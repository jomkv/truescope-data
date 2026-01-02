from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session as SessionType

from core.config import DATABASE_URI


class Database:
    """Database manager for batch processing scripts"""

    def __init__(self, database_uri: str = DATABASE_URI):
        self.engine = create_engine(database_uri, pool_pre_ping=True)
        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )
        self.Base = declarative_base()

    def _init_extensions(self):
        """Initialize required database extensions"""
        with self.engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()

    def get_session(self) -> SessionType:
        """Get a new database session"""
        return self.SessionLocal()

    def create_tables(self):
        """Create all tables defined in models"""
        self._init_extensions()
        self.Base.metadata.create_all(self.engine)


# Global instance for convenience
db = Database()
Base = db.Base
