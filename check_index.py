from core.db import Session
from sqlalchemy import text

session = Session()
result = session.execute(text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'claims' AND indexdef LIKE '%md5%'"))
for row in result:
    print(f"Index: {row[0]}")
    print(f"Definition: {row[1]}")
session.close()
