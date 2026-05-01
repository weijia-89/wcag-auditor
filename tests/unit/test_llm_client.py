# B5: OllamaClient size cap. Patches the lazy ollama import so these tests
# never need a real Ollama server.
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from wcag_auditor.models import ImpactLevel, ViolationInput


def _violation() -> ViolationInput:
    return ViolationInput(
        id="image-alt",
        description="Images must have alt text",
        help_url="https://example.com/image-alt",
        impact=ImpactLevel.CRITICAL,
        nodes=[{"html": "<img src='x'>"}],
        wcag_criterion="1.1.1",
    )


class TestOllamaClientSizeCap:
    def test_rejects_oversized_response(self) -> None:
        fake_ollama_module = MagicMock()
        fake_client = MagicMock()
        fake_response = MagicMock()
        # one byte over the 64KB cap
        fake_response.message.content = "x" * 65_001
        fake_client.chat.return_value = fake_response
        fake_ollama_module.Client.return_value = fake_client

        with patch.dict("sys.modules", {"ollama": fake_ollama_module}):
            from wcag_auditor.llm_client import OllamaClient
            client = OllamaClient(model="dummy")

            with pytest.raises(ValueError, match="LLM response too large"):
                client.generate_fix(_violation(), html_context="", file_path="x.html")

    def test_rejects_none_response(self) -> None:
        fake_ollama_module = MagicMock()
        fake_client = MagicMock()
        fake_response = MagicMock()
        fake_response.message.content = None
        fake_client.chat.return_value = fake_response
        fake_ollama_module.Client.return_value = fake_client

        with patch.dict("sys.modules", {"ollama": fake_ollama_module}):
            from wcag_auditor.llm_client import OllamaClient
            client = OllamaClient(model="dummy")

            with pytest.raises(ValueError, match="LLM response had no content"):
                client.generate_fix(_violation(), html_context="", file_path="x.html")

    def test_accepts_reasonable_response(self) -> None:
        fake_ollama_module = MagicMock()
        fake_client = MagicMock()
        fake_response = MagicMock()
        fake_response.message.content = (
            '{"element_selector":"img","original_html":"<img>","fix_html":"<img alt=\'x\'>",'
            '"fix_explanation":"Add alt","wcag_criterion":"1.1.1","impact":"critical",'
            '"explanation":"ok","confidence_score":0.9}'
        )
        fake_client.chat.return_value = fake_response
        fake_ollama_module.Client.return_value = fake_client

        with patch.dict("sys.modules", {"ollama": fake_ollama_module}):
            from wcag_auditor.llm_client import OllamaClient
            client = OllamaClient(model="dummy")
            result = client.generate_fix(_violation(), html_context="", file_path="x.html")
            assert result.rule_id == "image-alt"
            assert result.confidence_score == 0.9
