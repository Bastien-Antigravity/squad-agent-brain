#!/usr/bin/env python
# coding:utf-8

import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import sys
from pathlib import Path
import asyncio

# Resolve paths so we can import src.*
_self_dir = Path(__file__).resolve().parent.parent
if str(_self_dir) not in sys.path:
    sys.path.insert(0, str(_self_dir))

# Enforce environment bootstrapping
import src.bootstrap as bootstrap

from src.interfaces import SquadEventBus, LocalEventBus, DualSquadEventBus, EventDeduplicator
from microservice_toolbox.messaging.config import NatsConfig


class TestEventDeduplicator(unittest.TestCase):
    def setUp(self):
        # Reset internal state before each test
        EventDeduplicator._seen = set()
        EventDeduplicator._seen_list = []

    def test_deduplication(self):
        self.assertFalse(EventDeduplicator.is_duplicate("evt-1"))
        self.assertTrue(EventDeduplicator.is_duplicate("evt-1"))
        self.assertFalse(EventDeduplicator.is_duplicate("evt-2"))
        
        # Test None/empty checks
        self.assertFalse(EventDeduplicator.is_duplicate(""))


class TestLocalEventBus(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Reset subscribers before each test
        LocalEventBus._subscribers = None
        EventDeduplicator._seen = set()
        EventDeduplicator._seen_list = []

    async def test_pub_sub_direct(self):
        received = []
        async def cb(payload):
            received.append(payload)

        LocalEventBus.subscribe("my.custom.topic", cb)
        LocalEventBus.publish("my.custom.topic", {"event_id": "1", "data": "hello"})
        
        # Allow event loop turns to execute tasks
        await asyncio.sleep(0.01)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["data"], "hello")

    async def test_tag_routing_orchestrator_mention(self):
        received = []
        async def orchestrator_cb(payload):
            received.append(payload)

        # Register handler for orchestrator agent channel
        LocalEventBus.subscribe("antigravity.squad.chat", orchestrator_cb, role="orchestrator")
        
        # Publish user message mentioning @orchestrator
        payload = {
            "event_id": "evt-tag-1",
            "sender": "user",
            "content": "Hello @orchestrator, please audit the project."
        }
        LocalEventBus.publish("antigravity.squad.chat", payload)
        
        await asyncio.sleep(0.01)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["event_id"], "evt-tag-1")

    async def test_tag_routing_fallback_orchestrator(self):
        received = []
        async def orchestrator_cb(payload):
            received.append(payload)

        # Register handler for orchestrator agent channel
        LocalEventBus.subscribe("antigravity.squad.chat", orchestrator_cb, role="orchestrator")
        
        # Publish user message WITHOUT any mentions (should default route to orchestrator)
        payload = {
            "event_id": "evt-tag-2",
            "sender": "user",
            "content": "Perform sanity checks."
        }
        LocalEventBus.publish("antigravity.squad.chat", payload)
        
        await asyncio.sleep(0.01)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["event_id"], "evt-tag-2")


class TestDualSquadEventBus(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.logger = MagicMock()

    @patch("src.interfaces.interfaces.nats_connect", new_callable=AsyncMock)
    async def test_connect_success(self, mock_connect):
        # Setup mock NATS client returned by connection wrapper
        mock_nc = AsyncMock()
        mock_connect.return_value = mock_nc

        cfg = NatsConfig(servers=["nats://127.0.0.1:4222"], client_id="test_squad")
        bus = DualSquadEventBus(cfg, self.logger)
        
        await bus.connect()
        self.assertTrue(bus.nats_connected)
        self.assertEqual(bus.nc, mock_nc)

    @patch("src.interfaces.interfaces.nats_connect", side_effect=Exception("Connection Refused"))
    async def test_connect_offline_fallback(self, mock_connect):
        cfg = NatsConfig(servers=["nats://127.0.0.1:4222"], client_id="test_squad")
        bus = DualSquadEventBus(cfg, self.logger)
        
        await bus.connect()
        self.assertFalse(bus.nats_connected)
        self.assertIsNone(bus.nc)
        self.logger.warning.assert_called_once()

    async def test_config_legacy_string_compatibility(self):
        # Assert legacy string urls are handled and converted to NatsConfig
        bus = DualSquadEventBus("nats://my-nats-host:4222", self.logger)
        self.assertIsInstance(bus.cfg, NatsConfig)
        self.assertEqual(bus.cfg.servers, ["nats://my-nats-host:4222"])
        self.assertEqual(bus.cfg.client_id, "python_agent_squad")


if __name__ == "__main__":
    unittest.main()
