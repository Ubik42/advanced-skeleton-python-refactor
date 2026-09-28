"""Build source-shaped Bendy curve guides inside the character transaction."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.fit_bendy import FitBendyChainSpec


class FitBendyGuideHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...
    def preflight_fit_bendy_guides(
        self, spec: FitBendyChainSpec) -> None: ...
    def create_fit_bendy_guides(
        self, spec: FitBendyChainSpec) -> None: ...
    def capture_fit_bendy_guides(
        self, spec: FitBendyChainSpec) -> bool: ...


class BuildFitBendyGuides:
    def __init__(self, host: FitBendyGuideHost) -> None:
        self._host = host

    def apply(self, chains: tuple[FitBendyChainSpec, ...]
              ) -> tuple[FitBendyChainSpec, ...]:
        used = set()
        for chain in chains:
            names = set(chain.guide_node_names)
            if names & used:
                raise ValueError("Fit Bendy 导向节点名称重复")
            used.update(names)
            self._host.preflight_fit_bendy_guides(chain)
        with self._host.transaction("创建 Bendy 曲线导向"):
            for chain in chains:
                self._host.create_fit_bendy_guides(chain)
            for chain in chains:
                if not self._host.capture_fit_bendy_guides(chain):
                    raise RuntimeError("Bendy 曲线导向接线不一致："
                                       + chain.curve_name)
        return chains
