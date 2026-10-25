"""Automated tests for JarvisLabs multi-model fallback client and metadata tracking."""

import unittest
from unittest.mock import MagicMock, patch

import httpx
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    InternalServerError,
    PermissionDeniedError,
    RateLimitError,
)

from reposage.agent.orchestrator import RepoSageOrchestrator
from reposage.api import execute_ask_request
from reposage.config import Settings
from reposage.models.jarvis_client import (
    JarvisAllModelsFailedError,
    JarvisAuthError,
    JarvisClient,
    ModelResult,
    get_llm_client,
)
from reposage.models.ollama_client import MockOllamaClient


def make_dummy_response(content: str):
    """Helper to build a mock OpenAI chat completion response."""
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


class TestJarvisClientFallback(unittest.TestCase):
    def setUp(self):
        self.mock_openai = MagicMock()
        self.client = JarvisClient(
            api_key="test-key-12345",
            base_url="https://models.jarvislabs.net/v1",
            model_order=["gemma-4-31b-it", "deepseek-v4.1-flash-1017", "glm-5.3-flash"],
            timeout=18.0,
            openai_client=self.mock_openai,
        )

    def test_gemma_succeeds_only_gemma_called(self):
        """When Gemma succeeds, only Gemma is called and fallback is not used."""
        self.mock_openai.chat.completions.create.return_value = make_dummy_response(
            "Answer from Gemma"
        )

        result = self.client.chat_with_metadata([{"role": "user", "content": "hi"}])

        self.assertEqual(result.text, "Answer from Gemma")
        self.assertEqual(result.model_used, "gemma-4-31b-it")
        self.assertEqual(result.attempted_models, ["gemma-4-31b-it"])
        self.assertFalse(result.fallback_used)
        self.assertEqual(self.mock_openai.chat.completions.create.call_count, 1)

    def test_gemma_fails_deepseek_succeeds(self):
        """When Gemma fails with server error, DeepSeek is tried and succeeds."""
        req = httpx.Request("POST", "https://models.jarvislabs.net/v1/chat/completions")
        err = InternalServerError("Server Error 500", response=httpx.Response(500, request=req), body=None)

        self.mock_openai.chat.completions.create.side_effect = [
            err,
            make_dummy_response("Answer from DeepSeek"),
        ]

        result = self.client.chat_with_metadata([{"role": "user", "content": "hi"}])

        self.assertEqual(result.text, "Answer from DeepSeek")
        self.assertEqual(result.model_used, "deepseek-v4.1-flash-1017")
        self.assertEqual(
            result.attempted_models,
            ["gemma-4-31b-it", "deepseek-v4.1-flash-1017"],
        )
        self.assertTrue(result.fallback_used)
        self.assertEqual(self.mock_openai.chat.completions.create.call_count, 2)

    def test_gemma_and_deepseek_fail_glm_succeeds(self):
        """When Gemma and DeepSeek both fail, GLM succeeds."""
        req = httpx.Request("POST", "https://models.jarvislabs.net/v1/chat/completions")
        err_timeout = APITimeoutError(request=req)
        err_rate_limit = RateLimitError("Rate limit 429", response=httpx.Response(429, request=req), body=None)

        self.mock_openai.chat.completions.create.side_effect = [
            err_timeout,
            err_rate_limit,
            make_dummy_response("Answer from GLM"),
        ]

        result = self.client.chat_with_metadata([{"role": "user", "content": "hi"}])

        self.assertEqual(result.text, "Answer from GLM")
        self.assertEqual(result.model_used, "glm-5.3-flash")
        self.assertEqual(
            result.attempted_models,
            ["gemma-4-31b-it", "deepseek-v4.1-flash-1017", "glm-5.3-flash"],
        )
        self.assertTrue(result.fallback_used)
        self.assertEqual(self.mock_openai.chat.completions.create.call_count, 3)

    def test_all_three_models_fail(self):
        """When all models in the fallback chain fail, JarvisAllModelsFailedError is raised."""
        req = httpx.Request("POST", "https://models.jarvislabs.net/v1/chat/completions")
        err = APIConnectionError(request=req)

        self.mock_openai.chat.completions.create.side_effect = [err, err, err]

        with self.assertRaises(JarvisAllModelsFailedError) as ctx:
            self.client.chat_with_metadata([{"role": "user", "content": "hi"}])

        self.assertEqual(
            ctx.exception.attempted_models,
            ["gemma-4-31b-it", "deepseek-v4.1-flash-1017", "glm-5.3-flash"],
        )
        self.assertEqual(self.mock_openai.chat.completions.create.call_count, 3)

    def test_api_timeout_triggers_fallback(self):
        """Timeouts trigger automatic fallback to next available model."""
        req = httpx.Request("POST", "https://models.jarvislabs.net/v1/chat/completions")
        err_timeout = APITimeoutError(request=req)

        self.mock_openai.chat.completions.create.side_effect = [
            err_timeout,
            make_dummy_response("Recovered via DeepSeek"),
        ]

        result = self.client.generate_with_metadata("Explain this code")

        self.assertEqual(result.text, "Recovered via DeepSeek")
        self.assertEqual(result.model_used, "deepseek-v4.1-flash-1017")
        self.assertTrue(result.fallback_used)

    def test_http_429_and_5xx_errors_trigger_fallback(self):
        """HTTP 429 (Rate Limit) and 503 (Server Error) both cleanly trigger fallback."""
        req = httpx.Request("POST", "https://models.jarvislabs.net/v1/chat/completions")
        err429 = RateLimitError("429 Too Many Requests", response=httpx.Response(429, request=req), body=None)
        err503 = InternalServerError("503 Service Unavailable", response=httpx.Response(503, request=req), body=None)

        self.mock_openai.chat.completions.create.side_effect = [
            err429,
            err503,
            make_dummy_response("GLM handled 429+503 fallback"),
        ]

        result = self.client.chat_with_metadata([{"role": "user", "content": "test"}])

        self.assertEqual(result.model_used, "glm-5.3-flash")
        self.assertTrue(result.fallback_used)
        self.assertEqual(len(result.attempted_models), 3)

    def test_invalid_api_credentials_fail_clearly_without_fallback(self):
        """Authentication error (401) aborts immediately without attempting other models."""
        req = httpx.Request("POST", "https://models.jarvislabs.net/v1/chat/completions")
        err401 = AuthenticationError("Invalid API key", response=httpx.Response(401, request=req), body=None)

        self.mock_openai.chat.completions.create.side_effect = err401

        with self.assertRaises(JarvisAuthError):
            self.client.chat_with_metadata([{"role": "user", "content": "hi"}])

        # Must NOT attempt fallback on authentication failure
        self.assertEqual(self.mock_openai.chat.completions.create.call_count, 1)

    def test_permission_denied_fails_clearly(self):
        """Permission denied (403) aborts immediately without fallback."""
        req = httpx.Request("POST", "https://models.jarvislabs.net/v1/chat/completions")
        err403 = PermissionDeniedError("Forbidden", response=httpx.Response(403, request=req), body=None)

        self.mock_openai.chat.completions.create.side_effect = err403

        with self.assertRaises(JarvisAuthError):
            self.client.chat([{"role": "user", "content": "hi"}])

        self.assertEqual(self.mock_openai.chat.completions.create.call_count, 1)

    def test_empty_responses_trigger_fallback(self):
        """Empty or whitespace-only response from a model triggers fallback to next model."""
        empty_resp = make_dummy_response("   \n  ")
        valid_resp = make_dummy_response("Valid non-empty response")

        self.mock_openai.chat.completions.create.side_effect = [empty_resp, valid_resp]

        result = self.client.chat_with_metadata([{"role": "user", "content": "test"}])

        self.assertEqual(result.text, "Valid non-empty response")
        self.assertEqual(result.model_used, "deepseek-v4.1-flash-1017")
        self.assertTrue(result.fallback_used)
        self.assertEqual(self.mock_openai.chat.completions.create.call_count, 2)

    def test_custom_model_priority_works(self):
        """Users can configure a customized model priority order."""
        custom_client = JarvisClient(
            api_key="test-key",
            model_order=["glm-5.3-flash", "gemma-4-31b-it"],
            openai_client=self.mock_openai,
        )
        self.mock_openai.chat.completions.create.return_value = make_dummy_response("From GLM")

        res = custom_client.chat_with_metadata([{"role": "user", "content": "test"}])

        self.assertEqual(res.model_used, "glm-5.3-flash")
        self.mock_openai.chat.completions.create.assert_called_once_with(
            model="glm-5.3-flash",
            messages=[{"role": "user", "content": "test"}],
            temperature=0.2,
        )

    def test_structured_json_generation_for_visual_explorer(self):
        """JarvisClient supports structured JSON output for future visual tools."""
        json_resp = make_dummy_response('{"components": ["auth", "router"], "edges": []}')
        self.mock_openai.chat.completions.create.return_value = json_resp

        parsed = self.client.generate_json("Describe architecture")

        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed["components"], ["auth", "router"])

    def test_api_key_not_exposed_in_repr(self):
        """Sensitive API key is masked and never exposed."""
        client_repr = repr(self.client)
        self.assertNotIn("test-key-12345", client_repr)
        self.assertIn("test***", client_repr)


class TestEmbeddingsAndOrchestratorIntegration(unittest.TestCase):
    def test_ollama_embeddings_preserved(self):
        """Local embeddings through OllamaClient or MockOllamaClient work as expected."""
        mock_ollama = MockOllamaClient()
        vec = mock_ollama.embeddings("test code snippet")
        self.assertEqual(len(vec), 768)
        self.assertIsInstance(vec[0], float)

    def test_orchestrator_reports_model_metadata(self):
        """RepoSageOrchestrator populates model_used, attempted_models, and fallback_used."""
        mock_store = MagicMock()
        mock_store.get_repo.return_value = {"url": "https://github.com/org/repo", "last_commit_sha": "abc1234"}
        mock_store.audit_log.return_value = None

        mock_jarvis = MagicMock()
        mock_jarvis.chat_with_metadata.return_value = ModelResult(
            text="Analysis of the code [src/app.py:10-20]",
            model_used="deepseek-v4.1-flash-1017",
            attempted_models=["gemma-4-31b-it", "deepseek-v4.1-flash-1017"],
            fallback_used=True,
        )

        orchestrator = RepoSageOrchestrator(
            store=mock_store,
            repo_id=1,
            llm_client=mock_jarvis,
        )

        response = orchestrator.run("What does src/app.py do?")

        self.assertEqual(response.model_used, "deepseek-v4.1-flash-1017")
        self.assertEqual(
            response.attempted_models,
            ["gemma-4-31b-it", "deepseek-v4.1-flash-1017"],
        )
        self.assertTrue(response.fallback_used)

    def test_orchestrator_handles_all_models_failed_gracefully(self):
        """When all cloud models fail, orchestrator falls back to deterministic evidence synthesizer."""
        mock_store = MagicMock()
        mock_store.get_repo.return_value = {"url": "https://github.com/org/repo", "last_commit_sha": "abc1234"}
        mock_store.audit_log.return_value = None

        mock_jarvis = MagicMock()
        mock_jarvis.chat_with_metadata.side_effect = JarvisAllModelsFailedError(
            "All failed",
            attempted_models=["gemma-4-31b-it", "deepseek-v4.1-flash-1017", "glm-5.3-flash"],
        )

        orchestrator = RepoSageOrchestrator(
            store=mock_store,
            repo_id=1,
            llm_client=mock_jarvis,
        )

        response = orchestrator.run("What does src/app.py do?")

        self.assertEqual(response.model_used, "evidence-fallback")
        self.assertTrue(response.fallback_used)
        self.assertEqual(
            response.attempted_models,
            ["gemma-4-31b-it", "deepseek-v4.1-flash-1017", "glm-5.3-flash"],
        )


if __name__ == "__main__":
    unittest.main()
