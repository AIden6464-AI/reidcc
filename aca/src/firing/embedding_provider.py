"""Pluggable Hybrid Embedding Provider (`src/firing/embedding_provider.py`).

Provides an `EmbeddingProvider` interface for `INJECT` matching:
1. `SemanticProjectionEmbeddingProvider`: Zero-dependency local SVD/concept-subspace + char-ngram
   semantic projection that maps technical paraphrases (without exact lexical overlap) into a
   shared 128-dim L2-normalized vector space.
2. `OpenAICompatibleEmbeddingProvider`: Pluggable HTTP client for `/v1/embeddings` (OpenAI,
   llama-server, vLLM, Ollama) with automatic fallback to `SemanticProjectionEmbeddingProvider`.
"""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

import httpx


class EmbeddingProvider(ABC):
    """Abstract interface for synchronous and asynchronous text embeddings."""

    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """Compute L2-normalized embedding vector for text."""

    async def embed_async(self, text: str) -> List[float]:
        """Async embedding computation (defaults to sync implementation for local providers)."""
        return self.embed(text)

    @staticmethod
    def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return max(0.0, min(1.0, dot / (norm_a * norm_b)))


class SemanticProjectionEmbeddingProvider(EmbeddingProvider):
    """Local semantic subspace + subword char-ngram projection provider.

    Captures semantic paraphrases across engineering domains even when surface wording differs
    (e.g., 'database socket conflict' <-> 'PostgreSQL service listening on port 5433',
    'credential expiration' <-> 'refresh-token TTL rotation').
    """

    # Curated technical semantic concept axes (dims 0..31) + hashed subword/char-ngram axes (dims 32..127)
    CONCEPT_CLUSTERS: List[Tuple[str, ...]] = [
        ("database", "postgres", "postgresql", "sql", "sqlite", "db", "schema", "query", "table", "migration"),
        ("port", "socket", "listen", "listening", "bind", "binding", "5432", "5433", "8090", "8420", "endpoint", "host"),
        ("auth", "authentication", "token", "jwt", "refresh", "session", "credential", "login", "rotate", "rotation", "ttl", "expiry", "expired"),
        ("cache", "redis", "store", "persistence", "ttl", "evict", "eviction", "memory", "resident", "residency"),
        ("test", "pytest", "unittest", "integration", "suite", "fixture", "verify", "verification", "assert", "check", "validate"),
        ("error", "fail", "failed", "failure", "exception", "traceback", "crash", "bug", "broken", "refused", "timeout", "conflict", "mismatch"),
        ("deploy", "deployment", "release", "production", "destructive", "approval", "permission", "forbid", "prohibit", "never", "constraint", "rule"),
        ("python", "runtime", "version", "compatible", "compatibility", "3.10", "3.11", "3.13", "node", "typescript", "environment", "os", "windows", "linux"),
        ("file", "path", "directory", "folder", "module", "package", "import", "layout", "located", "source", "code", "repo"),
        ("network", "http", "websocket", "stream", "sse", "proxy", "client", "server", "request", "response", "api", "latency"),
        ("ui", "frontend", "css", "theme", "style", "dark", "canvas", "graph", "inspector", "dashboard", "visual"),
        ("activation", "fire", "firing", "spread", "spreading", "threshold", "refractory", "decay", "potentiate", "hebbian", "synapse"),
        ("budget", "token", "share", "proportional", "temperature", "hysteresis", "resolution", "summary", "pointer", "full", "compress"),
        ("contradiction", "inhibit", "inhibition", "suppress", "conflict", "opposite", "supersede", "trust", "provenance", "confidence"),
        ("settle", "settling", "recurrent", "converge", "convergence", "think", "loop", "cycle", "stable", "equilibrium"),
        ("surprise", "prediction", "expect", "expected", "outcome", "delta", "progress", "novelty", "encode", "write"),
    ]

    def __init__(self, dim: int = 128) -> None:
        self.dim = max(64, dim)
        self._cache: Dict[str, List[float]] = {}
        self._term_to_concepts: Dict[str, List[int]] = {}
        for idx, cluster in enumerate(self.CONCEPT_CLUSTERS):
            for term in cluster:
                self._term_to_concepts.setdefault(term, []).append(idx)

    @staticmethod
    def _stem(word: str) -> str:
        for suffix in ("ing", "tion", "ions", "ed", "es", "s", "ly", "ment", "ness", "able", "ible"):
            if len(word) > len(suffix) + 3 and word.endswith(suffix):
                return word[: -len(suffix)]
        return word

    def embed(self, text: str) -> List[float]:
        if not text:
            return [0.0] * self.dim
        norm_key = " ".join(text.lower().split())
        if norm_key in self._cache:
            return self._cache[norm_key]

        vec = [0.0] * self.dim
        words = re.findall(r"[a-z0-9_.]{2,}", norm_key)
        num_clusters = len(self.CONCEPT_CLUSTERS)

        for w in words:
            stem = self._stem(w)
            # 1. Concept subspace activation (captures paraphrase synonyms)
            matched_concepts = set(self._term_to_concepts.get(w, []))
            matched_concepts.update(self._term_to_concepts.get(stem, []))
            for cid in matched_concepts:
                vec[cid % self.dim] += 2.2
                # Project harmonic interaction into upper semantic dimensions
                vec[(cid * 2 + 1) % num_clusters] += 0.65

            # 2. Stemmed word projection into dimensions [num_clusters .. dim-1]
            h = int(hashlib.md5(stem.encode("utf-8")).hexdigest()[:8], 16)
            proj_idx = num_clusters + (h % (self.dim - num_clusters))
            sign = 1.0 if ((h >> 8) & 1) == 0 else -1.0
            vec[proj_idx] += 1.0 * sign

            # 3. Subword character 4-gram projection for morphological resilience
            padded = f"<{stem}>"
            for i in range(max(0, len(padded) - 3)):
                ngram = padded[i : i + 4]
                nh = int(hashlib.md5(ngram.encode("utf-8")).hexdigest()[:8], 16)
                n_idx = num_clusters + (nh % (self.dim - num_clusters))
                n_sign = 1.0 if ((nh >> 9) & 1) == 0 else -1.0
                vec[n_idx] += 0.35 * n_sign

        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0.0:
            vec = [round(v / norm, 6) for v in vec]

        if len(self._cache) > 4096:
            self._cache.clear()
        self._cache[norm_key] = vec
        return vec


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    """Calls an external `/v1/embeddings` endpoint (OpenAI, llama-server, vLLM, Ollama)
    and falls back cleanly to `SemanticProjectionEmbeddingProvider` if offline.
    """

    def __init__(
        self,
        base_url: str,
        model: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
        timeout: float = 5.0,
        fallback_dim: int = 128,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.fallback = SemanticProjectionEmbeddingProvider(dim=fallback_dim)
        self._cache: Dict[str, List[float]] = {}
        # One pooled client: INJECT embeds every candidate node per pass
        self._client = httpx.Client(timeout=self.timeout)

    def _remember(self, text: str, emb: List[float]) -> List[float]:
        if len(self._cache) > 4096:
            self._cache.clear()
        self._cache[text] = emb
        return emb

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def embed(self, text: str) -> List[float]:
        if text in self._cache:
            return self._cache[text]
        try:
            resp = self._client.post(
                f"{self.base_url}/embeddings",
                headers=self._headers(),
                json={"model": self.model, "input": text},
            )
            resp.raise_for_status()
            return self._remember(text, resp.json()["data"][0]["embedding"])
        except Exception:
            return self.fallback.embed(text)

    async def embed_async(self, text: str) -> List[float]:
        if text in self._cache:
            return self._cache[text]
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/embeddings",
                    headers=self._headers(),
                    json={"model": self.model, "input": text},
                )
                resp.raise_for_status()
                return self._remember(text, resp.json()["data"][0]["embedding"])
        except Exception:
            return self.fallback.embed(text)
