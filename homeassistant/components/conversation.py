"""Stub conversation helpers for tests."""

from __future__ import annotations

from typing import Any


async def async_set_agent(hass: Any, agent_id: str, agent: Any) -> None:
    """Register a conversation agent on Home Assistant stub."""

    agents = getattr(hass, "_conversation_agents", {})
    agents[agent_id] = agent
    hass._conversation_agents = agents


async def async_unset_agent(hass: Any, agent_id: str) -> None:
    """Remove a registered conversation agent."""

    agents = getattr(hass, "_conversation_agents", {})
    agents.pop(agent_id, None)
    hass._conversation_agents = agents
