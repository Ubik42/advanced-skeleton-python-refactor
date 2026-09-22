"""Promote a checked replacement Rig into the original character identity."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OriginalSpinePromotionResult:
    old_nodes_removed: int
    retained_nodes: int
    replacement_nodes: int


class PromoteOriginalSpineCharacter:
    def __init__(self, host):
        self._host = host

    def apply(self, source_namespace, target_namespace, skin_name, mesh_path):
        host = self._host
        plan = host.plan_original_spine_promotion(
            source_namespace, target_namespace, skin_name, mesh_path)
        with host.transaction('Promote replacement spine Rig'):
            host.apply_original_spine_promotion(plan)
        return OriginalSpinePromotionResult(len(plan.deletion_uuids),
            len(plan.retained_uuids), len(plan.target_uuids))
