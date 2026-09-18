"""Small immutable contracts for read-only website lifecycle lookup."""

from collections.abc import Callable
from dataclasses import dataclass
from threading import Event
from typing import Protocol

from smaxtec.application.api_data import ApiProgress


@dataclass(frozen=True, order=True)
class LifecycleTarget:
    farm: str
    cow: str

    def __post_init__(self) -> None:
        if not self.farm.strip() or not self.cow.strip():
            raise ValueError("Lifecycle targets require a farm and Animal number.")


@dataclass(frozen=True)
class LifecycleReading:
    target: LifecycleTarget
    lactation: int | None = None
    dim: int | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        values = self.lactation, self.dim
        if (self.lactation is None) != (self.dim is None) or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in values
            if value is not None
        ):
            raise ValueError(
                "A lifecycle reading must contain both non-negative values or neither."
            )

    @property
    def available(self) -> bool:
        return self.lactation is not None and self.dim is not None


class LifecycleReader(Protocol):
    def read_lact_dim(
        self,
        targets: tuple[LifecycleTarget, ...],
        progress: Callable[[ApiProgress], None],
        stop: Event,
    ) -> tuple[LifecycleReading, ...]: ...
