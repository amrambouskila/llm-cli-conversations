"""Embedding pipeline for semantic search (Phase 5.1).

Uses all-MiniLM-L6-v2 via ONNX Runtime for local, free, 384-dim embeddings.
Model files are downloaded from HuggingFace on first use and cached.
"""

from __future__ import annotations

import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer

MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
MAX_SEQ_LENGTH = 256

_tokenizer: Tokenizer | None = None
_ort_session: ort.InferenceSession | None = None


def _ensure_model() -> tuple[Tokenizer, ort.InferenceSession]:
    """Download model files if needed and initialize tokenizer + ONNX session."""
    global _tokenizer, _ort_session
    if _tokenizer is not None and _ort_session is not None:
        return _tokenizer, _ort_session

    tokenizer_path = hf_hub_download(MODEL_ID, "tokenizer.json")
    model_path = hf_hub_download(MODEL_ID, "onnx/model.onnx")

    _tokenizer = Tokenizer.from_file(tokenizer_path)
    _tokenizer.enable_truncation(max_length=MAX_SEQ_LENGTH)
    _tokenizer.enable_padding(length=MAX_SEQ_LENGTH)

    _ort_session = ort.InferenceSession(
        model_path,
        providers=["CPUExecutionProvider"],
    )

    return _tokenizer, _ort_session


def embed_text(text: str) -> list[float]:
    """Embed a single text string into a 384-dim normalized vector."""
    tokenizer, session = _ensure_model()

    encoded = tokenizer.encode(text)
    input_ids = np.array([encoded.ids], dtype=np.int64)
    attention_mask = np.array([encoded.attention_mask], dtype=np.int64)

    feeds: dict[str, np.ndarray] = {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
    }

    # Include token_type_ids only if the model expects it
    expected_inputs = {inp.name for inp in session.get_inputs()}
    if "token_type_ids" in expected_inputs:
        feeds["token_type_ids"] = np.zeros_like(input_ids)

    outputs = session.run(None, feeds)

    # Mean pooling over token embeddings, masked by attention
    token_embeddings = outputs[0]  # (1, seq_len, 384)
    mask = attention_mask[:, :, np.newaxis].astype(np.float32)
    pooled = (token_embeddings * mask).sum(axis=1) / mask.sum(axis=1)

    # L2 normalize
    norm = np.linalg.norm(pooled, axis=1, keepdims=True)
    normalized = pooled / np.maximum(norm, 1e-12)

    return normalized[0].tolist()


def build_session_text(
    project: str,
    model: str | None,
    summary_text: str | None,
    topics: list[str],
    tools: list[str],
) -> str:
    """Build compressed session text for embedding per DESIGN.md section 3.

    Format:
        [Project: conversations] [Model: opus] [Tools: Bash, Edit, Read]
        [Topics: semantic search, FastAPI] User asked about...
    """
    parts: list[str] = []

    if project:
        parts.append(f"[Project: {project}]")
    if model:
        parts.append(f"[Model: {model}]")
    if tools:
        parts.append(f"[Tools: {', '.join(sorted(set(tools)))}]")
    if topics:
        parts.append(f"[Topics: {', '.join(topics)}]")
    if summary_text:
        parts.append(summary_text[:500])

    return " ".join(parts)