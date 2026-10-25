"""JarvisLabs multi-model AI client with automatic fallback.

Uses the OpenAI-compatible API at JarvisLabs to provide chat and text
generation with automatic model fallback:
  1. gemma-4-31b-it  (primary)
  2. deepseek-v4.1-flash-1017  (fallback 1)
  3. glm-5.3-flash  (fallback 2)

Embeddings remain handled locally by Ollama.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

import openai
from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    InternalServerError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)

from reposage.config import settings

logger = logging.getLogger("reposage.jarvis")


@dataclass
class ModelResult:
    """Per-request metadata about which model handled the response."""

    text: str
    model_used: str
    attempted_models: List[str] = field(default_factory=list)
    fallback_used: bool = False


# ── Custom Exception Hierarchy ──────────────────────────────────────────────


class JarvisError(Exception):
    """Base exception for JarvisLabs client errors."""

    pass


class JarvisAuthError(JarvisError):
    """Invalid credentials or unauthorized (401/403). Non-retryable."""

    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.status_code = status_code


class JarvisAPIError(JarvisError):
    """HTTP/API error from the JarvisLabs endpoint."""

    def __init__(self, message: str, status_code: int = 0, body: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class JarvisConnectionError(JarvisError):
    """Network connection failure."""

    pass


class JarvisTimeoutError(JarvisError):
    """Request timed out."""

    pass


class JarvisEmptyResponseError(JarvisError):
    """Model returned an empty or whitespace-only response."""

    pass


class JarvisAllModelsFailedError(JarvisError):
    """All models in the fallback chain were attempted and failed."""

    def __init__(
        self,
        message: str,
        attempted_models: Optional[List[str]] = None,
        last_error: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.attempted_models = attempted_models or []
        self.last_error = last_error


# ── JarvisClient Implementation ─────────────────────────────────────────────


class JarvisClient:
    """OpenAI-compatible client for JarvisLabs with multi-model fallback."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model_order: Optional[List[str]] = None,
        timeout: Optional[float] = None,
        openai_client: Optional[OpenAI] = None,
    ):
        self.api_key = api_key or settings.jarvislabs_api_key
        self.base_url = (
            base_url or settings.jarvislabs_base_url
        ).rstrip("/")
        self.model_order = (
            list(model_order) if model_order is not None else list(settings.model_order)
        )
        self.timeout = float(
            timeout if timeout is not None else settings.llm_timeout
        )

        if not self.api_key:
            raise JarvisAuthError(
                "JARVISLABS_API_KEY is required. Set it in .env or environment variables."
            )

        if openai_client is not None:
            self._client = openai_client
        else:
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )

    def __repr__(self) -> str:
        # Never expose api_key in string representation
        masked = f"{self.api_key[:4]}***" if len(self.api_key) > 4 else "***"
        return (
            f"JarvisClient(base_url={self.base_url!r}, "
            f"models={self.model_order!r}, api_key={masked})"
        )

    def _call_model(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Call a single model using the OpenAI client.
        
        Translates OpenAI SDK exceptions into structured Jarvis exceptions.
        """
        extra_kwargs: Dict[str, Any] = {}
        if response_format:
            extra_kwargs["response_format"] = response_format

        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                **extra_kwargs,
            )
            choices = response.choices
            if not choices:
                raise JarvisEmptyResponseError(f"No choices returned by {model}")

            msg = choices[0].message
            content = msg.content if msg else ""
            if not content or not content.strip():
                raise JarvisEmptyResponseError(f"Empty response text from {model}")

            return content.strip()

        except AuthenticationError as e:
            # 401 - globally invalid API credentials
            raise JarvisAuthError(
                f"Authentication failed for JarvisLabs ({model}): {e}",
                status_code=401,
            ) from e

        except PermissionDeniedError as e:
            # 403 - permission denied
            raise JarvisAuthError(
                f"Permission denied for JarvisLabs ({model}): {e}",
                status_code=403,
            ) from e

        except RateLimitError as e:
            # 429 - rate limit, retry next model
            raise JarvisAPIError(
                f"Rate limit exceeded on {model}: {e}",
                status_code=429,
            ) from e

        except APITimeoutError as e:
            # Timeout
            raise JarvisTimeoutError(
                f"Request timed out for model {model} after {self.timeout}s: {e}"
            ) from e

        except APIConnectionError as e:
            # Network connection error
            raise JarvisConnectionError(
                f"Connection error reaching JarvisLabs ({model}): {e}"
            ) from e

        except InternalServerError as e:
            # 5xx error
            raise JarvisAPIError(
                f"Internal server error on {model}: {e}",
                status_code=500,
            ) from e

        except APIStatusError as e:
            code = getattr(e, "status_code", 0)
            if code in (401, 403):
                raise JarvisAuthError(
                    f"Authentication error ({code}) on {model}: {e}",
                    status_code=code,
                ) from e
            raise JarvisAPIError(
                f"HTTP {code} from JarvisLabs ({model}): {e}",
                status_code=code,
            ) from e

        except JarvisEmptyResponseError:
            raise

        except Exception as e:
            # General fallback check for timeout strings
            msg = str(e).lower()
            if "timeout" in msg or "timed out" in msg:
                raise JarvisTimeoutError(
                    f"Request timed out for {model}: {e}"
                ) from e
            raise JarvisConnectionError(f"Error calling {model}: {e}") from e

    def _call_with_fallback(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> ModelResult:
        """Execute request across models in order until a valid response is returned.

        Concurrency-safe and request-scoped: returns ModelResult without modifying
        shared state.
        Non-retryable errors (e.g. invalid API key) fail immediately without
        attempting fallback.
        """
        attempted: List[str] = []
        last_error: Optional[Exception] = None

        for model in self.model_order:
            attempted.append(model)
            try:
                logger.info("Attempting JarvisLabs model: %s", model)
                text = self._call_model(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    response_format=response_format,
                )

                fallback_used = len(attempted) > 1
                if fallback_used:
                    logger.info(
                        "Fallback succeeded: %s handled the request after failures on %s",
                        model,
                        attempted[:-1],
                    )

                return ModelResult(
                    text=text,
                    model_used=model,
                    attempted_models=list(attempted),
                    fallback_used=fallback_used,
                )

            except JarvisAuthError:
                # Do not retry on globally invalid authentication
                logger.error(
                    "JarvisLabs authentication error on model %s; aborting fallback.",
                    model,
                )
                raise

            except (
                JarvisAPIError,
                JarvisConnectionError,
                JarvisTimeoutError,
                JarvisEmptyResponseError,
            ) as e:
                logger.warning(
                    "Model %s failed with %s: %s; falling back to next model.",
                    model,
                    type(e).__name__,
                    e,
                )
                last_error = e
                continue

        # All models exhausted
        logger.error("All models in fallback chain exhausted: %s", attempted)
        raise JarvisAllModelsFailedError(
            f"All models failed: {attempted}. Last error: {last_error}",
            attempted_models=attempted,
            last_error=last_error,
        )

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        **kwargs,
    ) -> str:
        """Chat completion returning string text for drop-in OllamaClient compatibility."""
        result = self.chat_with_metadata(
            messages, temperature=temperature, **kwargs
        )
        return result.text

    def chat_with_metadata(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        response_format: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> ModelResult:
        """Chat completion returning ModelResult with model execution metadata."""
        return self._call_with_fallback(
            messages=messages,
            temperature=temperature,
            response_format=response_format,
        )

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.2,
        **kwargs,
    ) -> str:
        """Single prompt generation returning string text for drop-in compatibility."""
        result = self.generate_with_metadata(
            prompt=prompt, system=system, temperature=temperature, **kwargs
        )
        return result.text

    def generate_with_metadata(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.2,
        response_format: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> ModelResult:
        """Single prompt generation with full model execution metadata."""
        messages: List[Dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self._call_with_fallback(
            messages=messages,
            temperature=temperature,
            response_format=response_format,
        )

    def generate_json(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        """Generate structured JSON output for future architecture and visualization tools.

        Guarantees returned object is a parsed Python dictionary.
        """
        sys_prompt = (system or "") + "\nYou MUST return valid, parseable JSON only."
        result = self.generate_with_metadata(
            prompt=prompt,
            system=sys_prompt.strip(),
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        try:
            return json.loads(result.text)
        except json.JSONDecodeError:
            # Fallback regex extraction in case provider wraps in markdown code blocks
            match = re.search(r"\{.*\}", result.text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise

    def is_available(self) -> bool:
        """Check if JarvisLabs API is reachable and credentials are valid."""
        try:
            self._client.models.list()
            return True
        except Exception:
            return False


def get_llm_client(provider: Optional[str] = None):
    """Factory to get the configured LLM client.

    If REPOSAGE_LLM_PROVIDER is 'jarvislabs' (default), returns a JarvisClient.
    If JARVISLABS_API_KEY is unset, logs a notice and falls back to OllamaClient
    for local offline operation.
    """
    chosen_provider = (provider or settings.llm_provider).lower()

    if chosen_provider == "jarvislabs":
        if settings.jarvislabs_api_key:
            return JarvisClient()
        logger.warning(
            "JARVISLABS_API_KEY is not set. Falling back to local OllamaClient."
        )

    from reposage.models.ollama_client import OllamaClient
    return OllamaClient()
