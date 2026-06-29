import json
from pathlib import Path

import faiss
import numpy as np

from app.core.config import Settings


class VectorStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.index_path = settings.resolved_faiss_index_dir / "logs.index"
        self.mapping_path = settings.resolved_faiss_index_dir / "mapping.json"
        self.index = self._load_index()
        self.mapping = self._load_mapping()

    @property
    def count(self) -> int:
        return int(self.index.ntotal)

    def reset(self) -> None:
        self.index = faiss.IndexFlatIP(self.settings.embedding_dimension)
        self.mapping = []
        self.persist()

    def add(self, chunk_ids: list[str], embeddings: np.ndarray) -> int:
        if embeddings.size == 0:
            return 0
        normalized = self._normalize(embeddings)
        if normalized.shape[1] != self.index.d:
            raise ValueError(f"Embedding dimension {normalized.shape[1]} does not match FAISS index {self.index.d}")
        self.index.add(normalized)
        self.mapping.extend(chunk_ids)
        self.persist()
        return len(chunk_ids)

    def search(self, query_embedding: np.ndarray, limit: int) -> list[tuple[str, float]]:
        if self.index.ntotal == 0:
            return []
        vector = self._normalize(query_embedding.reshape(1, -1))
        scores, indexes = self.index.search(vector, min(limit, self.index.ntotal))
        results: list[tuple[str, float]] = []
        for index, score in zip(indexes[0], scores[0], strict=False):
            if index < 0 or index >= len(self.mapping):
                continue
            results.append((self.mapping[index], float(score)))
        return results

    def persist(self) -> None:
        self.settings.resolved_faiss_index_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(self.index_path))
        self.mapping_path.write_text(json.dumps(self.mapping, indent=2), encoding="utf-8")

    def _load_index(self) -> faiss.Index:
        if self.index_path.exists():
            return faiss.read_index(str(self.index_path))
        return faiss.IndexFlatIP(self.settings.embedding_dimension)

    def _load_mapping(self) -> list[str]:
        if self.mapping_path.exists():
            return json.loads(self.mapping_path.read_text(encoding="utf-8"))
        return []

    def _normalize(self, embeddings: np.ndarray) -> np.ndarray:
        vectors = embeddings.astype(np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1
        return vectors / norms


def remove_vector_files(settings: Settings) -> None:
    for filename in ("logs.index", "mapping.json"):
        path: Path = settings.resolved_faiss_index_dir / filename
        if path.exists():
            path.unlink()
