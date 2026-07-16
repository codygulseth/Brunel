from .interfaces import Agent


class AgentRegistry:
    """Allows new agents to be added without modifying consumers."""

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def register(self, agent: Agent) -> None:
        if agent.name in self._agents:
            raise ValueError(f"Agent already registered: {agent.name}")
        self._agents[agent.name] = agent

    def get(self, name: str) -> Agent:
        try:
            return self._agents[name]
        except KeyError as exc:
            raise LookupError(f"Unknown agent: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._agents))
