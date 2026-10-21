"""
AI Provider interfaces and implementations for Opsboard.
Supports pluggable embedding and LLM backends with deterministic offline fakes.
Matches docs/SYSTEM_DESIGN.md §9.3 - §9.5.
"""

from abc import ABC, abstractmethod
import hashlib
import json
import logging
import math
import re
from typing import Any, Dict, List, Optional
import httpx

from app.core.config import get_settings

logger = logging.getLogger("opsboard.ai.providers")


class EmbeddingProvider(ABC):
    """Abstract interface for document and query vector embedding."""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Vector dimensions."""
        pass

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Identifier of the underlying model."""
        pass

    @abstractmethod
    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Compute embeddings for a batch of documents."""
        pass

    @abstractmethod
    async def embed_query(self, text: str) -> List[float]:
        """Compute query embedding with any model-specific prefix applied."""
        pass


class FakeEmbeddingProvider(EmbeddingProvider):
    """
    Deterministic, offline embedding provider generating 384-dimensional unit vectors.
    Uses SHA-256 word hashing with term-frequency weighting so texts sharing
    tokens/stems have positive cosine similarity. Requires zero network calls or GPU.
    """

    def __init__(self, dimensions: int = 384, model_id: str = "BAAI/bge-small-en-v1.5"):
        self._dimensions = dimensions
        self._model_id = model_id

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model_id(self) -> str:
        return self._model_id

    def _embed_text_sync(self, text: str) -> List[float]:
        vec = [0.0] * self._dimensions
        words = re.findall(r"\w+", text.lower())
        if not words:
            # Fallback uniform unit vector
            val = 1.0 / math.sqrt(self._dimensions)
            return [val] * self._dimensions

        for word in words:
            # Deterministic hash to dimension index
            h = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16)
            idx = h % self._dimensions
            # Sign bit from secondary hash
            sign = 1.0 if (h >> 16) % 2 == 0 else -1.0
            vec[idx] += sign

        # L2 Normalize
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        else:
            val = 1.0 / math.sqrt(self._dimensions)
            vec = [val] * self._dimensions
        return vec

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_text_sync(t) for t in texts]

    async def embed_query(self, text: str) -> List[float]:
        # BGE query instruction prefix simulation
        query_text = f"Represent this sentence for searching relevant passages: {text}"
        return self._embed_text_sync(query_text)


class FastembedProvider(EmbeddingProvider):
    """
    Local ONNX CPU embedding provider using fastembed library.
    Falls back to FakeEmbeddingProvider if fastembed is unavailable.
    """

    def __init__(self, model_id: str = "BAAI/bge-small-en-v1.5"):
        self._model_id = model_id
        self._model = None
        self._fallback = FakeEmbeddingProvider(dimensions=384, model_id=model_id)
        try:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(model_name=model_id)
        except Exception as e:
            logger.info("Fastembed not available or model load deferred (%s). Using deterministic fake.", e)

    @property
    def dimensions(self) -> int:
        return 384

    @property
    def model_id(self) -> str:
        return self._model_id

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if self._model:
            embeddings = list(self._model.embed(texts))
            return [e.tolist() for e in embeddings]
        return await self._fallback.embed_documents(texts)

    async def embed_query(self, text: str) -> List[float]:
        if self._model:
            embeddings = list(self._model.embed([text]))
            return embeddings[0].tolist()
        return await self._fallback.embed_query(text)


class LLMProvider(ABC):
    """Abstract interface for grounded natural language synthesis."""

    @property
    @abstractmethod
    def model_id(self) -> str:
        pass

    @abstractmethod
    async def generate(self, prompt: str, system_prompt: str) -> str:
        """Synthesize a response grounded strictly in provided sources."""
        pass


class FakeLLMProvider(LLMProvider):
    """
    Deterministic offline LLM for unit tests and local environments without API keys.
    Parses retrieved source passages from the prompt, constructs a clear, grounded answer
    referencing [S1], [S2] markers, and strictly treats source text as untrusted data.
    """

    def __init__(self, model_id: str = "fake-grounded-v1"):
        self._model_id = model_id

    @property
    def model_id(self) -> str:
        return self._model_id

    async def generate(self, prompt: str, system_prompt: str) -> str:
        # Prompt contains sources formatted like: [S1] (PAY-101): ...
        sources = re.findall(r"\[(S\d+)\]\s*(.*?)(?=\n\[S\d+\]|\n\nQuery:|\Z)", prompt, re.DOTALL)

        if not sources:
            return "Based on the team's operational history, no relevant information was found to answer this question."

        # Synthesize from the top source
        primary_marker, primary_text = sources[0]
        primary_snippet = primary_text.strip()[:180].replace("\n", " ")

        # Look for reason / decision / explanation keywords
        answer_parts = []
        for marker, text in sources[:2]:
            clean_text = text.strip().replace("\n", " ")
            if "reason:" in clean_text.lower() or "moved" in clean_text.lower() or "decided" in clean_text.lower():
                answer_parts.append(f"Regarding the operational workflow, {clean_text[:120]} [{marker}].")
            else:
                answer_parts.append(f"According to [{marker}], {clean_text[:120]}.")

        if answer_parts:
            return " ".join(answer_parts)
        return f"Operational records show relevant details in [{primary_marker}]: {primary_snippet}."


class AnthropicProvider(LLMProvider):
    """
    Anthropic Claude 3.5 Sonnet provider with strict timeout and no-tool sandbox.
    """

    def __init__(self, api_key: str, model_id: str = "claude-3-5-sonnet-20241022"):
        self._api_key = api_key
        self._model_id = model_id
        self._client = httpx.AsyncClient(timeout=20.0)

    @property
    def model_id(self) -> str:
        return self._model_id

    async def generate(self, prompt: str, system_prompt: str) -> str:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": self._model_id,
            "max_tokens": 800,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": prompt}
            ],
        }
        resp = await self._client.post(url, headers=headers, json=body)
        if resp.status_code != 200:
            raise RuntimeError(f"Anthropic API returned status {resp.status_code}: {resp.text}")
        data = resp.json()
        return data["content"][0]["text"]


class OpenAIProvider(LLMProvider):
    """
    Standard OpenAI-compatible provider supporting OpenAI, Gemini, Groq, Ollama, etc.
    Strict 20s timeout and tool-free sandbox.
    """

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1", model_id: str = "gpt-4o-mini"):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model_id = model_id
        self._client = httpx.AsyncClient(timeout=20.0)

    @property
    def model_id(self) -> str:
        return self._model_id

    async def generate(self, prompt: str, system_prompt: str) -> str:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self._model_id,
            "max_tokens": 800,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }
        resp = await self._client.post(url, headers=headers, json=body)
        if resp.status_code != 200:
            raise RuntimeError(f"OpenAI API returned status {resp.status_code}: {resp.text}")
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def get_embedding_provider() -> EmbeddingProvider:
    """Factory to instantiate the configured EmbeddingProvider."""
    cfg = get_settings()
    if cfg.EMBEDDING_PROVIDER == "fastembed":
        return FastembedProvider(model_id=cfg.EMBEDDING_MODEL)
    return FakeEmbeddingProvider(dimensions=384, model_id=cfg.EMBEDDING_MODEL)


def get_llm_provider() -> Optional[LLMProvider]:
    """Factory to instantiate the configured LLMProvider."""
    cfg = get_settings()
    if not cfg.AI_ENABLED:
        return None
    if cfg.LLM_PROVIDER == "anthropic" and cfg.ANTHROPIC_API_KEY:
        return AnthropicProvider(api_key=cfg.ANTHROPIC_API_KEY, model_id=cfg.LLM_MODEL)
    if cfg.LLM_PROVIDER == "openai" and cfg.OPENAI_API_KEY:
        return OpenAIProvider(
            api_key=cfg.OPENAI_API_KEY,
            base_url=cfg.OPENAI_BASE_URL,
            model_id=cfg.LLM_MODEL,
        )
    if cfg.LLM_PROVIDER == "fake":
        return FakeLLMProvider()
    return None
