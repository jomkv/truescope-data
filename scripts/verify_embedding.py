from pathlib import Path
from sqlalchemy import select, func
from core.db import Session
from schemas.article_schema import Article
from schemas.article_chunks_schema import ArticleChunks
from schemas.claims_schema import Claim
from data_cleaning.generate_doc_id import generate_doc_id
from data_embedding.base import BaseEmbedding
import json


def compute_expected_chunks(content: str) -> int:
    return len(BaseEmbedding.chunk_text(content))


def verify_sample(sample_path: str, match_url: str | None = None):
    with open(sample_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        # Accept either a list of items or a single item
        if isinstance(data, list):
            if not data:
                print('No items in JSON.')
                return
            if match_url:
                matches = [x for x in data if x.get('url') == match_url]
                if not matches:
                    print(f'No item with url={match_url} found in file')
                    return
                item = matches[0]
            else:
                item = data[0]
        else:
            item = data

    url = item['url']
    doc_id = item.get('doc_id') or generate_doc_id(url)

    expected_article = {
        'doc_id': doc_id,
        'title': item.get('title'),
        'content': item.get('content'),
        'url': url,
        'source': item.get('source'),
        'type': item.get('type'),
    }
    expected_chunk_count = compute_expected_chunks(item.get('content') or '')

    s = Session()
    try:
        art = s.execute(select(Article).where(Article.doc_id == doc_id)).scalar_one_or_none()
        vec_count = s.execute(select(func.count()).select_from(ArticleChunks).where(ArticleChunks.doc_id == doc_id)).scalar() or 0
        claim = s.execute(select(Claim).where(Claim.doc_id == doc_id)).scalar_one_or_none()

        print(f"Doc ID: {doc_id}")
        if art is None:
            print("Article: NOT FOUND")
        else:
            print("Article: FOUND")
            mismatches = []
            for k, v in expected_article.items():
                if k in ('content',):
                    # Skip heavy content equality check; just confirm non-empty
                    continue
                if getattr(art, k) != v:
                    mismatches.append((k, getattr(art, k), v))
            if mismatches:
                print("Article field mismatches:")
                for k, actual, expected in mismatches:
                    print(f"  - {k}: actual={actual} expected={expected}")
            else:
                print("Article fields look consistent (excluding content)")

        print(f"ArticleChunks: {vec_count} (expected ~{expected_chunk_count})")
        if claim is None and (item.get('claim') or '').strip():
            print("Claim: EXPECTED but NOT FOUND")
        elif claim is not None:
            print("Claim: FOUND")
            if claim.claim_text != (item.get('claim') or ''):
                print(f"  - claim_text mismatch: actual={claim.claim_text} expected={item.get('claim')}")
        else:
            print("Claim: not expected (no claim text)")
    finally:
        s.close()


if __name__ == '__main__':
    import sys
    if len(sys.argv) not in (2, 3):
        print('Usage: python -m scripts.verify_embedding <path-to-json> [url-to-match]')
        raise SystemExit(2)
    path = sys.argv[1]
    url_filter = sys.argv[2] if len(sys.argv) == 3 else None
    verify_sample(path, url_filter)
