"""
Create the functional unique index on claims table for (doc_id, md5(claim_text))
"""
from core.db import Session
from sqlalchemy import text

def create_claims_index():
    session = Session()
    try:
        print("Creating functional unique index on claims (doc_id, md5(claim_text))...")
        
        # Drop old constraint if it exists
        session.execute(text("""
            ALTER TABLE claims DROP CONSTRAINT IF EXISTS claims_doc_id_claim_text_key
        """))
        print("✓ Dropped old constraint if existed")
        
        # Create functional unique index
        session.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS claims_doc_id_claim_hash_idx 
            ON claims (doc_id, md5(claim_text))
        """))
        print("✓ Created functional unique index: claims_doc_id_claim_hash_idx")
        
        session.commit()
        print("\n✓ Successfully created index!")
        
    except Exception as e:
        session.rollback()
        print(f"\n✗ Error: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    create_claims_index()
