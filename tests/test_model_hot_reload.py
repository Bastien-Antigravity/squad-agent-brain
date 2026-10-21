# =============================================================================
# ESSENTIAL PROCESS: Squad Agent Model Hot-Reload Verification
# DATA FLOW: Config Dynamic Capability Update -> Agent _refresh_llm_config -> Active Model Update
# KEY PARAMETERS: gemini_model, thinking_level, hot-reload without restart
# =============================================================================

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import sys
from pathlib import Path

# Resolve paths so we can import src.*
_self_dir = Path(__file__).resolve().parent.parent
if str(_self_dir) not in sys.path:
    sys.path.insert(0, str(_self_dir))

from src.agents.base_agent import BaseAgent
from google.genai import errors


class MockConfig:
    def __init__(self, data=None):
        self.data = data or {
            "capabilities": {
                "squad_agent": {
                    "gemini_model": "gemini-3.8-flash",
                    "thinking_level": "high",
                }
            }
        }
        self.live_cb = None

    def on_live_conf_update(self, cb):
        self.live_cb = cb

    def decrypt_secret(self, val):
        return val


@pytest.fixture
def mock_agent():
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock()
    mock_logger = MagicMock()
    config = MockConfig()

    agent = BaseAgent(
        role_name="architect",
        prompt_file="architect.md",
        event_bus=mock_bus,
        pg_pool=None,
        logger=mock_logger,
        config=config,
    )
    return agent, config


def test_initial_model_default(mock_agent):
    agent, _ = mock_agent
    assert agent.model_name == "gemini-3.8-flash"
    assert agent.thinking_level == "high"


def test_hot_reload_model_without_restart(mock_agent):
    agent, config = mock_agent
    assert agent.model_name == "gemini-3.8-flash"

    # Simulate dynamic config update pushed from config-server
    config.data["capabilities"]["squad_agent"]["gemini_model"] = "gemini-4-flash"
    config.data["capabilities"]["squad_agent"]["thinking_level"] = "medium"

    # Trigger refresh
    agent._refresh_llm_config()

    assert agent.model_name == "gemini-4-flash"
    assert agent.thinking_level == "medium"


def test_hot_reload_via_live_conf_update_callback(mock_agent):
    agent, config = mock_agent
    assert config.live_cb is not None

    # Update config data and invoke callback as config-server sync does
    config.data["capabilities"]["squad_agent"]["gemini_model"] = "gemini-2.5-pro"
    config.live_cb(config.data)

    assert agent.model_name == "gemini-2.5-pro"


import asyncio


def test_online_model_not_found_reporting(mock_agent):
    agent, _ = mock_agent
    agent.client = MagicMock()
    
    # Simulate APIError 404 (model not found online)
    api_err = errors.APIError(404, {"error": {"message": "models/non-existent-model is not found"}})
    agent.client.models.generate_content.side_effect = api_err

    with patch.object(agent, "_fetch_history", new_callable=AsyncMock) as mock_hist:
        mock_hist.return_value = [{"sender": "user", "content": "hello"}]
        asyncio.run(agent.think_and_respond("session-123"))

    agent.event_bus.publish.assert_called_once()
    published_payload = agent.event_bus.publish.call_args[0][1]
    assert "❌ [Model Error]" in published_payload["content"]
    assert "was not found online on Google AI Studio" in published_payload["content"]
