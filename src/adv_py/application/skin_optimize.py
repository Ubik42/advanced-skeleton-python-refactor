"""Run the original Skin cleanup routines without invented weight gates."""
from __future__ import annotations

from typing import Protocol


class SkinOptimizeHost(Protocol):
    def remove_unused(self) -> tuple[int, int]: ...
    def prune_small_weights(self) -> int: ...


class RemoveUnusedSkinInfluences:
    def __init__(self, host: SkinOptimizeHost) -> None:
        self._host = host

    def apply(self) -> tuple[int, int]:
        return self._host.remove_unused()


class PruneSmallSkinWeights:
    def __init__(self, host: SkinOptimizeHost) -> None:
        self._host = host

    def apply(self) -> int:
        return self._host.prune_small_weights()
