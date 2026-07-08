from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Theme:
    """An economic theme used to reason about portfolio exposure."""

    name: str
    description: str
    parent: str | None = None
    children: list[str] = field(default_factory=list)


AI_THEME_TREE = [
    Theme("Artificial Intelligence", "Broad exposure to AI-driven economic change."),
    Theme("AI Compute", "GPUs, accelerators, and compute infrastructure.", parent="Artificial Intelligence"),
    Theme("AI Cloud", "Cloud platforms and AI hosting infrastructure.", parent="Artificial Intelligence"),
    Theme("AI Power Grid", "Electric generation, transmission, substations, and transformers.", parent="Artificial Intelligence"),
    Theme("AI Cooling", "Thermal management and data-center cooling.", parent="Artificial Intelligence"),
    Theme("AI Networking", "Fiber, switching, interconnects, and data-center networking.", parent="Artificial Intelligence"),
    Theme("AI Automation", "Robotics, industrial automation, and productivity tools.", parent="Artificial Intelligence"),
    Theme("AI Cybersecurity", "Security demand caused by AI-enabled systems.", parent="Artificial Intelligence"),
]
