from __future__ import annotations

import hashlib
import logging
import math

import ollama


logger = logging.getLogger(__name__)


def embed_text(text: str, dimensions: int = 16, model: str = "nomic-embed-text", ollama_base_url: str = "http://127.0.0.1:11434") -> list[float]:
    try:
        client = ollama.Client(host=ollama_base_url)
        data = client.embed(model=model, input=text)
        emb = data.get("embeddings", [None])[0]
        if isinstance(emb, list) and emb:
            return [float(x) for x in emb]
    except Exception as exc:
        logger.warning("Falling back to deterministic embedding for model '%s': %s", model, exc)

    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vals = [digest[i % len(digest)] / 255.0 for i in range(dimensions)]
    norm = math.sqrt(sum(v * v for v in vals)) or 1.0
    return [v / norm for v in vals]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))
