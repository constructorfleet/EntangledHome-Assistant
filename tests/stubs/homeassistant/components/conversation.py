"""Stub conversation component for integration tests."""

from __future__ import annotations

from typing import Any


async def async_set_agent(hass: Any, agent_id: str, agent: Any) -> None:
    """Store the provided agent on ``hass`` for inspection."""

    agents = getattr(hass, "_conversation_agents", {})
    agents[agent_id] = agent
    hass._conversation_agents = agents


async def async_unset_agent(hass: Any, agent_id: str) -> None:
    """Remove the agent from the registry."""

    agents = getattr(hass, "_conversation_agents", {})
    agents.pop(agent_id, None)
    hass._conversation_agents = agents
