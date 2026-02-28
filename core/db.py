from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from core.config import DATABASE_URI
from core.base import Base

engine = create_engine(DATABASE_URI, pool_pre_ping=True)
Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _init_extensions():
    """Initialize required database extensions"""
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()


def drop_tables():
    """Drop all tables"""
    # Import models so they are registered with Base before drop_all
    import schemas.article_schema  # noqa: F401
    import schemas.article_chunks_schema  # noqa: F401
    import schemas.claims_schema  # noqa: F401
    Base.metadata.drop_all(engine)


def create_tables():
    """Create all tables defined in models"""
    _init_extensions()
    # Import models so they are registered with Base before create_all
    import schemas.article_schema  # noqa: F401
    import schemas.article_chunks_schema  # noqa: F401
    import schemas.claims_schema  # noqa: F401
    Base.metadata.create_all(engine)


if __name__ == "__main__":
    # Allows running as: python -m core.db
    print("Dropping all tables...")
    drop_tables()
    print("✓ Tables dropped")
    print("\nCreating tables...")
    create_tables()
    print("✓ Tables created")
