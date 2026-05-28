from __future__ import annotations

import ollama


def embed_with_local_llm(text: str, model: str = "llama3.2:1b", ollama_base_url: str = "http://127.0.0.1:11434") -> list[float]:
    client = ollama.Client(host=ollama_base_url)
    response = client.embed(
        model=model,
        input=text,
        options={"num_gpu": 1},
    )
    embeddings = response.get("embeddings", [])
    if not embeddings:
        raise RuntimeError(f"No embeddings returned for model '{model}'")
    return [float(x) for x in embeddings[0]]
