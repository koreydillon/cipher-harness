"""
Base Tool interface for Cipher — inspired by Claude Code's Tool.ts
Every tool must implement: call(), schema, name, description
Optional: is_read_only, is_concurrency_safe, is_destructive, check_permissions
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    output: str
    error: bool = False
    interrupted: bool = False


class Tool(ABC):
    # Override in subclass
    is_read_only: bool = False
    is_concurrency_safe: bool = False
    is_destructive: bool = False

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def input_schema(self) -> dict: ...

    def check_permissions(self, input: dict) -> tuple[bool, str]:
        """Return (allowed, reason). Override for custom permission logic."""
        return True, ""

    @abstractmethod
    def call(self, input: dict) -> ToolResult: ...

    def to_api_dict(self) -> dict:
        """Format for Anthropic API tool_choice / tools list."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
