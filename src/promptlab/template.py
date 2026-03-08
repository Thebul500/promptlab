"""Prompt template engine with variable interpolation and version tracking."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PromptTemplate:
    """A versioned prompt template with variable interpolation."""

    name: str
    content: str
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    _VAR_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")

    def render(self, **variables: str) -> str:
        """Render the template by substituting variables.

        Raises KeyError if a required variable is missing.
        """
        missing = self.variables - set(variables.keys())
        if missing:
            raise KeyError(f"Missing template variables: {', '.join(sorted(missing))}")

        def replacer(match: re.Match) -> str:
            return variables[match.group(1)]

        return self._VAR_PATTERN.sub(replacer, self.content)

    @property
    def variables(self) -> set[str]:
        """Return the set of variable names used in this template."""
        return set(self._VAR_PATTERN.findall(self.content))

    def new_version(self, content: str) -> "PromptTemplate":
        """Create a new version of this template with updated content."""
        return PromptTemplate(
            name=self.name,
            content=content,
            version=self.version + 1,
            metadata=dict(self.metadata),
        )


class TemplateRegistry:
    """Registry for managing named prompt templates."""

    def __init__(self) -> None:
        self._templates: dict[str, PromptTemplate] = {}

    def register(self, template: PromptTemplate) -> None:
        """Register a template. Overwrites existing template with same name."""
        self._templates[template.name] = template

    def get(self, name: str) -> PromptTemplate:
        """Get a template by name. Raises KeyError if not found."""
        if name not in self._templates:
            raise KeyError(f"Template not found: {name}")
        return self._templates[name]

    def list_templates(self) -> list[str]:
        """Return sorted list of registered template names."""
        return sorted(self._templates.keys())

    def __len__(self) -> int:
        return len(self._templates)
