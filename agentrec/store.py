"""
Abstract store interface and the in-memory implementation.

Later implementations (YAML cassette, Parquet corpus) satisfy the same
interface without touching the transport code.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict

from .capture import CapturedInteraction


class InteractionStore(ABC):
    @abstractmethod
    async def save(self, interaction_id: str, interaction: CapturedInteraction) -> None:
        ...

    @abstractmethod
    async def load(self, interaction_id: str) -> CapturedInteraction:
        ...


class InMemoryStore(InteractionStore):
    """Volatile, single-process store — the first implementation."""

    def __init__(self) -> None:
        self._data: Dict[str, CapturedInteraction] = {}

    async def save(self, interaction_id: str, interaction: CapturedInteraction) -> None:
        self._data[interaction_id] = interaction

    async def load(self, interaction_id: str) -> CapturedInteraction:
        try:
            return self._data[interaction_id]
        except KeyError:
            raise KeyError(
                f"No recorded interaction for id={interaction_id!r}. "
                "Run the record phase before replaying."
            ) from None

    def __contains__(self, interaction_id: str) -> bool:
        return interaction_id in self._data
