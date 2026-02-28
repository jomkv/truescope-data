from pathlib import Path
import sys
from data_embedding.embedder import PolitifactFactcheckEmbedding


def main(path: str):
    p = Path(path)
    if not p.exists():
        print(f"File not found: {p}")
        raise SystemExit(1)
    emb = PolitifactFactcheckEmbedding(input_file=str(p))
    emb.process()


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: python -m scripts.process_one <path-to-json>')
        raise SystemExit(2)
    main(sys.argv[1])
