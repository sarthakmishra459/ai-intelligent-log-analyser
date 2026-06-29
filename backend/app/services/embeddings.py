import hashlib
import logging
from abc import ABC, abstractmethod

import numpy as np

from app.core.config import Settings

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_texts(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError


class DeterministicEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimension: int) -> None:
        self.dimension = dimension

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), self.dimension), dtype=np.float32)
        for row, text in enumerate(texts):
            tokens = self._tokens(text)
            for token in tokens:
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimension
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vectors[row, index] += sign
            norm = np.linalg.norm(vectors[row])
            if norm > 0:
                vectors[row] /= norm
        return vectors

    def _tokens(self, text: str) -> list[str]:
        return [token.lower() for token in text.replace("/", " ").replace("_", " ").split() if token.strip()]


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    def __init__(self, settings: Settings) -> None:
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(settings.embedding_model)

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, normalize_embeddings=True).astype(np.float32)


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, settings: Settings) -> None:
        from langchain_openai import OpenAIEmbeddings

        self.client = OpenAIEmbeddings(model=settings.openai_embedding_model, api_key=settings.openai_api_key)

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        vectors = self.client.embed_documents(texts)
        return np.asarray(vectors, dtype=np.float32)


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.should_use_openai_embeddings:
        return OpenAIEmbeddingProvider(settings)
    if settings.embedding_provider == "local":
        try:
            return SentenceTransformerEmbeddingProvider(settings)
        except Exception as exc:
            logger.warning("Falling back to deterministic embeddings: %s", exc)
    return DeterministicEmbeddingProvider(settings.embedding_dimension)
