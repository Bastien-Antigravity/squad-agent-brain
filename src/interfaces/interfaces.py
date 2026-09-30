#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Provides the SquadEventBus interface and DualSquadEventBus concrete class
routing multi-agent communications via NATS or LocalEventBus in offline mode.

DATA FLOW:
1. Receives connection request to NATS server via microservice_toolbox.
2. If NATS is available, connects and delegates publish/subscribe to NATS channels.
3. If NATS is unavailable or fails, gracefully falls back to in-memory LocalEventBus.
4. Deduplicates event IDs via EventDeduplicator.

KEY PARAMETERS:
- nats_cfg: NatsConfig instance or connection string URI.
- logger: UniLog or compatible ILogger instance.
"""

import json
import asyncio
import uuid
import re
from typing import Dict, Any, List, Callable, Awaitable, Optional
from microservice_toolbox.messaging.config import NatsConfig
from microservice_toolbox.messaging.connector import connect as nats_connect

# -----------------------------------------------------------------------------

class SquadEventBus:
    """Abstract interface defining the pub/sub event bus contract for AI squad coordination."""

    # -----------------------------------------------------------------------------

    async def connect(self) -> None:
        """Initializes connection to the underlying message bus."""
        raise NotImplementedError

    # -----------------------------------------------------------------------------

    async def publish(self, topic: str, payload: Dict[str, Any]) -> None:
        """Broadcasts a payload JSON dictionary onto a topic channel."""
        raise NotImplementedError

    # -----------------------------------------------------------------------------

    async def subscribe(self, topic: str, callback: Callable[[Dict[str, Any]], Awaitable[None]], role: Optional[str] = None) -> None:
        """Registers a non-blocking async callback listener for a topic channel."""
        raise NotImplementedError

    # -----------------------------------------------------------------------------

    async def close(self) -> None:
        """Cleans up resources and disconnects from the transit layer."""
        raise NotImplementedError

# -----------------------------------------------------------------------------

class EventDeduplicator:
    _seen = set()
    _seen_list = []
    MAX_SIZE = 1000

    # -----------------------------------------------------------------------------

    @classmethod
    def is_duplicate(cls, event_id: str) -> bool:
        if not event_id:
            return False
        if event_id in cls._seen:
            return True
        cls._seen.add(event_id)
        cls._seen_list.append(event_id)
        if len(cls._seen_list) > cls.MAX_SIZE:
            oldest = cls._seen_list.pop(0)
            cls._seen.discard(oldest)
            return False
        return False

# -----------------------------------------------------------------------------

class LocalEventBus:
    """In-memory fallback event bus for NATS-offline/local testing."""
    _subscribers = None

    # -----------------------------------------------------------------------------

    @classmethod
    def _get_subscribers(cls):
        if cls._subscribers is None:
            cls._subscribers = {}
        return cls._subscribers

    # -----------------------------------------------------------------------------

    @classmethod
    def subscribe(cls, topic: str, callback: Callable[[Dict[str, Any]], Awaitable[None]], role: Optional[str] = None):
        subs = cls._get_subscribers()
        topics_to_sub = []
        if topic == "antigravity.squad.chat" and role:
            topics_to_sub.append(f"{topic}.broadcast")
            topics_to_sub.append(f"{topic}.agent.{role}")
        elif topic == "antigravity.squad.chat" and not role:
            topics_to_sub.append(f"{topic}.*")
        else:
            topics_to_sub.append(topic)
            
        for t in topics_to_sub:
            if t not in subs:
                subs[t] = []
            subs[t].append(callback)

    # -----------------------------------------------------------------------------

    @classmethod
    def publish(cls, topic: str, payload: Dict[str, Any]):
        # Deduplicate local events
        event_id = payload.get("event_id")
        if event_id and EventDeduplicator.is_duplicate(event_id):
            return

        # Map targets for local fallback
        targets = []
        if topic == "antigravity.squad.chat":
            content = payload.get("content", "").lower()
            sender = payload.get("sender")
            
            tags = re.findall(r'@([a-zA-Z0-9_-]+)', content)
            for tag in tags:
                role = tag.lower()
                targets.append(f"antigravity.squad.chat.agent.{role}")
                
            if sender == "user" and "orchestrator" not in tags:
                targets.append("antigravity.squad.chat.agent.orchestrator")
                
            if not targets:
                targets.append("antigravity.squad.chat.broadcast")
        else:
            targets = [topic]

        subs = cls._get_subscribers()
        callbacks_to_trigger = []
        for target in targets:
            callbacks_to_trigger.extend(subs.get(target, []))
            
        # Also trigger subscribers of wildcard or base topic
        if topic == "antigravity.squad.chat":
            callbacks_to_trigger.extend(subs.get("antigravity.squad.chat.*", []))
            callbacks_to_trigger.extend(subs.get("antigravity.squad.chat", []))

        # Deduplicate callbacks
        seen_cbs = set()
        unique_cbs = []
        for cb in callbacks_to_trigger:
            if cb not in seen_cbs:
                seen_cbs.add(cb)
                unique_cbs.append(cb)

        for cb in unique_cbs:
            try:
                asyncio.create_task(cb(payload))
            except Exception:
                pass

# -----------------------------------------------------------------------------

class DualSquadEventBus(SquadEventBus):
    """
    Unified hybrid event bus that attempts NATS broker routing but cleanly falls back
    to in-memory LocalEventBus if NATS is offline, avoiding noisy traceback logs.
    """

    # -----------------------------------------------------------------------------

    def __init__(self, nats_cfg: Any, logger: Any):
        self.logger = logger
        self.nc = None
        self.nats_connected = False
        if isinstance(nats_cfg, str):
            self.cfg = NatsConfig(
                servers=[nats_cfg],
                client_id="python_agent_squad",
                subject_prefix="antigravity",
                connect_timeout=0.5,
                reconnect_wait=1.0,
                max_reconnects=1
            )
        else:
            self.cfg = nats_cfg

    # -----------------------------------------------------------------------------

    async def connect(self) -> None:
        """Attempts a resilient connection to NATS, falling back to Local otherwise."""
        try:
            self.nc = await nats_connect(self.cfg, logger=self.logger)
            self.nats_connected = True
        except Exception as e:
            self.logger.warning(f"SquadEventBus: NATS connection failed ({e}). Falling back to in-memory LocalEventBus.")
            self.nats_connected = False
            if self.nc:
                try:
                    await self.nc.close()
                except Exception:
                    pass

    # -----------------------------------------------------------------------------

    async def publish(self, topic: str, payload: Dict[str, Any]) -> None:
        """Routes message broadcast depending on NATS connection state."""
        if "event_id" not in payload:
            payload["event_id"] = str(uuid.uuid4())

        if self.nats_connected:
            # Determine NATS subjects to publish to
            targets = []
            if topic == "antigravity.squad.chat":
                content = payload.get("content", "").lower()
                sender = payload.get("sender")
                
                tags = re.findall(r'@([a-zA-Z0-9_-]+)', content)
                for tag in tags:
                    role = tag.lower()
                    targets.append(f"antigravity.squad.chat.agent.{role}")
                    
                if sender == "user" and "orchestrator" not in tags:
                    targets.append("antigravity.squad.chat.agent.orchestrator")
                    
                if not targets:
                    targets.append("antigravity.squad.chat.broadcast")
            else:
                targets = [topic]

            try:
                for target_subject in targets:
                    await self.nc.publish(target_subject, json.dumps(payload).encode("utf-8"))
            except Exception as e:
                self.logger.error(f"SquadEventBus failed to publish to NATS: {e}. Falling back to Local.")
                LocalEventBus.publish(topic, payload)
        else:
            LocalEventBus.publish(topic, payload)

    # -----------------------------------------------------------------------------

    async def subscribe(self, topic: str, callback: Callable[[Dict[str, Any]], Awaitable[None]], role: Optional[str] = None) -> None:
        """Subscribes callback to the correct event provider."""
        # Always register local fallback subscription to ensure seamless offline state routing
        LocalEventBus.subscribe(topic, callback, role)
        
        if self.nats_connected:
            async def nats_callback(msg):
                try:
                    payload = json.loads(msg.data.decode("utf-8"))
                    # Deduplicate NATS events
                    event_id = payload.get("event_id")
                    if event_id and EventDeduplicator.is_duplicate(event_id):
                        return
                    await callback(payload)
                except Exception as e:
                    self.logger.error(f"SquadEventBus subscriber failed to process NATS payload: {e}")
            
            topics_to_sub = []
            if topic == "antigravity.squad.chat" and role:
                topics_to_sub.append(f"{topic}.broadcast")
                topics_to_sub.append(f"{topic}.agent.{role}")
            elif topic == "antigravity.squad.chat" and not role:
                topics_to_sub.append(f"{topic}.*")
            else:
                topics_to_sub.append(topic)

            for t in topics_to_sub:
                try:
                    await self.nc.subscribe(t, cb=nats_callback)
                    self.logger.info(f"SquadEventBus subscribed to NATS topic '{t}'")
                except Exception as e:
                    self.logger.error(f"SquadEventBus failed NATS subscription to '{t}': {e}")

    # -----------------------------------------------------------------------------

    async def close(self) -> None:
        """Closes connection cleanly."""
        if self.nats_connected:
            try:
                await self.nc.close()
            except Exception:
                pass
            self.nats_connected = False
