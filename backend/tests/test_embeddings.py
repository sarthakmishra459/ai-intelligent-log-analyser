import numpy as np
from app.services.embeddings import DeterministicEmbeddingProvider


def test_deterministic_embeddings_are_normalized_and_stable():
    provider = DeterministicEmbeddingProvider(64)
    first = provider.embed_texts(["connection refused upstream 502"])
    second = provider.embed_texts(["connection refused upstream 502"])
    assert first.shape == (1, 64)
    assert np.allclose(first, second)
    assert np.isclose(np.linalg.norm(first[0]), 1.0)
