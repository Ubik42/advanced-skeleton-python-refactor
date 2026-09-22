"""Atomic FK animation and Skin transfer between registered spine topologies."""
from dataclasses import dataclass

from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.skin_weight_redistribution import registered_spine_weight_redistribution

from .character_spine_retarget import RetargetCharacterSpineFk
from .spine_skin_handoff import HandoffRegisteredSpineSkinCluster
from .skin_weight_surface_transfer import TransferSkinWeightsBySurface
from .skin_weights import EditSkinWeights


@dataclass(frozen=True, slots=True)
class RegisteredSpineMigrationResult:
    frames: int
    fk_groups: int
    changed_vertices: int


class MigrateRegisteredSpineCharacter:
    """Write target control curves and target Skin weights in one undo chunk."""

    def __init__(self, host):
        self._host = host

    def apply(self, source_namespace, source_skin, source_mesh,
              target_skin, target_mesh, *, start_frame, end_frame,
              sample_by=1, reference_frame=None, max_distance,
              max_discarded_weight=0., allow_target_extra_influences=False):
        host = self._host
        source_reg = host.read_source_character_registration(source_namespace)
        target_reg = host.read_character_registration()
        source_state = host.capture_all_skin_weights(source_skin, source_mesh)
        target_state = host.capture_all_skin_weights(target_skin, target_mesh)
        if source_state.skin_name is None or target_state.skin_name is None:
            raise CharacterRegistryError('来源或目标 skinCluster 不存在')
        target_skin = target_state.skin_name
        target_mesh = target_state.geometry_path
        redistribution = registered_spine_weight_redistribution(
            source_reg, target_reg, source_state.influence_paths,
            target_state.influence_paths, source_namespace=source_namespace,
            target_namespace=host.namespace, target_skin_name=target_skin,
            target_mesh_path=target_mesh,
            allow_target_extra_influences=allow_target_extra_influences)
        transfer = TransferSkinWeightsBySurface(host)
        plan = transfer.plan(source_skin, source_mesh, target_skin, target_mesh,
            max_distance=max_distance,
            max_discarded_weight=max_discarded_weight,
            redistribution=redistribution,
            allow_target_extra_influences=allow_target_extra_influences)
        editor = EditSkinWeights(host)
        edit_plan = editor.plan(target_skin, target_mesh,
                                plan.transfer.document.vertices)
        if not edit_plan.ready:
            raise CharacterRegistryError('目标 Skin 权重不可写：'
                                         + '；'.join(edit_plan.blockers))
        with host.transaction('Migrate registered spine animation and Skin'):
            if (host.read_source_character_registration(source_namespace) != source_reg
                    or host.read_character_registration() != target_reg
                    or host.capture_all_skin_weights(source_skin, source_mesh) != source_state
                    or host.capture_face_mesh(source_mesh) != plan.source_mesh
                    or host.capture_face_triangles(source_mesh) != plan.source_triangles
                    or host.capture_face_mesh(target_mesh) != plan.target_mesh):
                raise CharacterRegistryError('脊柱动画或 Skin 来源在写入前发生变化')
            edit = editor.apply_plan_in_transaction(edit_plan)
            roots, groups = RetargetCharacterSpineFk(host).apply_in_transaction(
                source_namespace, start_frame=start_frame, end_frame=end_frame,
                sample_by=sample_by, reference_frame=reference_frame)
            if host.capture_all_skin_weights(source_skin, source_mesh) != source_state:
                raise RuntimeError('跨段数迁移改写了来源 Skin 权重')
            if host.capture_all_skin_weights(target_skin, target_mesh) != edit.snapshot:
                raise RuntimeError('跨段数迁移后的目标 Skin 权重变化')
        return RegisteredSpineMigrationResult(len(roots), len(groups),
                                              edit.changed_vertex_count)


@dataclass(frozen=True, slots=True)
class OriginalSkinSpineMigrationResult:
    frames: int
    fk_groups: int
    vertices: int
    target_influences: int


class MigrateRegisteredSpineOnOriginalSkin:
    """Keep the source mesh/skinCluster while writing replacement FK animation."""

    def __init__(self, host):
        self._host = host

    def apply(self, source_namespace, target_namespace, skin_name, mesh_path,
              *, start_frame, end_frame, sample_by=1, reference_frame=None):
        host = self._host
        if host.namespace != target_namespace:
            raise CharacterRegistryError('目标动画宿主与目标角色命名空间不一致')
        skin_host = host.original_skin_handoff_host()
        handoff = HandoffRegisteredSpineSkinCluster(skin_host)
        plan = handoff.plan(source_namespace, target_namespace, skin_name, mesh_path)
        with host.transaction('Migrate spine FK and original skinCluster'):
            skin_host._transaction_active = True
            try:
                result = handoff.apply_plan_in_transaction(
                    plan, source_namespace, target_namespace, skin_name, mesh_path,
                    before_mutation=host.mark_original_skin_mutation)
            finally:
                skin_host._transaction_active = False
            roots, groups = RetargetCharacterSpineFk(host).apply_in_transaction(
                source_namespace, start_frame=start_frame, end_frame=end_frame,
                sample_by=sample_by, reference_frame=reference_frame)
            if skin_host.read_registration_in_namespace(source_namespace) != plan.source_registration:
                raise RuntimeError('动画迁移改变了来源角色登记')
            final = skin_host.capture_all_skin_weights(skin_name, mesh_path)
            if (set(final.influence_paths) != set(plan.target_document.influence_paths)
                    or skin_host.capture_skin_handoff_boundary(skin_name, mesh_path)
                    != plan.boundary):
                raise RuntimeError('动画迁移改变了原 Skin 交接结果')
        return OriginalSkinSpineMigrationResult(
            len(roots), len(groups), result.vertex_count,
            result.target_influence_count)
