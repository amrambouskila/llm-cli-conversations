"""Unit tests for embed.embed_text and embed.build_session_text.

The real ONNX model is NEVER downloaded — every external dependency
(hf_hub_download, Tokenizer, onnxruntime.InferenceSession) is monkeypatched
so the tests run offline and deterministically.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

import embed

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _FakeEncoded:
    """Mimics the tokenizers.Encoding object embed_text consumes."""

    def __init__(self, length: int = 10) -> None:
        self.ids = list(range(length))
        self.attention_mask = [1] * length


def _make_fake_session(seq_len: int = 10, expected_inputs=None) -> MagicMock:
    """Return a mock onnxruntime.InferenceSession.

    Output shape (1, seq_len, 384) of all 1.0s — after mean-pool + L2 norm
    every element of the result equals 1/sqrt(384).
    """
    session = MagicMock()
    inputs = []
    for name in expected_inputs or ["input_ids", "attention_mask"]:
        inp = MagicMock()
        inp.name = name
        inputs.append(inp)
    session.get_inputs.return_value = inputs
    session.run.return_value = [np.ones((1, seq_len, 384), dtype=np.float32)]
    return session


@pytest.fixture
def patched_model(monkeypatch):
    """Pre-patch embed._tokenizer and embed._ort_session with mocks."""
    fake_tokenizer = MagicMock()
    fake_tokenizer.encode.return_value = _FakeEncoded(length=10)
    fake_session = _make_fake_session(seq_len=10)
    monkeypatch.setattr(embed, "_tokenizer", fake_tokenizer)
    monkeypatch.setattr(embed, "_ort_session", fake_session)
    return fake_tokenizer, fake_session


# ---------------------------------------------------------------------------
# _ensure_model — cache + lazy init paths
# ---------------------------------------------------------------------------

def test_ensure_model_returns_cached_when_already_initialized(monkeypatch):
    fake_tokenizer = MagicMock()
    fake_session = MagicMock()
    monkeypatch.setattr(embed, "_tokenizer", fake_tokenizer)
    monkeypatch.setattr(embed, "_ort_session", fake_session)
    # If the cached path is taken, hf_hub_download must NOT be invoked.
    monkeypatch.setattr(
        embed, "hf_hub_download",
        MagicMock(side_effect=AssertionError("should not download when cached")),
    )

    tokenizer, session = embed._ensure_model()
    assert tokenizer is fake_tokenizer
    assert session is fake_session


def test_ensure_model_lazy_initializes(monkeypatch):
    """When globals are None, _ensure_model downloads + builds tokenizer + session."""
    monkeypatch.setattr(embed, "_tokenizer", None)
    monkeypatch.setattr(embed, "_ort_session", None)

    download_calls = []

    def _fake_download(repo_id, filename):
        download_calls.append((repo_id, filename))
        return f"/fake/path/{filename}"

    fake_tokenizer = MagicMock()
    fake_session = MagicMock()
    monkeypatch.setattr(embed, "hf_hub_download", _fake_download)
    monkeypatch.setattr(embed, "Tokenizer", MagicMock(from_file=MagicMock(return_value=fake_tokenizer)))
    monkeypatch.setattr(embed.ort, "InferenceSession", MagicMock(return_value=fake_session))

    tokenizer, session = embed._ensure_model()

    assert tokenizer is fake_tokenizer
    assert session is fake_session
    assert (embed.MODEL_ID, "tokenizer.json") in download_calls
    assert (embed.MODEL_ID, "onnx/model.onnx") in download_calls
    fake_tokenizer.enable_truncation.assert_called_once_with(max_length=embed.MAX_SEQ_LENGTH)
    fake_tokenizer.enable_padding.assert_called_once_with(length=embed.MAX_SEQ_LENGTH)


def test_ensure_model_uses_cpu_provider(monkeypatch):
    monkeypatch.setattr(embed, "_tokenizer", None)
    monkeypatch.setattr(embed, "_ort_session", None)

    monkeypatch.setattr(embed, "hf_hub_download", lambda *a, **kw: "/fake/path")
    monkeypatch.setattr(embed, "Tokenizer", MagicMock(from_file=MagicMock(return_value=MagicMock())))
    inference_mock = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(embed.ort, "InferenceSession", inference_mock)

    embed._ensure_model()

    inference_mock.assert_called_once_with("/fake/path", providers=["CPUExecutionProvider"])


# ---------------------------------------------------------------------------
# embed_text
# ---------------------------------------------------------------------------

def test_embed_text_returns_list_of_384_floats(patched_model):
    result = embed.embed_text("hello world")
    assert isinstance(result, list)
    assert len(result) == embed.EMBEDDING_DIM
    assert all(isinstance(v, float) for v in result)


def test_embed_text_output_is_l2_normalized(patched_model):
    result = embed.embed_text("hello world")
    norm = sum(v * v for v in result) ** 0.5
    assert abs(norm - 1.0) < 1e-5


def test_embed_text_uniform_input_yields_uniform_output(patched_model):
    """All-1s pooled vector → all-equal normalized output (1/sqrt(384) each)."""
    result = embed.embed_text("anything")
    expected = 1.0 / (embed.EMBEDDING_DIM ** 0.5)
    for v in result:
        assert abs(v - expected) < 1e-5


def test_embed_text_includes_token_type_ids_when_model_expects(monkeypatch):
    fake_tokenizer = MagicMock()
    fake_tokenizer.encode.return_value = _FakeEncoded(length=8)
    fake_session = _make_fake_session(
        seq_len=8,
        expected_inputs=["input_ids", "attention_mask", "token_type_ids"],
    )
    monkeypatch.setattr(embed, "_tokenizer", fake_tokenizer)
    monkeypatch.setattr(embed, "_ort_session", fake_session)

    embed.embed_text("hi")

    feeds = fake_session.run.call_args.args[1]
    assert "token_type_ids" in feeds
    assert feeds["token_type_ids"].shape == feeds["input_ids"].shape
    # token_type_ids should be all zeros for single-segment input
    assert (feeds["token_type_ids"] == 0).all()


def test_embed_text_omits_token_type_ids_when_not_expected(patched_model):
    _, session = patched_model
    embed.embed_text("hi")
    feeds = session.run.call_args.args[1]
    assert "token_type_ids" not in feeds
    assert "input_ids" in feeds
    assert "attention_mask" in feeds


def test_embed_text_empty_string(monkeypatch):
    """Empty input still produces a 384-dim vector (tokenizer pads to MAX_SEQ_LENGTH)."""
    fake_tokenizer = MagicMock()
    # Real tokenizer with enable_padding still emits padding tokens (mask=0)
    # Use mask=1 for the very first slot (CLS-like) so mean-pool denominator > 0
    encoded = _FakeEncoded(length=embed.MAX_SEQ_LENGTH)
    encoded.attention_mask = [1] + [0] * (embed.MAX_SEQ_LENGTH - 1)
    fake_tokenizer.encode.return_value = encoded
    fake_session = _make_fake_session(seq_len=embed.MAX_SEQ_LENGTH)
    monkeypatch.setattr(embed, "_tokenizer", fake_tokenizer)
    monkeypatch.setattr(embed, "_ort_session", fake_session)

    result = embed.embed_text("")
    assert len(result) == embed.EMBEDDING_DIM
    assert abs(sum(v * v for v in result) ** 0.5 - 1.0) < 1e-5


def test_embed_text_long_input_truncated_by_tokenizer(monkeypatch):
    """The tokenizer's enable_truncation handles long input — embed_text just trusts it."""
    fake_tokenizer = MagicMock()
    fake_tokenizer.encode.return_value = _FakeEncoded(length=embed.MAX_SEQ_LENGTH)
    fake_session = _make_fake_session(seq_len=embed.MAX_SEQ_LENGTH)
    monkeypatch.setattr(embed, "_tokenizer", fake_tokenizer)
    monkeypatch.setattr(embed, "_ort_session", fake_session)

    long_text = "word " * 5000
    result = embed.embed_text(long_text)

    assert len(result) == embed.EMBEDDING_DIM
    # tokenizer.encode received the full string — truncation happens inside it
    fake_tokenizer.encode.assert_called_once_with(long_text)


def test_embed_text_feeds_use_int64(patched_model):
    _, session = patched_model
    embed.embed_text("hello")
    feeds = session.run.call_args.args[1]
    assert feeds["input_ids"].dtype == np.int64
    assert feeds["attention_mask"].dtype == np.int64


# ---------------------------------------------------------------------------
# build_session_text
# ---------------------------------------------------------------------------

def test_build_session_text_full_inputs():
    out = embed.build_session_text(
        project="conversations",
        model="opus",
        summary_text="Worked on docker auth",
        topics=["docker", "auth"],
        tools=["Bash", "Edit", "Read"],
    )
    assert "[Project: conversations]" in out
    assert "[Model: opus]" in out
    assert "[Tools: Bash, Edit, Read]" in out
    assert "[Topics: docker, auth]" in out
    assert "Worked on docker auth" in out


def test_build_session_text_missing_topics():
    out = embed.build_session_text("p", "m", "summary", [], ["Bash"])
    assert "[Topics:" not in out
    assert "[Project: p]" in out
    assert "[Tools: Bash]" in out


def test_build_session_text_missing_tools():
    out = embed.build_session_text("p", "m", "summary", ["t1"], [])
    assert "[Tools:" not in out
    assert "[Topics: t1]" in out


def test_build_session_text_missing_model():
    out = embed.build_session_text("p", None, "summary", [], [])
    assert "[Model:" not in out
    assert "[Project: p]" in out


def test_build_session_text_missing_summary():
    out = embed.build_session_text("p", "m", None, [], [])
    assert "[Project: p] [Model: m]" == out


def test_build_session_text_missing_project():
    out = embed.build_session_text("", "m", "summary", [], [])
    assert "[Project:" not in out
    assert "[Model: m]" in out


def test_build_session_text_all_missing():
    assert embed.build_session_text("", None, None, [], []) == ""


def test_build_session_text_summary_truncated_to_500_chars():
    long_summary = "x" * 600
    out = embed.build_session_text("", None, long_summary, [], [])
    # Only first 500 chars of the summary should appear
    assert "x" * 500 in out
    assert "x" * 501 not in out


def test_build_session_text_tools_dedupe_and_sort():
    out = embed.build_session_text("", None, None, [], ["Edit", "Bash", "Edit"])
    assert "[Tools: Bash, Edit]" in out


def test_build_session_text_topics_order_preserved():
    out = embed.build_session_text("", None, None, ["zeta", "alpha"], [])
    # topics are joined as-is, not sorted
    assert "[Topics: zeta, alpha]" in out
