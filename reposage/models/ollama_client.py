"""Ollama client for local chat completion and text embeddings."""

import json
import math
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from reposage.config import settings


class OllamaClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        chat_model: Optional[str] = None,
        embedding_model: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.chat_model = chat_model or settings.chat_model
        self.embedding_model = embedding_model or settings.embedding_model
        self.timeout = timeout

    def _post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise ConnectionError(f"Failed to communicate with Ollama at {url}: {e}")

    def is_available(self) -> bool:
        """Check if Ollama server is running and reachable."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                return resp.status == 200
        except Exception:
            return False

    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        """Single prompt text generation."""
        payload = {
            "model": model or self.chat_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if system:
            payload["system"] = system
        res = self._post("/api/generate", payload)
        return res.get("response", "")

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        """Chat completion given list of message dicts."""
        payload = {
            "model": model or self.chat_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        res = self._post("/api/chat", payload)
        return res.get("message", {}).get("content", "")

    def embeddings(
        self,
        prompt: str,
        model: Optional[str] = None,
    ) -> List[float]:
        """Generate dense vector embedding for text."""
        payload = {
            "model": model or self.embedding_model,
            "prompt": prompt,
        }
        res = self._post("/api/embeddings", payload)
        return res.get("embedding", [])


class MockOllamaClient:
    """Mock client for deterministic testing without external dependencies."""

    def __init__(self, responses: Optional[Dict[str, str]] = None, dim: int = 768):
        self.responses = responses or {}
        self.dim = dim
        self.history: List[Dict[str, Any]] = []

    def is_available(self) -> bool:
        return True

    def generate(self, prompt: str, **kwargs) -> str:
        self.history.append({"action": "generate", "prompt": prompt})
        for key, resp in self.responses.items():
            if key in prompt:
                return resp
        return "Deterministic generated summary."

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        self.history.append({"action": "chat", "messages": messages})
        content = messages[-1].get("content", "") if messages else ""
        for key, resp in self.responses.items():
            if key in content:
                return resp

        # Extract citations present in the prompt to simulate grounded LLM behavior
        citations = re.findall(
            r"\[([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]+:[0-9]+-[0-9]+)\]", content
        )
        if citations:
            if "bug-hunt" in content:
                return (
                    f"### Ranked Suspects\n"
                    f"1. **Location**: {citations[0]}\n"
                    f"   - **Why Suspect**: Logic in {citations[0]} causes unexpected expiration.\n"
                    f"   - **Evidence Present**: Directly seen at {citations[0]}.\n"
                    f"   - **Missing Evidence & Uncertainty**: Needs runtime verification."
                )
            elif "explain-file" in content:
                return (
                    f"### Purpose\nThe file implements core operations.\n\n"
                    f"### Key Symbols\n- Defined at {citations[0]}."
                )
            elif "connection" in content:
                chain = " -> ".join([f"`{c}`" for c in citations])
                return f"### Step-by-Step Call Trace\nExecution traces through {chain}."
            return f"Answer grounded in {citations[0]}."

        return "Deterministic chat answer based on retrieved evidence."

    def embeddings(self, prompt: str, **kwargs) -> List[float]:
        """Produce a deterministic normalized vector based on prompt token hashes."""
        vec = [0.0] * self.dim
        tokens = prompt.lower().split()
        for tok in tokens:
            idx = abs(hash(tok)) % self.dim
            vec[idx] += 1.0
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec
