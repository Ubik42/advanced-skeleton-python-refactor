"""Install native AlignIKTo frames using the complete preserved-data rebuild."""
from dataclasses import dataclass

from adv_py.core.source_spline_alignment_upgrade import source_spline_alignment_upgrade_systems
from .character_rebuild import RebuildBodyCharacter


@dataclass(frozen=True)
class SourceSplineAlignmentUpgradeResult:
    systems: tuple[str, ...]
    rebuild: object | None


class UpgradeSourceSplineAlignment:
    def __init__(self, host):
        self.host = host

    def apply(self, replacement_namespace, systems=None, *, extensions=()):
        registration = self.host.read_character_registration()
        selected = source_spline_alignment_upgrade_systems(registration, systems)
        if not selected:
            return SourceSplineAlignmentUpgradeResult((), None)
        result = RebuildBodyCharacter(self.host).apply(replacement_namespace,
            extensions=extensions, spline_alignment_systems=selected)
        return SourceSplineAlignmentUpgradeResult(selected, result)
