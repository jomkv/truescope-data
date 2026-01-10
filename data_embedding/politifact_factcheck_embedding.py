from data_embedding.base import BaseEmbedding
from pathlib import Path
from core.db import Session
from sqlalchemy import insert
from schemas.article_schema import Article
from schemas.article_vector_schema import ArticleVector


class PolitifactFactcheckEmbedding(BaseEmbedding):
    def __init__(
        self,
        input_file: Path | str,
    ):
        super().__init__(input_file=input_file)

    def process(self):
        (article_vector_dicts, article_dicts) = self.extract()

        session = Session()
        try:
            session.execute(insert(Article), article_dicts)
            session.execute(insert(ArticleVector), article_vector_dicts)

            print(f"Articles and vectors saved")

            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()


if __name__ == "__main__":
    BASE_DIR = Path(__file__).resolve().parent.parent
    input_path = BASE_DIR / "outputs_clean/politifact/politifact_factcheck_cleaned.json"

    politifact = PolitifactFactcheckEmbedding(input_file=input_path)
    politifact.process()
