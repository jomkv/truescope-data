from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from core.config import DATABASE_URI, CA_CERT_PATH
from core.base import Base
import os

# Configure SQLAlchemy engine with specific SSL parameters for Production
connect_args = {}
if "postgresql" in DATABASE_URI and CA_CERT_PATH:
    connect_args["sslmode"] = "require"
    # Use the CA certificate if it exists
    if os.path.exists(CA_CERT_PATH):
        connect_args["sslrootcert"] = CA_CERT_PATH
    else:
        print(f"Warning: CA_CERT_PATH {CA_CERT_PATH} not found. DB connection might fail.")

engine = create_engine(
    DATABASE_URI,
    pool_pre_ping=True,
    connect_args=connect_args
)

Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def drop_tables():
    """Drop all tables for a clean slate."""
    import time
    tables = ["claims", "article_chunks", "articles"]

    with engine.connect() as conn:
        for table in tables:
            print(f"  - Dropping {table}...")
            for attempt in range(3):
                try:
                    conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                    conn.commit()
                    break
                except Exception as e:
                    if attempt == 2:
                        print(f"    Failed to drop {table}: {e}")
                    else:
                        print(f"    Retrying {table} drop...")
                        time.sleep(2)

def create_tables():
    """Create all tables and initialize pgvector setup."""
    # Import schemas to register them with SQLAlchemy Base
    import schemas.article_schema  # noqa: F401
    import schemas.article_chunks_schema  # noqa: F401
    import schemas.claims_schema  # noqa: F401

    with engine.connect() as conn:
        # 1. Enable pgvector extension first
        try:
            print("Enabling pgvector extension...")
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
        except Exception as e:
            print(f"  Error enabling pgvector (ensure you are using Managed Postgres with superuser/admin access): {e}")

    # 2. Create standard tables
    Base.metadata.create_all(engine)

    # 3. Establish Postgres-specific indices (pgvector HNSW)
    with engine.connect() as conn:
        print("Establishing production indices...")
        
        # Standard indices
        indices = [
            ("idx_article_chunks_doc_id", "article_chunks", "doc_id"),
            ("idx_claims_verdict", "claims", "verdict"),
        ]
        for idx_name, table, col in indices:
            try:
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({col})"))
            except Exception as e:
                print(f"  Could not create index {idx_name}: {e}")

        # Vector HNSW indices for high-speed similarity search
        vector_indices = [
            ("chunks_vec_idx", "article_chunks", "embedding", "vector_cosine_ops"),
            ("claims_idx", "claims", "embedding", "vector_cosine_ops"),
        ]
        for idx_name, table, col, ops in vector_indices:
            try:
                # Check if index exists
                res = conn.execute(
                    text(f"SELECT indexname FROM pg_indexes WHERE indexname = '{idx_name}'")
                ).fetchone()
                if not res:
                    print(f"  - Creating pgvector HNSW index: {idx_name}...")
                    conn.execute(text(f"CREATE INDEX {idx_name} ON {table} USING hnsw ({col} {ops})"))
            except Exception as e:
                print(f"  Could not create vector index {idx_name}: {e}")
        
        conn.commit()
    print("Database initialization complete.")

if __name__ == "__main__":
    print(f"Targeting Postgres: {engine.url.host}")
    create_tables()
