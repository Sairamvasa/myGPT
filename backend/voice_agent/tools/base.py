import abc
from typing import Dict, Any, List
from voice_agent.security.permissions import PermissionLevel

class Tool(abc.ABC):
    def __init__(self, *, name: str, description: str, permission: PermissionLevel, parameters: Dict[str, Any]):
        self.name = name
        self.description = description
        self.permission = permission
        self.parameters = parameters

    @abc.abstractmethod
    async def run(self, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError

class ToolRegistry:
    _registry: Dict[str, Tool] = {}

    @classmethod
    def register(cls, tool: Tool) -> None:
        cls._registry[tool.name] = tool

    @classmethod
    def get(cls, name: str) -> Tool:
        return cls._registry[name]

    @classmethod
    def list_tools(cls) -> List[Tool]:
        return list(cls._registry.values())
