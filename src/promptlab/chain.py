"""Prompt chain composition for multi-step prompt pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .template import PromptTemplate


@dataclass
class ChainStep:
    """A single step in a prompt chain."""

    name: str
    template: PromptTemplate
    transform: Callable[[str], dict[str, str]] | None = None

    def execute(self, variables: dict[str, str]) -> str:
        """Render the template with the given variables."""
        return self.template.render(**variables)


@dataclass
class PromptChain:
    """A chain of prompt templates that feed into each other."""

    name: str
    steps: list[ChainStep] = field(default_factory=list)

    def add_step(self, step: ChainStep) -> None:
        """Append a step to the chain."""
        self.steps.append(step)

    def execute(self, initial_variables: dict[str, str]) -> list[str]:
        """Execute all steps in order, passing outputs through transforms.

        Each step's transform function converts the step's output string
        into variables for the next step. If no transform is set, the
        output is passed as a 'previous_output' variable.
        """
        if not self.steps:
            return []

        results: list[str] = []
        current_vars = dict(initial_variables)

        for step in self.steps:
            output = step.execute(current_vars)
            results.append(output)

            if step.transform:
                current_vars = step.transform(output)
            else:
                current_vars = {"previous_output": output}

        return results

    def __len__(self) -> int:
        return len(self.steps)
