"""Retain an existing mesh and skinCluster while replacing Body influences."""
from dataclasses import dataclass

from adv_py.core.character_identity import CharacterIdentity
from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.body_spline import BodySplinePlan
from adv_py.core.skin_weight_io import skin_weight_document_from_state
from adv_py.core.skin_weight_redistribution import (
    registered_spine_weight_redistribution, redistribute_skin_weight_document)

from .skin_weights import EditSkinWeights


def _short(path):
    return path.rsplit('|', 1)[-1].rsplit(':', 1)[-1]


def _require_bind_pose(registration, matrices):
    if len(matrices) != len(registration.body):
        raise CharacterRegistryError('原位 Skin 交接的 Body 绑定姿态不完整')
    for joint, actual in zip(registration.body, matrices):
        if max(abs(a-b) for a, b in zip(joint.matrix, actual)) > 1e-4:
            raise CharacterRegistryError('原位 Skin 交接要求两个角色处于登记绑定姿态：'
                                         + joint.path)


@dataclass(frozen=True, slots=True)
class SpineSkinHandoffPlan:
    source_registration: object
    target_registration: object
    source_state: object
    source_bind_pose: tuple
    target_bind_pose: tuple
    mesh: object
    boundary: tuple
    target_document: object


@dataclass(frozen=True, slots=True)
class SpineSkinHandoffResult:
    plan: SpineSkinHandoffPlan
    vertex_count: int
    target_influence_count: int


class HandoffRegisteredSpineSkinCluster:
    """Reassign one existing skinCluster to the target registered Body."""

    def __init__(self, host):
        self._host = host

    def plan(self, source_namespace, target_namespace, skin_name, mesh_path):
        host = self._host
        source = host.read_registration_in_namespace(source_namespace)
        target = host.read_registration_in_namespace(target_namespace)
        if (not isinstance(source.spine, BodySplinePlan)
                or not isinstance(target.spine, BodySplinePlan)):
            raise CharacterRegistryError('原位 Skin 交接要求两个可变脊柱登记角色')
        state = host.capture_all_skin_weights(skin_name, mesh_path)
        if state.skin_name is None or state.geometry_path != mesh_path:
            raise CharacterRegistryError('原位 Skin 交接的网格与 skinCluster 不一致')
        source_bind = host.capture_registered_body_matrices(source, source_namespace)
        target_bind = host.capture_registered_body_matrices(target, target_namespace)
        _require_bind_pose(source, source_bind)
        _require_bind_pose(target, target_bind)
        physical = CharacterIdentity(target_namespace)
        target_by_name = {_short(row.path): physical.to_scene(row.path)
                          for row in target.body}
        spine_names = tuple(_short(path) for path in target.spine.body_joints)
        nonspine = tuple(_short(path) for path in state.influence_paths
                         if _short(path) not in {_short(p) for p in source.spine.body_joints})
        if any(name not in target_by_name for name in (*spine_names, *nonspine)):
            raise CharacterRegistryError('目标 Body 缺少原 Skin 所需的同名关节')
        target_paths = tuple(target_by_name[name] for name in (*spine_names, *nonspine))
        redistribution = registered_spine_weight_redistribution(
            source, target, state.influence_paths, target_paths,
            source_namespace=source_namespace, target_namespace=target_namespace,
            target_skin_name=state.skin_name, target_mesh_path=state.geometry_path)
        document = redistribute_skin_weight_document(
            skin_weight_document_from_state(state), redistribution)
        if (state.maintain_maximum_influences and
                any(len(row.weights) > state.maximum_influences
                    for row in document.vertices)):
            raise CharacterRegistryError('重分配结果超过原 skinCluster 最大影响数')
        mesh = host.capture_face_mesh(mesh_path)
        boundary = host.capture_skin_handoff_boundary(skin_name, mesh_path)
        return SpineSkinHandoffPlan(source, target, state, source_bind,
                                    target_bind, mesh, boundary, document)

    def apply(self, source_namespace, target_namespace, skin_name, mesh_path):
        host = self._host
        plan = self.plan(source_namespace, target_namespace, skin_name, mesh_path)
        with host.transaction('Handoff original skinCluster to variable spine'):
            return self.apply_plan_in_transaction(plan, source_namespace,
                                                  target_namespace, skin_name, mesh_path)

    def apply_plan_in_transaction(self, plan, source_namespace, target_namespace,
                                  skin_name, mesh_path, *, before_mutation=None,
                                  release_bind_pose=True):
        """Apply a checked handoff inside a larger character migration."""
        host = self._host
        host._require_transaction()
        if not isinstance(plan, SpineSkinHandoffPlan):
            raise CharacterRegistryError('原位 Skin 交接计划类型无效')
        if (host.read_registration_in_namespace(source_namespace)
                != plan.source_registration
                or host.read_registration_in_namespace(target_namespace)
                != plan.target_registration
                or host.capture_all_skin_weights(skin_name, mesh_path)
                != plan.source_state
                or host.capture_registered_body_matrices(
                    plan.source_registration, source_namespace) != plan.source_bind_pose
                or host.capture_registered_body_matrices(
                    plan.target_registration, target_namespace) != plan.target_bind_pose
                or host.capture_face_mesh(mesh_path) != plan.mesh
                or host.capture_skin_handoff_boundary(skin_name, mesh_path)
                != plan.boundary):
            raise CharacterRegistryError('原位 Skin 交接输入在写入前发生变化')
        if before_mutation is not None:
            before_mutation()
        host.add_skin_handoff_influences(skin_name,
            plan.target_document.influence_paths)
        host.verify_skin_handoff_bind_matrices(skin_name,
            plan.target_registration, target_namespace,
            plan.target_document.influence_paths)
        added = host.capture_all_skin_weights(skin_name, mesh_path)
        for old, current in zip(plan.source_state.vertices, added.vertices):
            values = {entry.influence_path: entry.weight
                      for entry in current.weights}
            if any(abs(values.get(entry.influence_path, 0.) - entry.weight) > 1e-6
                   for entry in old.weights):
                raise RuntimeError('新增目标影响关节改变了原权重')
        editor = EditSkinWeights(host)
        edit = editor.plan(skin_name, mesh_path,
                           plan.target_document.vertices)
        if not edit.ready:
            raise CharacterRegistryError('原 skinCluster 无法写入重分配权重：'
                                         + '；'.join(edit.blockers))
        editor.apply_plan_in_transaction(edit)
        host.remove_skin_handoff_influences(skin_name,
                                            plan.source_state.influence_paths)
        if release_bind_pose:
            host.release_old_bind_pose_members(skin_name, source_namespace)
        final = host.capture_all_skin_weights(skin_name, mesh_path)
        if set(final.influence_paths) != set(plan.target_document.influence_paths):
            raise RuntimeError('原 skinCluster 的影响关节集合未完整交接')
        for wanted, actual in zip(plan.target_document.vertices, final.vertices):
            values = {entry.influence_path: entry.weight
                      for entry in actual.weights}
            if (wanted.vertex_index != actual.vertex_index
                    or any(abs(values.get(entry.influence_path, 0.)
                               - entry.weight) > 1e-6
                           for entry in wanted.weights)
                    or any(path not in {entry.influence_path for entry in wanted.weights}
                           and weight > 1e-8 for path, weight in values.items())):
                raise RuntimeError('原 skinCluster 权重交接复检失败')
        current_points = host.capture_face_mesh(mesh_path).points
        if (host.capture_skin_handoff_boundary(skin_name, mesh_path)
                != plan.boundary
                or len(current_points) != len(plan.mesh.points)
                or any(max(abs(a-b) for a, b in zip(left, right)) > 1e-4
                       for left, right in zip(current_points, plan.mesh.points))):
            raise RuntimeError('原位 Skin 交接改变网格中性姿态或变形历史')
        return SpineSkinHandoffResult(plan, final.vertex_count,
                                      len(final.influence_paths))
