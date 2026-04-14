from data_embedding.base import BaseEmbedding
from sqlalchemy.sql import func
import hashlib
from pathlib import Path
from core.db import Session
from sqlalchemy import insert, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from schemas.article_schema import Article
from schemas.article_chunks_schema import ArticleChunks
from schemas.claims_schema import Claim
from data_cleaning.second_cleaning.verdict_normalizer import normalize_verdict


class PolitifactFactcheckEmbedding(BaseEmbedding):
    def __init__(
        self,
        input_file: Path | str,
    ):
        super().__init__(input_file=input_file)

    def process(self):
        (article_vector_dicts, article_dicts) = self.extract()

        # Extract claims BEFORE filtering article_dicts (so we still have claim/verdict fields)
        claims_dicts = []
        for article in article_dicts:
            if (
                article.get("claim") and article.get("claim").strip()
            ):  # Only if claim exists and is not empty
                # Normalize the verdict
                normalized_verdict = normalize_verdict(
                    article.get("verdict"), article.get("claim")
                )
                claim_text = article["claim"]
                claims_dicts.append(
                    {
                        "doc_id": article["doc_id"],
                        "claim_text": claim_text,
                        "verdict": normalized_verdict,
                        "embedding": None,  # Will be generated based on claim_text
                    }
                )

        # Drop duplicate claims per doc_id/claim_text combination before encoding
        orig_claim_count = len(claims_dicts)
        claims_dicts = list(
            {(c["doc_id"], c["claim_text"].strip()): c for c in claims_dicts}.values()
        )
        if len(claims_dicts) != orig_claim_count:
            print(f"  Deduped claims: {orig_claim_count - len(claims_dicts)} removed")

        # Restrict payloads to model columns to avoid passing extraneous keys
        vector_allowed_keys = {"chunk_id", "doc_id", "chunk_content", "embedding"}
        article_allowed_keys = {
            "doc_id",
            "title",
            "content",
            "publish_date",
            "url",
            "source",
            "type",
            "source_bias",
        }

        article_vector_dicts = [
            {k: v for k, v in vec.items() if k in vector_allowed_keys}
            for vec in article_vector_dicts
        ]
        article_dicts = [
            {k: v for k, v in art.items() if k in article_allowed_keys}
            for art in article_dicts
        ]

        # Ensure source_bias is always present to satisfy NOT NULL constraint
        for art in article_dicts:
            bias = art.get("source_bias")
            if bias is None or (isinstance(bias, str) and not bias.strip()):
                art["source_bias"] = "UNKNOWN"

        # Drop duplicate keys within this run to avoid hitting the same doc_id/chunk_id twice per batch
        orig_article_count = len(article_dicts)
        article_dicts = list({a["doc_id"]: a for a in article_dicts}.values())
        if len(article_dicts) != orig_article_count:
            print(
                f"  Deduped articles: {orig_article_count - len(article_dicts)} removed"
            )

        orig_vec_count = len(article_vector_dicts)
        article_vector_dicts = list(
            {v["chunk_id"]: v for v in article_vector_dicts}.values()
        )
        if len(article_vector_dicts) != orig_vec_count:
            print(
                f"  Deduped vectors: {orig_vec_count - len(article_vector_dicts)} removed"
            )

        print(f"\nInserting {len(article_dicts)} articles into database...")
        session = Session()
        try:
            # Batch insert articles in chunks of 500 to avoid parameter limit
            if article_dicts:
                batch_size = 500
                for i in range(0, len(article_dicts), batch_size):
                    batch = article_dicts[i : i + batch_size]
                    stmt = pg_insert(Article).values(batch)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["doc_id"],
                        set_={
                            Article.title: stmt.excluded.title,
                            Article.content: stmt.excluded.content,
                            Article.publish_date: stmt.excluded.publish_date,
                            Article.url: stmt.excluded.url,
                            Article.source: stmt.excluded.source,
                            Article.type: stmt.excluded.type,
                            Article.source_bias: stmt.excluded.source_bias,
                        },
                    )
                    session.execute(stmt)
                    print(
                        f"  ✓ Inserted/updated articles {i+1}-{min(i+batch_size, len(article_dicts))}"
                    )
            print(f"✓ Articles inserted/updated")

            print(f"Inserting {len(article_vector_dicts)} vectors into database...")
            if article_vector_dicts:
                batch_size = 500
                for i in range(0, len(article_vector_dicts), batch_size):
                    batch = article_vector_dicts[i : i + batch_size]
                    stmt = pg_insert(ArticleChunks).values(batch)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["chunk_id"],
                        set_={
                            ArticleChunks.embedding: stmt.excluded.embedding,
                            ArticleChunks.chunk_content: stmt.excluded.chunk_content,
                        },
                    )
                    session.execute(stmt)
                    print(
                        f"  ✓ Inserted/updated vectors {i+1}-{min(i+batch_size, len(article_vector_dicts))}"
                    )
            print(f"✓ Vectors inserted/updated")

            print(f"Inserting {len(claims_dicts)} claims into database...")
            if claims_dicts:
                # Generate embeddings for claims in a single batch
                claim_texts = [c["claim_text"] for c in claims_dicts]
                claim_embeddings = self.model.encode(claim_texts)
                for claim_dict, claim_embedding in zip(claims_dicts, claim_embeddings):
                    claim_dict["embedding"] = claim_embedding

                batch_size = 500
                for i in range(0, len(claims_dicts), batch_size):
                    batch = claims_dicts[i : i + batch_size]
                    stmt = pg_insert(Claim).values(batch)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=[Claim.doc_id, func.md5(Claim.claim_text)],
                        set_={
                            Claim.claim_text: stmt.excluded.claim_text,
                            Claim.verdict: stmt.excluded.verdict,
                            Claim.embedding: stmt.excluded.embedding,
                        },
                    )
                    session.execute(stmt)
                    print(
                        f"  ✓ Inserted/updated claims {i+1}-{min(i+batch_size, len(claims_dicts))}"
                    )
            print(f"✓ Claims inserted/updated")

            session.commit()
            print(
                f"\n✓ Successfully saved {len(article_dicts)} articles, {len(article_vector_dicts)} vectors, and {len(claims_dicts)} claims!"
            )
        except Exception as e:
            session.rollback()
            err_msg = str(getattr(e, "orig", e))
            print(f"\n✗ Error: {err_msg}")
        finally:
            session.close()


if __name__ == "__main__":
    import glob
    import os

    BASE_DIR = Path(__file__).resolve().parent.parent
    outputs_clean_dir = BASE_DIR / "outputs_clean"

    # Get all JSON files in outputs_clean directory
    json_files = sorted(glob.glob(str(outputs_clean_dir / "*.json")))

    print(f"Found {len(json_files)} JSON files to process\n")
    print("=" * 80)

    for idx, file_path in enumerate(json_files, 1):
        file_name = os.path.basename(file_path)
        print(f"\n[{idx}/{len(json_files)}] Processing: {file_name}")
        print("-" * 80)

        try:
            embedder = PolitifactFactcheckEmbedding(input_file=file_path)
            embedder.process()
            print(f"✓ Successfully completed: {file_name}")
        except Exception as e:
            err_msg = str(getattr(e, "orig", e))
            print(f"✗ Error processing {file_name}: {err_msg}")
            # Continue with next file even if one fails
            continue

        print("-" * 80)

    print("\n" + "=" * 80)
    print(f"\n✓ Finished processing all {len(json_files)} files!")
