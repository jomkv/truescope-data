import json
import os
from pathlib import Path
from data_class.raw_data import RawData
from data_class.article_data import ArticleData
from data_class.embedded_data import EmbeddedData
from sentence_transformers import SentenceTransformer


class BaseEmbedding:
    def __init__(
        self,
        input_file: Path | str,
        model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    ):
        self.raw_datas: list[RawData] = []
        self.model = SentenceTransformer(model)
        self.input_file = input_file

    @staticmethod
    def chunk_text(text: str, min_words: int = 150, max_words: int = 300) -> list[str]:
        """
        Chunk text into paragraph-aligned chunks
        between min_words and max_words.
        """
        paragraphs: list[str] = [
            p.strip() for p in text.split("\n") if len(p.strip()) > 0
        ]

        chunks: list[str] = []
        current_chunk: list[str] = []
        current_word_count: int = 0

        for para in paragraphs:
            words = para.split()
            word_count = len(words)

            # If adding this paragraph exceeds max_words,
            # finalize the current chunk
            if current_word_count + word_count > max_words:
                if current_word_count >= min_words:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = []
                    current_word_count = 0

            current_chunk.append(para)
            current_word_count += word_count

        # Add remaining chunk
        if current_word_count >= min_words:
            chunks.append(" ".join(current_chunk))

        return chunks

    def generate_embedding(self, raw_data: RawData) -> list[EmbeddedData]:
        contents = self.chunk_text(raw_data["content"])
        content_embeddings = self.model.encode(contents)
        embedded_datas: list[EmbeddedData] = []

        for idx, content_embedding in enumerate(content_embeddings):
            embedded_data = EmbeddedData(
                chunk_id=f"{raw_data['doc_id']}_{idx}",
                doc_id=raw_data["doc_id"],
                embedding=content_embedding,
                source=raw_data["source"],
                type=raw_data["type"],
                source_bias=raw_data["source_bias"],
            )

            embedded_datas.append(embedded_data)

        return embedded_datas

    @staticmethod
    def generate_article_data(raw_data: RawData) -> ArticleData:
        return ArticleData(
            doc_id=raw_data["doc_id"],
            title=raw_data["title"],
            content=raw_data["content"],
            verdict=raw_data["verdict"],
            publish_date=raw_data["publish_date"],
            url=raw_data["url"],
        )

    def extract_data_from_json(self) -> list[RawData]:
        if os.path.exists(self.input_file):
            with open(self.input_file, "r", encoding="utf-8") as f:
                try:
                    self.raw_datas = json.load(f)
                except json.JSONDecodeError as e:
                    raise e

    def process(self):
        """Entry point of base, the only function that we call outside base"""
        self.extract_data_from_json(self.input_file)

        embeddings: list[EmbeddedData] = []
        datas: list[ArticleData] = []

        for raw_data in self.raw_datas:
            embeddings += self.generate_embedding(raw_data)
            datas.append(self.generate_article_data(raw_data))

        # TODO: save to DB? or save as file? idk mane
