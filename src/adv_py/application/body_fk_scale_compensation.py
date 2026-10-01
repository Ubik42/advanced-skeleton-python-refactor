"""Connect and read back FK segment scale compensation."""
from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from adv_py.core.body_fk_scale_compensation import (
    BodyFkScaleCompensationSpec,
)


class BodyFkScaleCompensationHost(Protocol):
    def transaction(self, label: str) -> AbstractContextManager[None]: ...

    def preflight_body_fk_scale_compensation(
        self, spec: BodyFkScaleCompensationSpec,
    ) -> None: ...

    def connect_body_fk_scale_compensation(
        self, spec: BodyFkScaleCompensationSpec,
    ) -> None: ...

    def capture_body_fk_scale_compensation(
        self, spec: BodyFkScaleCompensationSpec,
    ) -> bool: ...


class BuildBodyFkScaleCompensation:
    def __init__(self, host: BodyFkScaleCompensationHost) -> None:
        self._host = host

    def apply(
        self, specs: tuple[BodyFkScaleCompensationSpec, ...],
    ) -> tuple[BodyFkScaleCompensationSpec, ...]:
        for spec in specs:
            self._host.preflight_body_fk_scale_compensation(spec)
        with self._host.transaction("构建 FK 分段缩放补偿"):
            # Freeze each receiver after its ancestor's bind frame is final.
            # Sibling/label order is not a hierarchy order on imported Fits.
            for spec in sorted(specs, key=lambda item: item.offset_path.count("|")):
                self._host.connect_body_fk_scale_compensation(spec)
            for spec in specs:
                if not self._host.capture_body_fk_scale_compensation(spec):
                    raise RuntimeError("FK 分段缩放补偿读回不一致："
                                       + spec.offset_path)
        return specs
