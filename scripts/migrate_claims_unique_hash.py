from sqlalchemy import text
from core.db import engine

"""
Migration: Replace unique constraint on claims (doc_id, claim_text) with a functional unique index.
- Drops old unique constraint uq_claim_doc_claimtext if present (problematic for very long claim_text values).
- Creates a UNIQUE INDEX named uq_claim_doc_claimtext_md5 on (doc_id, md5(claim_text)).
This avoids btree row size limits while preserving uniqueness semantics without changing column names.
Idempotent: checks for existing constraints/indexes before altering.
"""

def constraint_exists(conn, table_name: str, constraint_name: str) -> bool:
    sql = text(
        """
        SELECT 1
        FROM information_schema.table_constraints
        WHERE table_name = :table
          AND constraint_name = :name
        LIMIT 1
        """
    )
    res = conn.execute(sql, {"table": table_name, "name": constraint_name}).fetchone()
    return res is not None


def index_exists(conn, index_name: str) -> bool:
    sql = text(
        """
        SELECT 1
        FROM pg_class c
        JOIN pg_index i ON i.indexrelid = c.oid
        WHERE c.relname = :name
        LIMIT 1
        """
    )
    res = conn.execute(sql, {"name": index_name}).fetchone()
    return res is not None


def run_migration():
    with engine.begin() as conn:
        # 1) Drop old unique constraint if present
        if constraint_exists(conn, "claims", "uq_claim_doc_claimtext"):
            conn.execute(text("ALTER TABLE claims DROP CONSTRAINT uq_claim_doc_claimtext"))
        
        # 2) Create functional unique index if missing
        if not index_exists(conn, "uq_claim_doc_claimtext_md5"):
            conn.execute(text("CREATE UNIQUE INDEX uq_claim_doc_claimtext_md5 ON claims (doc_id, md5(claim_text))"))

        print("Migration completed: functional unique index on (doc_id, md5(claim_text))")


if __name__ == "__main__":
    run_migration()
