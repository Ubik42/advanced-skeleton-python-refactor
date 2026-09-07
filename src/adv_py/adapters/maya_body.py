from __future__ import annotations

from adv_py.core.body_arm_mechanisms import (
    BodyArmMechanismJointSpec,
    BodyArmMechanismJointState,
    BodyArmMechanismPlan,
    BodyArmMechanismSnapshot,
)
from adv_py.core.body_arm_ik import (
    BodyArmIkPlan,
    BodyArmIkSnapshot,
    BodyArmIkSpec,
    BodyArmIkState,
)
from adv_py.core.body_arm_blend import (
    BodyArmBlendJointState,
    BodyArmBlendPlan,
    BodyArmBlendSideState,
    BodyArmBlendSnapshot,
)
from adv_py.core.body_leg_blend import (
    BodyLegBlendPlan,
    BodyLegBlendSnapshot,
)
from adv_py.core.body_arm_visibility import (
    BodyArmVisibilityPlan,
    BodyArmVisibilitySideState,
    BodyArmVisibilitySnapshot,
)
from adv_py.core.body_leg_visibility import (
    BodyLegVisibilityInputState,
    BodyLegVisibilityPlan,
    BodyLegVisibilitySideState,
    BodyLegVisibilitySnapshot,
)
from adv_py.core.body_arm_match import (
    BodyArmFkToIkPlan,
    BodyArmFkToIkSceneState,
    BodyArmIkToFkPlan,
    BodyArmIkToFkSceneState,
)
from adv_py.core.body_leg_match import (
    BodyLegFkToIkPlan,
    BodyLegFkToIkSceneState,
    audit_body_leg_fk_to_ik_preflight,
)
from adv_py.core.body_arm_stretch import (
    BodyArmStretchPlan,
    BodyArmStretchSideState,
    BodyArmStretchSnapshot,
)
from adv_py.core.body_arm_twist import (
    BodyArmTwistJointSpec,
    BodyArmTwistJointState,
    BodyArmTwistPlan,
    BodyArmTwistSegmentSpec,
    BodyArmTwistSegmentState,
    BodyArmTwistSnapshot,
)
from adv_py.core.body_arm_volume import (
    BodyArmVolumePlan,
    BodyArmVolumeSideState,
    BodyArmVolumeSnapshot,
)
from adv_py.core.body_leg_mechanisms import (
    BodyLegMechanismJointSpec,
    BodyLegMechanismPlan,
    BodyLegMechanismSnapshot,
)
from adv_py.core.body_leg_controls import (
    BodyLegFkControlPlan,
    BodyLegFkControlSnapshot,
    BodyLegFkControlSpec,
)
from adv_py.core.body_leg_ik import (
    BodyLegIkPlan,
    BodyLegIkSnapshot,
    BodyLegIkSpec,
    BodyLegIkState,
)
from adv_py.core.skin_bind import (
    SkinBindInputState,
    SkinBindMethod,
    SkinBindPlan,
    SkinBindSnapshot,
    SkinWeightNormalization,
)
from adv_py.core.skin_weights import (
    SkinInfluenceWeight,
    SkinVertexWeights,
    SkinWeightChange,
    SkinWeightEditRequest,
    SkinWeightInputState,
)
from adv_py.core.skin_weight_geometry import (
    SkinMeshGeometryState,
    SkinMeshVertexPosition,
)
from adv_py.core.body_controls import (
    BodyArmFkControlPlan,
    BodyArmFkControlSnapshot,
    BodyArmFkControlSpec,
    BodyArmFkControlState,
)
from adv_py.core.body_rebuild import (
    BodyExternalDependency,
    BodyExternalDependencyKind,
    BodyRebuildSceneState,
)
from adv_py.core.body_skeleton import (
    BodyJointOrientationChange,
    BodyJointSpec,
    BodyJointState,
    BodySkeletonProvenance,
    BodySkeletonProvenanceState,
    BodySkeletonSnapshot,
)
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.fit_symmetry import FitBuildSide

from .maya_fit import MayaFitJointHost


_MAYA_SIDE_FROM_CORE = {
    FitBuildSide.MIDDLE: 0,
    FitBuildSide.LEFT: 1,
    FitBuildSide.RIGHT: 2,
}
_CORE_SIDE_FROM_MAYA = {value: key for key, value in _MAYA_SIDE_FROM_CORE.items()}
_BODY_PROVENANCE_ATTRIBUTES = {
    "owner": "advPyOwner",
    "artifact_kind": "advPyArtifactKind",
    "schema_version": "advPySchemaVersion",
    "source_container": "advPySourceContainer",
    "body_joint_count": "advPyBodyJointCount",
}


class MayaBodyBuildHost(MayaFitJointHost):
    """Maya scene adapter for the first materialized Body skeleton stage."""

    def create_body_joint(self, spec: BodyJointSpec) -> str:
        self._require_transaction()
        if self.find_name_collisions(spec.name):
            raise FitSkeletonValidationError(
                f"同名节点已存在，拒绝创建构建关节：{spec.name}"
            )
        parent = None
        if spec.parent_path is not None:
            matches = self._cmds.ls(spec.parent_path, long=True, type="joint") or []
            if len(matches) != 1:
                raise FitSkeletonValidationError(
                    f"构建关节父级在执行前失效：{spec.parent_path}"
                )
            parent = matches[0]
        options = {
            "name": spec.name,
            "skipSelect": True,
        }
        if parent is not None:
            options["parent"] = parent
        joint = self._cmds.createNode("joint", **options)
        self._transaction_changed = True
        path = (self._cmds.ls(joint, long=True) or [joint])[0]
        self._cmds.xform(
            path,
            worldSpace=True,
            translation=spec.world_position,
        )
        self.set_joint_label(path, spec.label)
        self._cmds.setAttr(f"{path}.side", _MAYA_SIDE_FROM_CORE[spec.side])
        return path

    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot:
        roots = self._cmds.ls(root_name, long=True, type="joint") or []
        if len(roots) != 1:
            raise FitSkeletonValidationError(
                f"Body skeleton 根关节无效：{root_name}"
            )
        root = roots[0]
        paths = self._cmds.listRelatives(
            root,
            allDescendents=True,
            type="joint",
            fullPath=True,
        ) or []
        paths.append(root)
        paths = sorted(set(paths), key=lambda path: (path.count("|"), path))
        states: list[BodyJointState] = []
        for path in paths:
            parents = self._cmds.listRelatives(path, parent=True, fullPath=True) or []
            position = self._cmds.xform(
                path,
                query=True,
                worldSpace=True,
                translation=True,
            )
            side_code = int(self._cmds.getAttr(f"{path}.side"))
            try:
                side = _CORE_SIDE_FROM_MAYA[side_code]
            except KeyError as error:
                raise FitSkeletonValidationError(
                    f"构建关节侧向值无效：{path}.side={side_code}"
                ) from error
            joint_orient = self._cmds.getAttr(f"{path}.jointOrient")[0]
            rotation = self._cmds.getAttr(f"{path}.rotate")[0]
            matrix = self._cmds.xform(
                path,
                query=True,
                worldSpace=True,
                matrix=True,
            )
            world_axes = tuple(
                self._normalized_vector(
                    tuple(float(value) for value in matrix[index : index + 3])
                )
                for index in (0, 4, 8)
            )
            writable_axes = frozenset(
                axis
                for axis in ("x", "y", "z")
                if self._cmds.getAttr(
                    f"{path}.jointOrient{axis.upper()}",
                    settable=True,
                )
            )
            states.append(
                BodyJointState(
                    path=path,
                    name=path.rsplit("|", 1)[-1].rsplit(":", 1)[-1],
                    parent_path=parents[0] if parents else None,
                    side=side,
                    world_position=tuple(float(value) for value in position),
                    label=self.read_joint_label(path),
                    joint_orient=tuple(float(value) for value in joint_orient),
                    rotation=tuple(float(value) for value in rotation),
                    world_axes=world_axes,
                    writable_joint_orient_axes=writable_axes,
                )
            )
        return BodySkeletonSnapshot(
            root,
            tuple(states),
            self._capture_body_provenance(root),
        )

    def write_body_provenance(
        self,
        root: str,
        provenance: BodySkeletonProvenance,
    ) -> None:
        self._require_transaction()
        matches = self._cmds.ls(root, long=True, type="joint") or []
        if len(matches) != 1 or matches[0] != root:
            raise FitSkeletonValidationError(
                f"Body provenance 根关节在执行前失效：{root}"
            )
        if any(
            self._cmds.attributeQuery(attribute, node=root, exists=True)
            for attribute in _BODY_PROVENANCE_ATTRIBUTES.values()
        ):
            raise FitSkeletonValidationError(
                "Body provenance 属性已存在，拒绝覆盖"
            )
        self._transaction_changed = True
        for field in ("owner", "artifact_kind", "source_container"):
            attribute = _BODY_PROVENANCE_ATTRIBUTES[field]
            self._cmds.addAttr(root, longName=attribute, dataType="string")
            self._cmds.setAttr(
                f"{root}.{attribute}",
                getattr(provenance, field),
                type="string",
            )
        for field in ("schema_version", "body_joint_count"):
            attribute = _BODY_PROVENANCE_ATTRIBUTES[field]
            self._cmds.addAttr(root, longName=attribute, attributeType="long")
            self._cmds.setAttr(
                f"{root}.{attribute}",
                getattr(provenance, field),
            )
        for attribute in _BODY_PROVENANCE_ATTRIBUTES.values():
            self._cmds.setAttr(f"{root}.{attribute}", lock=True)

    def capture_body_rebuild_state(
        self,
        root_name: str,
    ) -> BodyRebuildSceneState:
        roots = self._cmds.ls(root_name, long=True, type="joint") or []
        if len(roots) != 1:
            raise FitSkeletonValidationError(
                f"Body ReBuild 根关节无效：{root_name}"
            )
        root = roots[0]
        descendants = self._cmds.listRelatives(
            root,
            allDescendents=True,
            fullPath=True,
        ) or []
        dag_paths = tuple(
            sorted(set(descendants + [root]), key=lambda path: (path.count("|"), path))
        )
        body_joints = set(
            self._cmds.listRelatives(
                root,
                allDescendents=True,
                type="joint",
                fullPath=True,
            )
            or []
        )
        body_joints.add(root)
        dependencies: set[BodyExternalDependency] = set()
        for joint in sorted(body_joints):
            pairs = self._cmds.listConnections(
                joint,
                source=True,
                destination=True,
                connections=True,
                plugs=True,
            ) or []
            for index in range(0, len(pairs) - 1, 2):
                first, second = pairs[index], pairs[index + 1]
                first_node = self._resolve_connected_node(first)
                second_node = self._resolve_connected_node(second)
                if first_node in body_joints:
                    body_plug, external_plug = first, second
                    external_node = second_node
                elif second_node in body_joints:
                    body_plug, external_plug = second, first
                    external_node = first_node
                else:
                    continue
                if external_node in body_joints:
                    continue
                dependencies.add(
                    BodyExternalDependency(
                        self._dependency_kind(external_node),
                        body_plug,
                        external_plug,
                    )
                )
        return BodyRebuildSceneState(
            root,
            dag_paths,
            tuple(
                sorted(
                    dependencies,
                    key=lambda item: (
                        item.kind.value,
                        item.body_plug,
                        item.external_plug,
                    ),
                )
            ),
        )

    def delete_owned_body(self, root: str) -> None:
        self._require_transaction()
        matches = self._cmds.ls(root, long=True, type="joint") or []
        if len(matches) != 1 or matches[0] != root:
            raise FitSkeletonValidationError(
                f"待替换 Body 根关节在执行前失效：{root}"
            )
        self._transaction_changed = True
        self._cmds.delete(matches[0])

    def create_body_control_root(self, name: str) -> str:
        self._require_transaction()
        if self.find_name_collisions(name):
            raise FitSkeletonValidationError(f"Body 控制根名称冲突：{name}")
        self._transaction_changed = True
        created = self._cmds.createNode(
            "transform",
            name=name,
            skipSelect=True,
        )
        return (self._cmds.ls(created, long=True) or [created])[0]

    def create_body_arm_ik_root(self, name: str) -> str:
        return self.create_body_control_root(name)

    def create_body_leg_ik_root(self, name: str) -> str:
        return self.create_body_control_root(name)

    def create_body_arm_blend(self, plan: BodyArmBlendPlan) -> None:
        self._create_body_limb_blend(plan, "Arm")

    def create_body_leg_blend(self, plan: BodyLegBlendPlan) -> None:
        self._create_body_limb_blend(plan, "Leg")

    def _create_body_limb_blend(
        self,
        plan: BodyArmBlendPlan,
        limb_label: str,
    ) -> None:
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            self._create_body_limb_blend_nodes(plan, limb_label)
        finally:
            if selection:
                self._cmds.select(selection, replace=True)
            else:
                self._cmds.select(clear=True)

    def _create_body_limb_blend_nodes(
        self,
        plan: BodyArmBlendPlan,
        limb_label: str,
    ) -> None:
        self._require_transaction()
        names = [plan.settings_name]
        for side in plan.sides:
            names.append(side.reverse_name)
            names.extend(joint.constraint_name for joint in side.joints)
            names.extend(joint.translation_constraint_name for joint in side.joints if joint.translation_constraint_name)
        if any(self.find_name_collisions(name) for name in names):
            raise FitSkeletonValidationError(
                f"{limb_label} IK/FK 输出名称冲突"
            )
        self._transaction_changed = True
        settings = self._cmds.createNode("transform", name=plan.settings_name, skipSelect=True)
        settings = (self._cmds.ls(settings, long=True) or [settings])[0]
        if settings != plan.settings_path:
            raise RuntimeError(f"{limb_label} IK/FK 设置节点路径漂移")
        for side in plan.sides:
            self._cmds.addAttr(settings, longName=side.attribute, attributeType="double", minValue=0.0, maxValue=1.0, defaultValue=0.0, keyable=True)
            plug = f"{settings}.{side.attribute}"
            reverse = self._cmds.createNode("reverse", name=side.reverse_name)
            self._cmds.connectAttr(plug, f"{reverse}.inputX")
            for joint in side.joints:
                if any(not self._cmds.objExists(path) for path in (joint.body_joint, joint.fk_driver, joint.ik_driver)):
                    raise FitSkeletonValidationError(
                        f"{limb_label} IK/FK 驱动或 Body joint 失效"
                    )
                constraint = self._cmds.orientConstraint(joint.fk_driver, joint.ik_driver, joint.body_joint, maintainOffset=False, name=joint.constraint_name)[0]
                aliases = self._cmds.orientConstraint(constraint, query=True, weightAliasList=True) or []
                if len(aliases) != 2:
                    raise RuntimeError(
                        f"{limb_label} IK/FK 双源权重别名无效"
                    )
                self._cmds.connectAttr(f"{reverse}.outputX", f"{constraint}.{aliases[0]}")
                self._cmds.connectAttr(plug, f"{constraint}.{aliases[1]}")
                if joint.translation_constraint_name:
                    point = self._cmds.pointConstraint(
                        joint.fk_driver,
                        joint.ik_driver,
                        joint.body_joint,
                        maintainOffset=False,
                        name=joint.translation_constraint_name,
                    )[0]
                    point_aliases = self._cmds.pointConstraint(point, query=True, weightAliasList=True) or []
                    if len(point_aliases) != 2:
                        raise RuntimeError(
                            f"{limb_label} FK/IK 位移双源权重别名无效"
                        )
                    self._cmds.connectAttr(f"{reverse}.outputX", f"{point}.{point_aliases[0]}")
                    self._cmds.connectAttr(plug, f"{point}.{point_aliases[1]}")

    def capture_body_arm_blend(self, plan: BodyArmBlendPlan) -> BodyArmBlendSnapshot:
        return self._capture_body_limb_blend(plan, "Arm")

    def capture_body_leg_blend(self, plan: BodyLegBlendPlan) -> BodyLegBlendSnapshot:
        return self._capture_body_limb_blend(plan, "Leg")

    def _capture_body_limb_blend(
        self,
        plan: BodyArmBlendPlan,
        limb_label: str,
    ) -> BodyArmBlendSnapshot:
        def normalized_plug(value: str | None) -> str | None:
            if value is None or "." not in value:
                return value
            node, attribute = value.split(".", 1)
            paths = self._cmds.ls(node, long=True) or [node]
            return f"{paths[0]}.{attribute}"

        settings_nodes = self._cmds.ls(plan.settings_path, long=True, type="transform") or []
        if len(settings_nodes) != 1:
            raise FitSkeletonValidationError(
                f"{limb_label} IK/FK 设置节点无效"
            )
        settings = settings_nodes[0]
        side_states = []
        for side in plan.sides:
            plug = f"{settings}.{side.attribute}"
            reverse_nodes = self._cmds.ls(side.reverse_name, type="reverse") or []
            if len(reverse_nodes) != 1 or not self._cmds.objExists(plug):
                raise FitSkeletonValidationError(
                    f"{limb_label} IK/FK 属性或 reverse 无效"
                )
            reverse = reverse_nodes[0]
            reverse_sources = self._cmds.listConnections(f"{reverse}.inputX", source=True, destination=False, plugs=True) or []
            joint_states = []
            for spec in side.joints:
                constraints = self._cmds.ls(spec.constraint_name, type="orientConstraint") or []
                if len(constraints) != 1:
                    raise FitSkeletonValidationError(
                        f"{limb_label} IK/FK 约束无效"
                    )
                constraint = constraints[0]
                targets = self._cmds.orientConstraint(constraint, query=True, targetList=True) or []
                target_paths = tuple((self._cmds.ls(target, long=True) or [target])[0] for target in targets)
                aliases = self._cmds.orientConstraint(constraint, query=True, weightAliasList=True) or []
                weight_sources = [
                    normalized_plug((self._cmds.listConnections(f"{constraint}.{alias}", source=True, destination=False, plugs=True) or [None])[0])
                    for alias in aliases
                ]
                outputs = self._cmds.listConnections(f"{constraint}.constraintRotateX", source=False, destination=True, plugs=True) or []
                driven = self._resolve_connected_node(outputs[0]) if len(outputs) == 1 else None
                translation_name = None
                translation_targets = ()
                translation_weights = (None, None)
                translation_driven = None
                if spec.translation_constraint_name:
                    point_constraints = self._cmds.ls(spec.translation_constraint_name, type="pointConstraint") or []
                    if len(point_constraints) != 1:
                        raise FitSkeletonValidationError(
                            f"{limb_label} FK/IK 位移约束无效"
                        )
                    point = point_constraints[0]
                    point_targets = self._cmds.pointConstraint(point, query=True, targetList=True) or []
                    translation_targets = tuple((self._cmds.ls(target, long=True) or [target])[0] for target in point_targets)
                    point_aliases = self._cmds.pointConstraint(point, query=True, weightAliasList=True) or []
                    sources = tuple(
                        normalized_plug((self._cmds.listConnections(f"{point}.{alias}", source=True, destination=False, plugs=True) or [None])[0])
                        for alias in point_aliases
                    )
                    translation_weights = (
                        sources[0] if len(sources) > 0 else None,
                        sources[1] if len(sources) > 1 else None,
                    )
                    point_outputs = self._cmds.listConnections(f"{point}.constraintTranslateX", source=False, destination=True, plugs=True) or []
                    translation_driven = self._resolve_connected_node(point_outputs[0]) if len(point_outputs) == 1 else None
                    translation_name = point
                joint_states.append(BodyArmBlendJointState(
                    constraint,
                    driven,
                    target_paths,
                    weight_sources[0] if len(weight_sources) > 0 else None,
                    weight_sources[1] if len(weight_sources) > 1 else None,
                    translation_name,
                    translation_targets,
                    translation_weights[0],
                    translation_weights[1],
                    translation_driven,
                ))
            side_states.append(BodyArmBlendSideState(side.side, plug, float(self._cmds.getAttr(plug)), reverse, normalized_plug(reverse_sources[0]) if len(reverse_sources) == 1 else None, tuple(joint_states)))
        return BodyArmBlendSnapshot(settings, tuple(side_states))

    def create_body_arm_visibility(self, plan: BodyArmVisibilityPlan) -> None:
        self._create_body_limb_visibility(plan, "Arm")

    def create_body_leg_visibility(self, plan: BodyLegVisibilityPlan) -> None:
        self._create_body_limb_visibility(plan, "Leg")

    def _create_body_limb_visibility(self, plan, limb_label: str) -> None:
        self._require_transaction()
        targets = tuple(
            path
            for side in plan.sides
            for path in (side.fk_offset_path, *side.ik_offset_paths)
        )
        sources = tuple(
            plug
            for side in plan.sides
            for plug in (side.reverse_output_plug, side.blend_plug)
        )
        if any(not self._cmds.objExists(value) for value in (*targets, *sources)):
            raise FitSkeletonValidationError(f"{limb_label} 控制显隐节点或属性在执行前失效")
        self._transaction_changed = True
        for side in plan.sides:
            self._cmds.connectAttr(side.reverse_output_plug, f"{side.fk_offset_path}.visibility")
            for path in side.ik_offset_paths:
                self._cmds.connectAttr(side.blend_plug, f"{path}.visibility")

    def capture_body_arm_visibility(self, plan: BodyArmVisibilityPlan) -> BodyArmVisibilitySnapshot:
        return self._capture_body_limb_visibility(
            plan, BodyArmVisibilitySideState, BodyArmVisibilitySnapshot
        )

    def capture_body_leg_visibility(self, plan: BodyLegVisibilityPlan) -> BodyLegVisibilitySnapshot:
        return self._capture_body_limb_visibility(
            plan, BodyLegVisibilitySideState, BodyLegVisibilitySnapshot
        )

    def capture_body_leg_visibility_input(
        self, plan: BodyLegVisibilityPlan
    ) -> BodyLegVisibilityInputState:
        sources = tuple(
            plug
            for side in plan.sides
            for plug in (side.reverse_output_plug, side.blend_plug)
            if self._cmds.objExists(plug)
        )
        target_plugs = tuple(
            f"{path}.visibility"
            for side in plan.sides
            for path in (side.fk_offset_path, *side.ik_offset_paths)
        )
        writable = tuple(
            plug
            for plug in target_plugs
            if self._cmds.objExists(plug)
            and bool(self._cmds.getAttr(plug, settable=True))
        )
        return BodyLegVisibilityInputState(sources, writable)

    def _capture_body_limb_visibility(self, plan, side_state_type, snapshot_type):
        def source(path: str) -> str | None:
            values = self._cmds.listConnections(
                f"{path}.visibility",
                source=True,
                destination=False,
                plugs=True,
            ) or []
            if len(values) != 1:
                return None
            value = values[0]
            if "." not in value:
                return value
            node, attribute = value.split(".", 1)
            nodes = self._cmds.ls(node, long=True) or [node]
            return f"{nodes[0]}.{attribute}"

        states = []
        for side in plan.sides:
            states.append(
                side_state_type(
                    side.side,
                    source(side.fk_offset_path),
                    tuple(source(path) for path in side.ik_offset_paths),
                )
            )
        return snapshot_type(tuple(states))

    def create_body_arm_stretch(self, plan: BodyArmStretchPlan) -> None:
        self._require_transaction()
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            if not self._cmds.objExists(plan.settings_path):
                raise FitSkeletonValidationError("Arm stretch 设置节点在执行前失效")
            global_scale_plug = f"{plan.settings_path}.{plan.global_scale_attribute}"
            if self._cmds.objExists(global_scale_plug):
                raise FitSkeletonValidationError("Arm stretch 全局比例属性已存在")
            self._transaction_changed = True
            self._cmds.addAttr(
                plan.settings_path,
                longName=plan.global_scale_attribute,
                attributeType="double",
                minValue=0.0001,
                defaultValue=plan.global_scale_default,
                keyable=True,
            )
            for spec in plan.sides:
                names = (spec.start_name, spec.distance_name, spec.ratio_name, spec.rest_scale_name, spec.clamp_name, spec.blend_name, spec.segment_name)
                if any(self.find_name_collisions(name) for name in names):
                    raise FitSkeletonValidationError("Arm stretch 输出名称冲突")
                if any(not self._cmds.objExists(path) for path in (spec.wrist_control_path, *spec.segment_joints)):
                    raise FitSkeletonValidationError("Arm stretch 控制或 IK mechanism 在执行前失效")
                plug = f"{plan.settings_path}.{spec.attribute}"
                if self._cmds.objExists(plug):
                    raise FitSkeletonValidationError("Arm stretch 属性已存在")
                self._cmds.addAttr(plan.settings_path, longName=spec.attribute, attributeType="double", minValue=0.0, maxValue=1.0, defaultValue=1.0, keyable=True)
                start = self._cmds.createNode("transform", name=spec.start_name, parent="|AdvPy_ArmMechanisms", skipSelect=True)
                start = (self._cmds.ls(start, long=True) or [start])[0]
                self._cmds.xform(start, worldSpace=True, translation=spec.start_position)
                if start != spec.start_path:
                    raise RuntimeError("Arm stretch 起点路径漂移")
                distance = self._cmds.createNode("distanceBetween", name=spec.distance_name, skipSelect=True)
                ratio = self._cmds.createNode("multiplyDivide", name=spec.ratio_name, skipSelect=True)
                rest_scale = self._cmds.createNode("multiplyDivide", name=spec.rest_scale_name, skipSelect=True)
                clamp = self._cmds.createNode("clamp", name=spec.clamp_name, skipSelect=True)
                blend = self._cmds.createNode("blendColors", name=spec.blend_name, skipSelect=True)
                segments = self._cmds.createNode("multiplyDivide", name=spec.segment_name, skipSelect=True)
                self._cmds.connectAttr(f"{start}.worldMatrix[0]", f"{distance}.inMatrix1")
                self._cmds.connectAttr(f"{spec.wrist_control_path}.worldMatrix[0]", f"{distance}.inMatrix2")
                self._cmds.setAttr(f"{ratio}.operation", 2)
                self._cmds.connectAttr(f"{distance}.distance", f"{ratio}.input1X")
                self._cmds.setAttr(f"{rest_scale}.operation", 1)
                self._cmds.setAttr(f"{rest_scale}.input1X", spec.rest_length)
                self._cmds.connectAttr(global_scale_plug, f"{rest_scale}.input2X")
                self._cmds.connectAttr(f"{rest_scale}.outputX", f"{ratio}.input2X")
                self._cmds.setAttr(f"{clamp}.minR", 1.0)
                self._cmds.setAttr(f"{clamp}.maxR", 1000000.0)
                self._cmds.connectAttr(f"{ratio}.outputX", f"{clamp}.inputR")
                self._cmds.connectAttr(f"{clamp}.outputR", f"{blend}.color1R")
                self._cmds.setAttr(f"{blend}.color2R", 1.0)
                self._cmds.connectAttr(plug, f"{blend}.blender")
                self._cmds.setAttr(f"{segments}.operation", 1)
                self._cmds.setAttr(f"{segments}.input1X", spec.base_translations[0])
                self._cmds.setAttr(f"{segments}.input1Y", spec.base_translations[1])
                self._cmds.connectAttr(f"{blend}.outputR", f"{segments}.input2X")
                self._cmds.connectAttr(f"{blend}.outputR", f"{segments}.input2Y")
                self._cmds.connectAttr(f"{segments}.outputX", f"{spec.segment_joints[0]}.translateX")
                self._cmds.connectAttr(f"{segments}.outputY", f"{spec.segment_joints[1]}.translateX")
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def capture_body_arm_stretch(self, plan: BodyArmStretchPlan) -> BodyArmStretchSnapshot:
        def source(plug: str) -> str | None:
            values = self._cmds.listConnections(plug, source=True, destination=False, plugs=True) or []
            if len(values) != 1:
                return None
            value = values[0]
            if "." not in value:
                return value
            node, attribute = value.split(".", 1)
            if attribute == "worldMatrix":
                attribute = "worldMatrix[0]"
            nodes = self._cmds.ls(node, long=True) or [node]
            return f"{nodes[0]}.{attribute}"

        settings = (self._cmds.ls(plan.settings_path, long=True, type="transform") or [None])[0]
        if settings is None:
            raise FitSkeletonValidationError("Arm stretch 设置节点无效")
        global_scale_plug = f"{settings}.{plan.global_scale_attribute}"
        if not self._cmds.objExists(global_scale_plug):
            raise FitSkeletonValidationError("Arm stretch 全局比例输入无效")
        states = []
        for spec in plan.sides:
            typed = (
                (spec.start_path, "transform"),
                (spec.distance_name, "distanceBetween"),
                (spec.ratio_name, "multiplyDivide"),
                (spec.rest_scale_name, "multiplyDivide"),
                (spec.clamp_name, "clamp"),
                (spec.blend_name, "blendColors"),
                (spec.segment_name, "multiplyDivide"),
            )
            if any(len(self._cmds.ls(name, type=node_type) or []) != 1 for name, node_type in typed):
                raise FitSkeletonValidationError("Arm stretch 节点集合无效")
            plug = f"{settings}.{spec.attribute}"
            states.append(BodyArmStretchSideState(
                spec.side,
                plug,
                float(self._cmds.getAttr(plug)),
                spec.start_path,
                tuple(float(value) for value in self._cmds.xform(spec.start_path, query=True, worldSpace=True, translation=True)),
                spec.distance_name,
                (source(f"{spec.distance_name}.inMatrix1"), source(f"{spec.distance_name}.inMatrix2")),
                spec.ratio_name,
                source(f"{spec.ratio_name}.input1X"),
                spec.rest_scale_name,
                float(self._cmds.getAttr(f"{spec.rest_scale_name}.input1X")),
                source(f"{spec.rest_scale_name}.input2X"),
                int(self._cmds.getAttr(f"{spec.rest_scale_name}.operation")),
                source(f"{spec.ratio_name}.input2X"),
                int(self._cmds.getAttr(f"{spec.ratio_name}.operation")),
                spec.clamp_name,
                source(f"{spec.clamp_name}.inputR"),
                float(self._cmds.getAttr(f"{spec.clamp_name}.minR")),
                float(self._cmds.getAttr(f"{spec.clamp_name}.maxR")),
                spec.blend_name,
                source(f"{spec.blend_name}.color1R"),
                source(f"{spec.blend_name}.blender"),
                float(self._cmds.getAttr(f"{spec.blend_name}.color2R")),
                spec.segment_name,
                (float(self._cmds.getAttr(f"{spec.segment_name}.input1X")), float(self._cmds.getAttr(f"{spec.segment_name}.input1Y"))),
                (source(f"{spec.segment_name}.input2X"), source(f"{spec.segment_name}.input2Y")),
                (source(f"{spec.segment_joints[0]}.translateX"), source(f"{spec.segment_joints[1]}.translateX")),
                int(self._cmds.getAttr(f"{spec.segment_name}.operation")),
            ))
        return BodyArmStretchSnapshot(
            settings,
            global_scale_plug,
            float(self._cmds.getAttr(global_scale_plug)),
            tuple(states),
        )

    def prepare_body_arm_twist_runtime(self) -> None:
        try:
            if not self._cmds.pluginInfo("quatNodes", query=True, loaded=True):
                self._cmds.loadPlugin("quatNodes", quiet=True)
        except Exception as exc:
            raise FitSkeletonValidationError(
                "Arm twist 需要 Maya 自带 quatNodes 插件"
            ) from exc
        if "quatToEuler" not in (self._cmds.allNodeTypes() or []):
            raise FitSkeletonValidationError("Arm twist 缺少 quatToEuler 节点")

    def create_body_arm_twist_root(self, name: str) -> str:
        self._require_transaction()
        if self.find_name_collisions(name):
            raise FitSkeletonValidationError(f"Arm twist 根名称冲突：{name}")
        if "quatToEuler" not in (self._cmds.allNodeTypes() or []):
            raise FitSkeletonValidationError("Arm twist 运行依赖在执行前失效")
        self._transaction_changed = True
        root = self._cmds.createNode("transform", name=name, skipSelect=True)
        return (self._cmds.ls(root, long=True) or [root])[0]

    def create_body_arm_twist_segment(self, spec: BodyArmTwistSegmentSpec) -> None:
        self._require_transaction()
        selection = self._cmds.ls(selection=True, long=True) or []
        names = (
            spec.name,
            spec.constraint_name,
            spec.compose_name,
            spec.decompose_name,
            spec.quaternion_name,
        )
        try:
            if any(self.find_name_collisions(name) for name in names):
                raise FitSkeletonValidationError("Arm twist 段驱动名称冲突")
            if any(
                not self._cmds.objExists(path)
                for path in (spec.parent_path, spec.start_joint, spec.end_joint)
            ):
                raise FitSkeletonValidationError("Arm twist 段父级或 Body 端点失效")
            end_parents = self._cmds.listRelatives(
                spec.end_joint,
                parent=True,
                fullPath=True,
            ) or []
            if end_parents != [spec.start_joint]:
                raise FitSkeletonValidationError("Arm twist 端点不再是直接父子链")
            self._transaction_changed = True
            base = self._cmds.createNode(
                "transform",
                name=spec.name,
                parent=spec.parent_path,
                skipSelect=True,
            )
            base = (self._cmds.ls(base, long=True) or [base])[0]
            self._cmds.xform(
                base,
                worldSpace=True,
                matrix=self._cmds.xform(
                    spec.start_joint,
                    query=True,
                    worldSpace=True,
                    matrix=True,
                ),
            )
            if base != spec.path:
                raise RuntimeError("Arm twist 段基座路径漂移")
            self._cmds.parentConstraint(
                spec.start_joint,
                base,
                maintainOffset=False,
                name=spec.constraint_name,
            )
            compose = self._cmds.createNode("composeMatrix", name=spec.compose_name)
            decompose = self._cmds.createNode("decomposeMatrix", name=spec.decompose_name)
            quaternion = self._cmds.createNode("quatToEuler", name=spec.quaternion_name)
            self._cmds.connectAttr(f"{spec.end_joint}.rotate", f"{compose}.inputRotate")
            self._cmds.connectAttr(
                f"{spec.end_joint}.rotateOrder",
                f"{compose}.inputRotateOrder",
            )
            self._cmds.connectAttr(f"{compose}.outputMatrix", f"{decompose}.inputMatrix")
            self._cmds.connectAttr(
                f"{decompose}.outputQuatX",
                f"{quaternion}.inputQuatX",
            )
            self._cmds.connectAttr(
                f"{decompose}.outputQuatW",
                f"{quaternion}.inputQuatW",
            )
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def create_body_arm_twist_joint(self, spec: BodyArmTwistJointSpec) -> None:
        self._require_transaction()
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            if any(
                self.find_name_collisions(name)
                for name in (spec.name, spec.constraint_name, spec.multiplier_name)
            ):
                raise FitSkeletonValidationError("Arm twist joint、约束或角度节点名称冲突")
            if any(not self._cmds.objExists(path) for path in (spec.parent_path, spec.start_joint, spec.end_joint)):
                raise FitSkeletonValidationError("Arm twist 父级或 Body 端点在执行前失效")
            self._transaction_changed = True
            joint = self._cmds.createNode("joint", name=spec.name, parent=spec.parent_path, skipSelect=True)
            joint = (self._cmds.ls(joint, long=True) or [joint])[0]
            self._cmds.xform(joint, worldSpace=True, translation=spec.world_position)
            self._cmds.setAttr(f"{joint}.side", _MAYA_SIDE_FROM_CORE[spec.side])
            if joint != spec.path:
                raise RuntimeError("Arm twist joint 路径漂移")
            constraint = self._cmds.pointConstraint(
                spec.start_joint,
                spec.end_joint,
                joint,
                maintainOffset=False,
                name=spec.constraint_name,
            )[0]
            aliases = self._cmds.pointConstraint(constraint, query=True, weightAliasList=True) or []
            if len(aliases) != 2:
                raise RuntimeError("Arm twist 双端权重别名无效")
            self._cmds.setAttr(f"{constraint}.{aliases[0]}", 1.0 - spec.fraction)
            self._cmds.setAttr(f"{constraint}.{aliases[1]}", spec.fraction)
            multiplier = self._cmds.createNode(
                "unitConversion",
                name=spec.multiplier_name,
            )
            self._cmds.setAttr(f"{multiplier}.conversionFactor", spec.fraction)
            self._cmds.connectAttr(
                f"{spec.quaternion_name}.outputRotateX",
                f"{multiplier}.input",
            )
            self._cmds.connectAttr(f"{multiplier}.output", f"{joint}.rotateX")
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def capture_body_arm_twist(self, plan: BodyArmTwistPlan) -> BodyArmTwistSnapshot:
        roots = self._cmds.ls(plan.root_path, long=True, type="transform") or []
        if len(roots) != 1:
            raise FitSkeletonValidationError("Arm twist 根节点无效")
        def source(plug: str) -> str | None:
            values = self._cmds.listConnections(
                plug,
                source=True,
                destination=False,
                plugs=True,
            ) or []
            if len(values) != 1:
                return None
            node, attribute = values[0].split(".", 1)
            paths = self._cmds.ls(node, long=True) or [node]
            return f"{paths[0]}.{attribute}"

        segment_states = []
        for spec in plan.segments:
            bases = self._cmds.ls(spec.path, long=True, type="transform") or []
            constraints = self._cmds.ls(spec.constraint_name, type="parentConstraint") or []
            typed_nodes = (
                (spec.compose_name, "composeMatrix"),
                (spec.decompose_name, "decomposeMatrix"),
                (spec.quaternion_name, "quatToEuler"),
            )
            if (
                len(bases) != 1
                or len(constraints) != 1
                or any(len(self._cmds.ls(name, type=node_type) or []) != 1 for name, node_type in typed_nodes)
            ):
                raise FitSkeletonValidationError("Arm twist 段驱动节点无效")
            base, constraint = bases[0], constraints[0]
            parents = self._cmds.listRelatives(base, parent=True, fullPath=True) or []
            targets = self._cmds.parentConstraint(
                constraint,
                query=True,
                targetList=True,
            ) or []
            target_paths = tuple(
                (self._cmds.ls(target, long=True) or [target])[0]
                for target in targets
            )
            outputs = self._cmds.listConnections(
                f"{constraint}.constraintTranslateX",
                source=False,
                destination=True,
                plugs=True,
            ) or []
            segment_states.append(
                BodyArmTwistSegmentState(
                    spec.side,
                    spec.segment,
                    base,
                    parents[0] if parents else None,
                    constraint,
                    target_paths,
                    self._resolve_connected_node(outputs[0]) if len(outputs) == 1 else None,
                    spec.compose_name,
                    source(f"{spec.compose_name}.inputRotate"),
                    source(f"{spec.compose_name}.inputRotateOrder"),
                    spec.decompose_name,
                    source(f"{spec.decompose_name}.inputMatrix"),
                    spec.quaternion_name,
                    source(f"{spec.quaternion_name}.inputQuatX"),
                    source(f"{spec.quaternion_name}.inputQuatW"),
                )
            )

        states = []
        for spec in plan.joints:
            joints = self._cmds.ls(spec.path, long=True, type="joint") or []
            constraints = self._cmds.ls(spec.constraint_name, type="pointConstraint") or []
            multipliers = self._cmds.ls(spec.multiplier_name, type="unitConversion") or []
            if len(joints) != 1 or len(constraints) != 1 or len(multipliers) != 1:
                raise FitSkeletonValidationError("Arm twist joint、位置约束或角度节点无效")
            joint, constraint = joints[0], constraints[0]
            parents = self._cmds.listRelatives(joint, parent=True, fullPath=True) or []
            targets = self._cmds.pointConstraint(constraint, query=True, targetList=True) or []
            target_paths = tuple((self._cmds.ls(target, long=True) or [target])[0] for target in targets)
            aliases = self._cmds.pointConstraint(constraint, query=True, weightAliasList=True) or []
            weights = tuple(float(self._cmds.getAttr(f"{constraint}.{alias}")) for alias in aliases)
            outputs = self._cmds.listConnections(f"{constraint}.constraintTranslateX", source=False, destination=True, plugs=True) or []
            driven = self._resolve_connected_node(outputs[0]) if len(outputs) == 1 else None
            states.append(BodyArmTwistJointState(
                spec.side,
                spec.segment,
                joint,
                parents[0] if parents else None,
                tuple(float(value) for value in self._cmds.xform(joint, query=True, worldSpace=True, translation=True)),
                constraint,
                target_paths,
                weights,
                driven,
                spec.multiplier_name,
                source(f"{spec.multiplier_name}.input"),
                float(self._cmds.getAttr(f"{spec.multiplier_name}.conversionFactor")),
                source(f"{joint}.rotateX"),
                (
                    float(self._cmds.getAttr(f"{joint}.rotateY")),
                    float(self._cmds.getAttr(f"{joint}.rotateZ")),
                ),
            ))
        return BodyArmTwistSnapshot(roots[0], tuple(segment_states), tuple(states))

    def create_body_arm_volume(self, plan: BodyArmVolumePlan) -> None:
        self._require_transaction()
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            settings = self._cmds.ls(
                plan.settings_path,
                long=True,
                type="transform",
            ) or []
            if len(settings) != 1 or settings[0] != plan.settings_path:
                raise FitSkeletonValidationError("Arm 体积设置节点失效")
            for spec in plan.sides:
                plug = f"{plan.settings_path}.{spec.attribute}"
                if (
                    self._cmds.attributeQuery(
                        spec.attribute,
                        node=plan.settings_path,
                        exists=True,
                    )
                    or any(
                        self.find_name_collisions(name)
                        for name in (
                            spec.mode_blend_name,
                            spec.power_name,
                            spec.blend_name,
                        )
                    )
                    or any(not self._cmds.objExists(path) for path in spec.helper_joints)
                    or not self._cmds.objExists(spec.stretch_ratio_source)
                    or not self._cmds.objExists(
                        f"{plan.settings_path}.{spec.mode_attribute}"
                    )
                ):
                    raise FitSkeletonValidationError("Arm 体积输入或名称在执行前失效")
                self._transaction_changed = True
                self._cmds.addAttr(
                    plan.settings_path,
                    longName=spec.attribute,
                    attributeType="double",
                    minValue=0.0,
                    maxValue=1.0,
                    defaultValue=1.0,
                    keyable=True,
                )
                mode_blend = self._cmds.createNode(
                    "blendColors",
                    name=spec.mode_blend_name,
                )
                self._cmds.connectAttr(
                    spec.stretch_ratio_source,
                    f"{mode_blend}.color1R",
                )
                self._cmds.setAttr(f"{mode_blend}.color2R", 1.0)
                self._cmds.connectAttr(
                    f"{plan.settings_path}.{spec.mode_attribute}",
                    f"{mode_blend}.blender",
                )
                power = self._cmds.createNode(
                    "multiplyDivide",
                    name=spec.power_name,
                )
                self._cmds.setAttr(f"{power}.operation", 3)
                self._cmds.setAttr(f"{power}.input2X", spec.exponent)
                self._cmds.connectAttr(f"{mode_blend}.outputR", f"{power}.input1X")
                blend = self._cmds.createNode(
                    "blendColors",
                    name=spec.blend_name,
                )
                self._cmds.connectAttr(f"{power}.outputX", f"{blend}.color1R")
                self._cmds.setAttr(f"{blend}.color2R", 1.0)
                self._cmds.connectAttr(plug, f"{blend}.blender")
                for helper in spec.helper_joints:
                    self._cmds.connectAttr(f"{blend}.outputR", f"{helper}.scaleY")
                    self._cmds.connectAttr(f"{blend}.outputR", f"{helper}.scaleZ")
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def capture_body_arm_volume(
        self,
        plan: BodyArmVolumePlan,
    ) -> BodyArmVolumeSnapshot:
        def source(plug: str) -> str | None:
            values = self._cmds.listConnections(
                plug,
                source=True,
                destination=False,
                plugs=True,
            ) or []
            if len(values) != 1:
                return None
            node, attribute = values[0].split(".", 1)
            paths = self._cmds.ls(node, long=True) or [node]
            return f"{paths[0]}.{attribute}"

        settings = self._cmds.ls(
            plan.settings_path,
            long=True,
            type="transform",
        ) or []
        if len(settings) != 1:
            raise FitSkeletonValidationError("Arm 体积设置节点无效")
        states = []
        for spec in plan.sides:
            plug = f"{plan.settings_path}.{spec.attribute}"
            mode_blend = self._cmds.ls(spec.mode_blend_name, type="blendColors") or []
            power = self._cmds.ls(spec.power_name, type="multiplyDivide") or []
            blend = self._cmds.ls(spec.blend_name, type="blendColors") or []
            helpers = tuple(
                self._cmds.ls(path, long=True, type="joint") or []
                for path in spec.helper_joints
            )
            if (
                not self._cmds.objExists(plug)
                or len(mode_blend) != 1
                or len(power) != 1
                or len(blend) != 1
                or any(len(values) != 1 for values in helpers)
            ):
                raise FitSkeletonValidationError("Arm 体积节点集合无效")
            states.append(
                BodyArmVolumeSideState(
                    spec.side,
                    plug,
                    float(self._cmds.getAttr(plug)),
                    spec.mode_blend_name,
                    source(f"{spec.mode_blend_name}.color1R"),
                    source(f"{spec.mode_blend_name}.blender"),
                    float(self._cmds.getAttr(f"{spec.mode_blend_name}.color2R")),
                    spec.power_name,
                    source(f"{spec.power_name}.input1X"),
                    float(self._cmds.getAttr(f"{spec.power_name}.input2X")),
                    int(self._cmds.getAttr(f"{spec.power_name}.operation")),
                    spec.blend_name,
                    source(f"{spec.blend_name}.color1R"),
                    source(f"{spec.blend_name}.blender"),
                    float(self._cmds.getAttr(f"{spec.blend_name}.color2R")),
                    tuple(
                        (
                            path,
                            source(f"{path}.scaleY"),
                            source(f"{path}.scaleZ"),
                        )
                        for path in spec.helper_joints
                    ),
                )
            )
        return BodyArmVolumeSnapshot(settings[0], tuple(states))

    def capture_skin_bind_input(self, plan: SkinBindPlan) -> SkinBindInputState:
        meshes = self._cmds.ls(plan.mesh_path, long=True, type="transform") or []
        mesh = meshes[0] if len(meshes) == 1 else None
        shapes = tuple(
            self._cmds.listRelatives(
                mesh,
                shapes=True,
                noIntermediate=True,
                fullPath=True,
                type="mesh",
            ) or []
        ) if mesh else ()
        vertex_count = (
            int(self._cmds.polyEvaluate(mesh, vertex=True))
            if mesh and len(shapes) == 1
            else 0
        )
        available = []
        for path in plan.influence_paths:
            matches = self._cmds.ls(path, long=True, type="joint") or []
            if len(matches) == 1 and matches[0] == path:
                available.append(path)
        history = (
            self._cmds.listHistory(shapes[0], pruneDagObjects=True) or []
            if len(shapes) == 1
            else []
        )
        skin_clusters = tuple(
            sorted(
                node
                for node in history
                if self._cmds.nodeType(node) == "skinCluster"
            )
        )
        return SkinBindInputState(
            mesh,
            shapes,
            vertex_count,
            tuple(available),
            skin_clusters,
        )

    def create_skin_bind(self, plan: SkinBindPlan) -> None:
        self._require_transaction()
        if self.find_name_collisions(plan.skin_name):
            raise FitSkeletonValidationError(f"Skin Bind 节点名称冲突：{plan.skin_name}")
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            self._transaction_changed = True
            created = self._cmds.skinCluster(
                list(plan.influence_paths),
                plan.mesh_path,
                toSelectedBones=True,
                bindMethod=0,
                normalizeWeights=1,
                maximumInfluences=plan.maximum_influences,
                obeyMaxInfluences=True,
                name=plan.skin_name,
            )
            if not created or created[0] != plan.skin_name:
                raise RuntimeError("Maya 未按计划创建 skinCluster")
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def capture_skin_bind(self, plan: SkinBindPlan) -> SkinBindSnapshot:
        clusters = self._cmds.ls(plan.skin_name, type="skinCluster") or []
        if len(clusters) != 1:
            raise FitSkeletonValidationError("Skin Bind 结果节点无效")
        skin = clusters[0]
        geometry = []
        for shape in self._cmds.skinCluster(skin, query=True, geometry=True) or []:
            shape_paths = self._cmds.ls(shape, long=True, type="mesh") or []
            parents = (
                self._cmds.listRelatives(
                    shape_paths[0],
                    parent=True,
                    fullPath=True,
                ) or []
                if len(shape_paths) == 1
                else []
            )
            if len(parents) == 1:
                geometry.append(parents[0])
        influences = []
        for joint in self._cmds.skinCluster(skin, query=True, influence=True) or []:
            matches = self._cmds.ls(joint, long=True, type="joint") or []
            if len(matches) == 1:
                influences.append(matches[0])
        bind_method = {0: SkinBindMethod.CLOSEST_DISTANCE}.get(
            int(self._cmds.getAttr(f"{skin}.bindMethod"))
        )
        normalization = {1: SkinWeightNormalization.INTERACTIVE}.get(
            int(self._cmds.getAttr(f"{skin}.normalizeWeights"))
        )
        return SkinBindSnapshot(
            skin,
            tuple(geometry),
            tuple(influences),
            int(self._cmds.getAttr(f"{skin}.maxInfluences")),
            bool(self._cmds.getAttr(f"{skin}.maintainMaxInfluences")),
            bind_method,
            normalization,
        )

    def capture_skin_weight_input(
        self,
        request: SkinWeightEditRequest,
    ) -> SkinWeightInputState:
        return self._capture_skin_weight_state(
            request.skin_name,
            tuple(vertex.vertex_index for vertex in request.vertices),
        )

    def capture_all_skin_weights(
        self,
        skin_name: str,
        mesh_path: str,
    ) -> SkinWeightInputState:
        del mesh_path
        return self._capture_skin_weight_state(skin_name, None)

    def capture_skin_vertices(
        self,
        skin_name: str,
        mesh_path: str,
        vertex_indices: tuple[int, ...],
    ) -> SkinWeightInputState:
        del mesh_path
        return self._capture_skin_weight_state(skin_name, vertex_indices)

    def capture_mesh_vertex_positions(self, mesh_path: str) -> SkinMeshGeometryState:
        matches = self._cmds.ls(mesh_path, long=True, type="transform") or []
        if len(matches) != 1 or matches[0] != mesh_path:
            return SkinMeshGeometryState(None, 0, ())
        shapes = self._cmds.listRelatives(
            mesh_path,
            shapes=True,
            noIntermediate=True,
            fullPath=True,
            type="mesh",
        ) or []
        if len(shapes) != 1:
            return SkinMeshGeometryState(None, 0, ())
        vertex_count = int(self._cmds.polyEvaluate(mesh_path, vertex=True))
        vertices = tuple(
            SkinMeshVertexPosition(
                index,
                tuple(
                    float(value)
                    for value in self._cmds.pointPosition(
                        f"{mesh_path}.vtx[{index}]",
                        world=True,
                    )
                ),
            )
            for index in range(vertex_count)
        )
        return SkinMeshGeometryState(mesh_path, vertex_count, vertices)

    def _capture_skin_weight_state(
        self,
        skin_name: str,
        vertex_indices: tuple[int, ...] | None,
    ) -> SkinWeightInputState:
        clusters = self._cmds.ls(skin_name, type="skinCluster") or []
        if len(clusters) != 1:
            return SkinWeightInputState(None, None, 0, (), (), 0, False, ())
        skin = clusters[0]
        geometry = []
        for shape in self._cmds.skinCluster(skin, query=True, geometry=True) or []:
            shape_paths = self._cmds.ls(shape, long=True, type="mesh") or []
            parents = (
                self._cmds.listRelatives(
                    shape_paths[0],
                    parent=True,
                    fullPath=True,
                ) or []
                if len(shape_paths) == 1
                else []
            )
            if len(parents) == 1:
                geometry.append(parents[0])
        mesh = geometry[0] if len(geometry) == 1 else None
        vertex_count = int(self._cmds.polyEvaluate(mesh, vertex=True)) if mesh else 0
        influences = []
        locked = []
        for joint in self._cmds.skinCluster(skin, query=True, influence=True) or []:
            matches = self._cmds.ls(joint, long=True, type="joint") or []
            if len(matches) != 1:
                continue
            path = matches[0]
            influences.append(path)
            if self._cmds.attributeQuery(
                "lockInfluenceWeights",
                node=path,
                exists=True,
            ) and self._cmds.getAttr(f"{path}.lockInfluenceWeights"):
                locked.append(path)
        vertices = []
        if mesh:
            indices = (
                range(vertex_count)
                if vertex_indices is None
                else vertex_indices
            )
            for vertex_index in indices:
                if vertex_index >= vertex_count:
                    continue
                component = f"{mesh}.vtx[{vertex_index}]"
                weights = []
                for influence in influences:
                    value = float(self._cmds.skinPercent(
                        skin,
                        component,
                        query=True,
                        transform=influence,
                    ))
                    if value > 1e-8:
                        weights.append(SkinInfluenceWeight(influence, value))
                vertices.append(SkinVertexWeights(vertex_index, tuple(weights)))
        return SkinWeightInputState(
            skin,
            mesh,
            vertex_count,
            tuple(influences),
            tuple(locked),
            int(self._cmds.getAttr(f"{skin}.maxInfluences")),
            bool(self._cmds.getAttr(f"{skin}.maintainMaxInfluences")),
            tuple(vertices),
        )

    def apply_skin_weight_changes(
        self,
        request: SkinWeightEditRequest,
        changes: tuple[SkinWeightChange, ...],
    ) -> None:
        self._require_transaction()
        if not changes:
            return
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            self._transaction_changed = True
            for change in changes:
                self._cmds.skinPercent(
                    request.skin_name,
                    f"{request.mesh_path}.vtx[{change.vertex_index}]",
                    transformValue=[
                        (entry.influence_path, entry.weight)
                        for entry in change.after
                    ],
                    normalize=False,
                    zeroRemainingInfluences=True,
                )
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def capture_body_arm_fk_to_ik_state(self, plan: BodyArmFkToIkPlan) -> BodyArmFkToIkSceneState:
        existing = tuple(path for path in plan.required_paths if self._cmds.objExists(path))
        writable = tuple(
            plug
            for plug in plan.required_writable_plugs
            if self._cmds.objExists(plug) and self._cmds.getAttr(plug, settable=True)
        )
        value = float(self._cmds.getAttr(plan.blend_plug)) if self._cmds.objExists(plan.blend_plug) else float("nan")
        return BodyArmFkToIkSceneState(existing, writable, value)

    def apply_body_arm_fk_to_ik(self, plan: BodyArmFkToIkPlan) -> None:
        self._require_transaction()
        state = self.capture_body_arm_fk_to_ik_state(plan)
        if set(state.existing_paths) != set(plan.required_paths) or set(state.writable_plugs) != set(plan.required_writable_plugs) or abs(state.blend_value) > 1e-6:
            raise FitSkeletonValidationError("Arm FK→IK 匹配输入在执行前失效")
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            self._transaction_changed = True
            self._cmds.xform(plan.pole_control_path, worldSpace=True, translation=plan.pole_position)
            x_axis, y_axis, z_axis = plan.wrist_axes
            matrix = (*x_axis, 0.0, *y_axis, 0.0, *z_axis, 0.0, *plan.wrist_position, 1.0)
            self._cmds.xform(plan.wrist_control_path, worldSpace=True, matrix=matrix)
            self._cmds.setAttr(plan.blend_plug, 1.0)
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def capture_body_leg_fk_to_ik_state(
        self, plan: BodyLegFkToIkPlan
    ) -> BodyLegFkToIkSceneState:
        existing = tuple(
            path for path in plan.required_paths if self._cmds.objExists(path)
        )
        writable = tuple(
            plug
            for plug in plan.required_writable_plugs
            if self._cmds.objExists(plug)
            and self._cmds.getAttr(plug, settable=True)
        )
        value = (
            float(self._cmds.getAttr(plan.blend_plug))
            if self._cmds.objExists(plan.blend_plug)
            else float("nan")
        )
        positions = []
        for path in plan.body_joint_paths:
            if not self._cmds.objExists(path):
                break
            positions.append(tuple(float(item) for item in self._cmds.xform(
                path, query=True, worldSpace=True, translation=True
            )))
        ankle_axes = ()
        ankle_path = plan.body_joint_paths[2]
        if self._cmds.objExists(ankle_path):
            matrix = self._cmds.xform(
                ankle_path, query=True, worldSpace=True, matrix=True
            )
            ankle_axes = tuple(
                self._normalized_vector(
                    tuple(float(item) for item in matrix[index:index + 3])
                )
                for index in (0, 4, 8)
            )
        return BodyLegFkToIkSceneState(
            existing, writable, value, tuple(positions), ankle_axes
        )

    def apply_body_leg_fk_to_ik(self, plan: BodyLegFkToIkPlan) -> None:
        self._require_transaction()
        state = self.capture_body_leg_fk_to_ik_state(plan)
        if audit_body_leg_fk_to_ik_preflight(plan, state):
            raise FitSkeletonValidationError("Leg FK→IK 匹配输入在执行前失效")
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            self._transaction_changed = True
            self._cmds.xform(
                plan.pole_control_path,
                worldSpace=True,
                translation=plan.pole_position,
            )
            x_axis, y_axis, z_axis = plan.ankle_axes
            matrix = (
                *x_axis, 0.0,
                *y_axis, 0.0,
                *z_axis, 0.0,
                *plan.ankle_position, 1.0,
            )
            self._cmds.xform(
                plan.ankle_control_path, worldSpace=True, matrix=matrix
            )
            self._cmds.setAttr(plan.blend_plug, 1.0)
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def capture_body_arm_ik_to_fk_state(self, plan: BodyArmIkToFkPlan) -> BodyArmIkToFkSceneState:
        existing = tuple(path for path in plan.required_paths if self._cmds.objExists(path))
        writable = tuple(
            plug
            for plug in plan.required_writable_plugs
            if self._cmds.objExists(plug) and self._cmds.getAttr(plug, settable=True)
        )
        value = float(self._cmds.getAttr(plan.blend_plug)) if self._cmds.objExists(plan.blend_plug) else float("nan")
        positions = []
        axes = []
        for path in plan.body_joint_paths:
            if not self._cmds.objExists(path):
                break
            positions.append(tuple(float(item) for item in self._cmds.xform(
                path,
                query=True,
                worldSpace=True,
                translation=True,
            )))
            matrix = self._cmds.xform(
                path,
                query=True,
                worldSpace=True,
                matrix=True,
            )
            axes.append(tuple(
                self._normalized_vector(
                    tuple(float(item) for item in matrix[index : index + 3])
                )
                for index in (0, 4, 8)
            ))
        segment_translations = tuple(
            float(self._cmds.getAttr(plug))
            for plug in plan.fk_segment_plugs
            if self._cmds.objExists(plug)
        )
        return BodyArmIkToFkSceneState(
            existing,
            writable,
            value,
            tuple(positions),
            tuple(axes),
            segment_translations,
        )

    def apply_body_arm_ik_to_fk(self, plan: BodyArmIkToFkPlan) -> None:
        self._require_transaction()
        state = self.capture_body_arm_ik_to_fk_state(plan)
        if set(state.existing_paths) != set(plan.required_paths) or set(state.writable_plugs) != set(plan.required_writable_plugs) or abs(state.blend_value - 1.0) > 1e-6:
            raise FitSkeletonValidationError("Arm IK→FK 匹配输入在执行前失效")
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            self._transaction_changed = True
            for path, target_axes in zip(plan.fk_control_paths, plan.fk_control_axes):
                position = self._cmds.xform(path, query=True, worldSpace=True, translation=True)
                x_axis, y_axis, z_axis = target_axes
                matrix = (*x_axis, 0.0, *y_axis, 0.0, *z_axis, 0.0, *position, 1.0)
                self._cmds.xform(path, worldSpace=True, matrix=matrix)
            for plug, value in zip(
                plan.fk_segment_plugs,
                plan.fk_segment_translations,
            ):
                self._cmds.setAttr(plug, value)
            self._cmds.setAttr(plan.blend_plug, 0.0)
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def create_body_arm_ik(self, spec: BodyArmIkSpec) -> None:
        self._require_transaction()
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            for name in (spec.wrist_offset_name, spec.wrist_control_name, spec.pole_offset_name, spec.pole_control_name, spec.handle_name, spec.pole_constraint_name, spec.wrist_constraint_name):
                if self.find_name_collisions(name):
                    raise FitSkeletonValidationError(f"Arm IK 名称冲突：{name}")
            if any(not self._cmds.objExists(path) for path in spec.chain):
                raise FitSkeletonValidationError("Arm IK mechanism chain 在执行前失效")
            self._transaction_changed = True
            wrist_offset = self._cmds.createNode("transform", name=spec.wrist_offset_name, parent=spec.root_path, skipSelect=True)
            wrist_offset = (self._cmds.ls(wrist_offset, long=True) or [wrist_offset])[0]
            x_axis, y_axis, z_axis = spec.wrist_axes
            matrix = (*x_axis, 0.0, *y_axis, 0.0, *z_axis, 0.0, *spec.wrist_position, 1.0)
            self._cmds.xform(wrist_offset, worldSpace=True, matrix=matrix)
            wrist = self._cmds.circle(name=spec.wrist_control_name, normal=(1, 0, 0), radius=spec.radius, degree=3, sections=12, constructionHistory=False)[0]
            wrist = self._cmds.parent(wrist, wrist_offset, relative=True)[0]
            wrist = (self._cmds.ls(wrist, long=True) or [wrist])[0]
            pole_offset = self._cmds.createNode("transform", name=spec.pole_offset_name, parent=spec.root_path, skipSelect=True)
            pole_offset = (self._cmds.ls(pole_offset, long=True) or [pole_offset])[0]
            self._cmds.xform(pole_offset, worldSpace=True, translation=spec.pole_position)
            pole = self._cmds.circle(name=spec.pole_control_name, normal=(0, 0, 1), radius=spec.radius * 0.65, degree=3, sections=8, constructionHistory=False)[0]
            pole = self._cmds.parent(pole, pole_offset, relative=True)[0]
            pole = (self._cmds.ls(pole, long=True) or [pole])[0]
            if wrist != spec.wrist_control_path or pole != spec.pole_control_path:
                raise RuntimeError("Arm IK 控制路径漂移")
            handle, _ = self._cmds.ikHandle(name=spec.handle_name, startJoint=spec.chain[0], endEffector=spec.chain[2], solver="ikRPsolver")
            self._cmds.parent(handle, wrist, absolute=True)
            self._cmds.poleVectorConstraint(pole, handle, name=spec.pole_constraint_name)
            self._cmds.orientConstraint(
                wrist,
                spec.chain[2],
                maintainOffset=False,
                name=spec.wrist_constraint_name,
            )
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def capture_body_arm_ik(self, plan: BodyArmIkPlan) -> BodyArmIkSnapshot:
        roots = self._cmds.ls(plan.root_path, long=True, type="transform") or []
        if len(roots) != 1: raise FitSkeletonValidationError("Arm IK 控制根节点无效")
        states = []
        for spec in plan.limbs:
            wrist = (self._cmds.ls(spec.wrist_control_path, long=True, type="transform") or [None])[0]
            pole = (self._cmds.ls(spec.pole_control_path, long=True, type="transform") or [None])[0]
            handles = self._cmds.ls(spec.handle_name, long=True, type="ikHandle") or []
            constraints = self._cmds.ls(spec.pole_constraint_name, type="poleVectorConstraint") or []
            wrist_constraints = self._cmds.ls(spec.wrist_constraint_name, type="orientConstraint") or []
            if wrist is None or pole is None or len(handles) != 1 or len(constraints) != 1 or len(wrist_constraints) != 1:
                raise FitSkeletonValidationError("Arm IK 节点集合无效")
            handle = handles[0]
            wp = self._cmds.listRelatives(wrist, parent=True, fullPath=True) or []
            pp = self._cmds.listRelatives(pole, parent=True, fullPath=True) or []
            hp = self._cmds.listRelatives(handle, parent=True, fullPath=True) or []
            joint_list = tuple((self._cmds.ls(value, long=True) or [value])[0] for value in (self._cmds.ikHandle(handle, query=True, jointList=True) or []))
            targets = self._cmds.poleVectorConstraint(constraints[0], query=True, targetList=True) or []
            pole_source = (self._cmds.ls(targets[0], long=True) or [targets[0]])[0] if len(targets) == 1 else None
            wrist_targets = self._cmds.orientConstraint(wrist_constraints[0], query=True, targetList=True) or []
            wrist_source = (self._cmds.ls(wrist_targets[0], long=True) or [wrist_targets[0]])[0] if len(wrist_targets) == 1 else None
            wrist_outputs = self._cmds.listConnections(f"{wrist_constraints[0]}.constraintRotateX", source=False, destination=True, plugs=True) or []
            wrist_driven = self._resolve_connected_node(wrist_outputs[0]) if len(wrist_outputs) == 1 else None
            def shape_type(node):
                shapes = self._cmds.listRelatives(node, shapes=True, noIntermediate=True, fullPath=True) or []
                return self._cmds.nodeType(shapes[0]) if len(shapes) == 1 else None
            def vector(node, attr): return tuple(float(v) for v in self._cmds.getAttr(f"{node}.{attr}")[0])
            states.append(BodyArmIkState(
                spec.side, wrist, wp[0] if wp else None, pole, pp[0] if pp else None,
                spec.handle_name, constraints[0], hp[0] if hp else None, joint_list, pole_source,
                tuple(float(v) for v in self._cmds.xform(wrist, query=True, worldSpace=True, translation=True)),
                tuple(float(v) for v in self._cmds.xform(pole, query=True, worldSpace=True, translation=True)),
                shape_type(wrist), shape_type(pole), vector(wrist, "translate"), vector(wrist, "rotate"), vector(pole, "translate"), vector(pole, "rotate"),
                wrist_constraints[0], wrist_source, wrist_driven,
            ))
        return BodyArmIkSnapshot(roots[0], tuple(states))

    def create_body_leg_ik(self, spec: BodyLegIkSpec) -> None:
        self._require_transaction()
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            names = (
                spec.ankle_offset_name,
                spec.ankle_control_name,
                spec.pole_offset_name,
                spec.pole_control_name,
                spec.handle_name,
                spec.pole_constraint_name,
                spec.ankle_constraint_name,
            )
            if any(self.find_name_collisions(name) for name in names):
                raise FitSkeletonValidationError("Leg IK 名称冲突")
            if any(not self._cmds.objExists(path) for path in spec.chain):
                raise FitSkeletonValidationError(
                    "Leg IK mechanism chain 在执行前失效"
                )
            self._transaction_changed = True
            ankle_offset = self._cmds.createNode(
                "transform",
                name=spec.ankle_offset_name,
                parent=spec.root_path,
                skipSelect=True,
            )
            ankle_offset = (
                self._cmds.ls(ankle_offset, long=True) or [ankle_offset]
            )[0]
            x_axis, y_axis, z_axis = spec.ankle_axes
            matrix = (
                *x_axis,
                0.0,
                *y_axis,
                0.0,
                *z_axis,
                0.0,
                *spec.ankle_position,
                1.0,
            )
            self._cmds.xform(ankle_offset, worldSpace=True, matrix=matrix)
            ankle = self._cmds.circle(
                name=spec.ankle_control_name,
                normal=(1.0, 0.0, 0.0),
                radius=spec.radius,
                degree=3,
                sections=12,
                constructionHistory=False,
            )[0]
            ankle = self._cmds.parent(ankle, ankle_offset, relative=True)[0]
            ankle = (self._cmds.ls(ankle, long=True) or [ankle])[0]
            pole_offset = self._cmds.createNode(
                "transform",
                name=spec.pole_offset_name,
                parent=spec.root_path,
                skipSelect=True,
            )
            pole_offset = (
                self._cmds.ls(pole_offset, long=True) or [pole_offset]
            )[0]
            self._cmds.xform(
                pole_offset,
                worldSpace=True,
                translation=spec.pole_position,
            )
            pole = self._cmds.circle(
                name=spec.pole_control_name,
                normal=(0.0, 0.0, 1.0),
                radius=spec.radius * 0.65,
                degree=3,
                sections=8,
                constructionHistory=False,
            )[0]
            pole = self._cmds.parent(pole, pole_offset, relative=True)[0]
            pole = (self._cmds.ls(pole, long=True) or [pole])[0]
            if (
                ankle != spec.ankle_control_path
                or pole != spec.pole_control_path
            ):
                raise RuntimeError("Leg IK 控制路径漂移")
            handle, _ = self._cmds.ikHandle(
                name=spec.handle_name,
                startJoint=spec.chain[0],
                endEffector=spec.chain[2],
                solver="ikRPsolver",
            )
            self._cmds.parent(handle, ankle, absolute=True)
            self._cmds.poleVectorConstraint(
                pole,
                handle,
                name=spec.pole_constraint_name,
            )
            self._cmds.orientConstraint(
                ankle,
                spec.chain[2],
                maintainOffset=False,
                name=spec.ankle_constraint_name,
            )
        finally:
            if selection:
                self._cmds.select(selection, replace=True)
            else:
                self._cmds.select(clear=True)

    def capture_body_leg_ik(self, plan: BodyLegIkPlan) -> BodyLegIkSnapshot:
        roots = self._cmds.ls(plan.root_path, long=True, type="transform") or []
        if len(roots) != 1:
            raise FitSkeletonValidationError("Leg IK 控制根节点无效")
        states = []
        for spec in plan.limbs:
            ankle = (
                self._cmds.ls(
                    spec.ankle_control_path,
                    long=True,
                    type="transform",
                )
                or [None]
            )[0]
            pole = (
                self._cmds.ls(
                    spec.pole_control_path,
                    long=True,
                    type="transform",
                )
                or [None]
            )[0]
            handles = self._cmds.ls(
                spec.handle_name,
                long=True,
                type="ikHandle",
            ) or []
            pole_constraints = self._cmds.ls(
                spec.pole_constraint_name,
                type="poleVectorConstraint",
            ) or []
            ankle_constraints = self._cmds.ls(
                spec.ankle_constraint_name,
                type="orientConstraint",
            ) or []
            if (
                ankle is None
                or pole is None
                or len(handles) != 1
                or len(pole_constraints) != 1
                or len(ankle_constraints) != 1
            ):
                raise FitSkeletonValidationError("Leg IK 节点集合无效")
            handle = handles[0]
            ankle_parent = self._cmds.listRelatives(
                ankle, parent=True, fullPath=True
            ) or []
            pole_parent = self._cmds.listRelatives(
                pole, parent=True, fullPath=True
            ) or []
            handle_parent = self._cmds.listRelatives(
                handle, parent=True, fullPath=True
            ) or []
            joint_list = tuple(
                (self._cmds.ls(value, long=True) or [value])[0]
                for value in (
                    self._cmds.ikHandle(handle, query=True, jointList=True) or []
                )
            )
            pole_targets = self._cmds.poleVectorConstraint(
                pole_constraints[0],
                query=True,
                targetList=True,
            ) or []
            pole_source = (
                (self._cmds.ls(pole_targets[0], long=True) or [pole_targets[0]])[0]
                if len(pole_targets) == 1
                else None
            )
            ankle_targets = self._cmds.orientConstraint(
                ankle_constraints[0],
                query=True,
                targetList=True,
            ) or []
            ankle_source = (
                (self._cmds.ls(ankle_targets[0], long=True) or [ankle_targets[0]])[0]
                if len(ankle_targets) == 1
                else None
            )
            outputs = self._cmds.listConnections(
                f"{ankle_constraints[0]}.constraintRotateX",
                source=False,
                destination=True,
                plugs=True,
            ) or []
            ankle_driven = (
                self._resolve_connected_node(outputs[0])
                if len(outputs) == 1
                else None
            )

            def shape_type(node):
                shapes = self._cmds.listRelatives(
                    node,
                    shapes=True,
                    noIntermediate=True,
                    fullPath=True,
                ) or []
                return (
                    self._cmds.nodeType(shapes[0])
                    if len(shapes) == 1
                    else None
                )

            def vector(node, attribute):
                return tuple(
                    float(value)
                    for value in self._cmds.getAttr(
                        f"{node}.{attribute}"
                    )[0]
                )

            states.append(BodyLegIkState(
                side=spec.side,
                ankle_control_path=ankle,
                ankle_parent_path=(ankle_parent[0] if ankle_parent else None),
                pole_control_path=pole,
                pole_parent_path=(pole_parent[0] if pole_parent else None),
                handle_name=spec.handle_name,
                pole_constraint_name=pole_constraints[0],
                handle_parent_path=(handle_parent[0] if handle_parent else None),
                joint_list=joint_list,
                pole_source=pole_source,
                ankle_position=tuple(
                    float(value)
                    for value in self._cmds.xform(
                        ankle,
                        query=True,
                        worldSpace=True,
                        translation=True,
                    )
                ),
                pole_position=tuple(
                    float(value)
                    for value in self._cmds.xform(
                        pole,
                        query=True,
                        worldSpace=True,
                        translation=True,
                    )
                ),
                ankle_shape=shape_type(ankle),
                pole_shape=shape_type(pole),
                ankle_translation=vector(ankle, "translate"),
                ankle_rotation=vector(ankle, "rotate"),
                pole_translation=vector(pole, "translate"),
                pole_rotation=vector(pole, "rotate"),
                ankle_constraint_name=ankle_constraints[0],
                ankle_source=ankle_source,
                ankle_driven_joint=ankle_driven,
            ))
        return BodyLegIkSnapshot(roots[0], tuple(states))

    def create_body_arm_mechanism_root(self, name: str) -> str:
        self._require_transaction()
        if self.find_name_collisions(name):
            raise FitSkeletonValidationError(f"Arm 机制链根名称冲突：{name}")
        self._transaction_changed = True
        created = self._cmds.createNode(
            "transform",
            name=name,
            skipSelect=True,
        )
        return (self._cmds.ls(created, long=True) or [created])[0]

    def create_body_arm_mechanism_joint(
        self,
        spec: BodyArmMechanismJointSpec,
    ) -> str:
        self._require_transaction()
        if self.find_name_collisions(spec.name):
            raise FitSkeletonValidationError(f"Arm 机制关节名称冲突：{spec.name}")
        parents = self._cmds.ls(spec.parent_path, long=True) or []
        sources = self._cmds.ls(spec.source_joint, long=True, type="joint") or []
        if (
            len(parents) != 1
            or self._cmds.nodeType(parents[0]) not in {"transform", "joint"}
            or len(sources) != 1
            or sources[0] != spec.source_joint
        ):
            raise FitSkeletonValidationError(
                f"Arm 机制关节父级或来源失效：{spec.name}"
            )
        self._transaction_changed = True
        joint = self._cmds.createNode(
            "joint",
            name=spec.name,
            parent=parents[0],
            skipSelect=True,
        )
        joint = (self._cmds.ls(joint, long=True) or [joint])[0]
        self._cmds.xform(
            joint,
            worldSpace=True,
            translation=spec.world_position,
        )
        self._set_joint_world_axes(joint, spec.world_axes)
        self._cmds.setAttr(f"{joint}.side", _MAYA_SIDE_FROM_CORE[spec.side])
        self._cmds.addAttr(joint, longName="advPySourceJoint", attributeType="message")
        self._cmds.connectAttr(
            f"{sources[0]}.message",
            f"{joint}.advPySourceJoint",
        )
        return joint

    def capture_body_arm_mechanisms(
        self,
        plan: BodyArmMechanismPlan,
    ) -> BodyArmMechanismSnapshot:
        roots = self._cmds.ls(plan.root_path, long=True, type="transform") or []
        if len(roots) != 1:
            raise FitSkeletonValidationError("Arm 机制链根节点无效")
        paths = self._cmds.listRelatives(
            roots[0],
            allDescendents=True,
            type="joint",
            fullPath=True,
        ) or []
        states: list[BodyArmMechanismJointState] = []
        for path in sorted(set(paths), key=lambda value: (value.count("|"), value)):
            parents = self._cmds.listRelatives(path, parent=True, fullPath=True) or []
            position = self._cmds.xform(
                path,
                query=True,
                worldSpace=True,
                translation=True,
            )
            matrix = self._cmds.xform(
                path,
                query=True,
                worldSpace=True,
                matrix=True,
            )
            world_axes = tuple(
                self._normalized_vector(
                    tuple(float(value) for value in matrix[index : index + 3])
                )
                for index in (0, 4, 8)
            )
            source_nodes = []
            if self._cmds.attributeQuery(
                "advPySourceJoint",
                node=path,
                exists=True,
            ):
                source_nodes = self._cmds.listConnections(
                    f"{path}.advPySourceJoint",
                    source=True,
                    destination=False,
                    type="joint",
                ) or []
            source = None
            if len(source_nodes) == 1:
                source = (
                    self._cmds.ls(source_nodes[0], long=True) or [source_nodes[0]]
                )[0]
            side_code = int(self._cmds.getAttr(f"{path}.side"))
            side = _CORE_SIDE_FROM_MAYA.get(side_code)
            if side is None:
                raise FitSkeletonValidationError(
                    f"Arm 机制关节侧向值无效：{path}.side={side_code}"
                )
            rotation = self._cmds.getAttr(f"{path}.rotate")[0]
            states.append(
                BodyArmMechanismJointState(
                    path=path,
                    parent_path=parents[0] if parents else None,
                    side=side,
                    source_joint=source,
                    world_position=tuple(float(value) for value in position),
                    world_axes=world_axes,
                    rotation=tuple(float(value) for value in rotation),
                )
            )
        return BodyArmMechanismSnapshot(roots[0], tuple(states))

    def create_body_leg_mechanism_root(self, name: str) -> str:
        return self.create_body_arm_mechanism_root(name)

    def create_body_leg_mechanism_joint(
        self,
        spec: BodyLegMechanismJointSpec,
    ) -> str:
        return self.create_body_arm_mechanism_joint(spec)

    def capture_body_leg_mechanisms(
        self,
        plan: BodyLegMechanismPlan,
    ) -> BodyLegMechanismSnapshot:
        return self.capture_body_arm_mechanisms(plan)

    def create_body_arm_fk_control(self, spec: BodyArmFkControlSpec) -> None:
        self._create_body_limb_fk_control(spec, "Arm")

    def create_body_leg_fk_control(self, spec: BodyLegFkControlSpec) -> None:
        self._create_body_limb_fk_control(spec, "Leg")

    def _create_body_limb_fk_control(
        self,
        spec: BodyArmFkControlSpec,
        limb_label: str,
    ) -> None:
        self._require_transaction()
        selection = self._cmds.ls(selection=True, long=True) or []
        for name in (spec.offset_name, spec.control_name, spec.constraint_name):
            if self.find_name_collisions(name):
                raise FitSkeletonValidationError(
                    f"{limb_label} FK 控制名称冲突：{name}"
                )
        parent = self._cmds.ls(spec.parent_path, long=True, type="transform") or []
        driven = self._cmds.ls(spec.driven_joint, long=True, type="joint") or []
        if len(parent) != 1 or len(driven) != 1:
            raise FitSkeletonValidationError(
                f"{limb_label} FK 控制父级或驱动关节失效：{spec.control_name}"
            )
        self._transaction_changed = True
        try:
            offset = self._cmds.createNode(
                "transform",
                name=spec.offset_name,
                parent=parent[0],
                skipSelect=True,
            )
            offset = (self._cmds.ls(offset, long=True) or [offset])[0]
            x_axis, y_axis, z_axis = spec.world_axes
            matrix = (
                *x_axis,
                0.0,
                *y_axis,
                0.0,
                *z_axis,
                0.0,
                *spec.world_position,
                1.0,
            )
            self._cmds.xform(offset, worldSpace=True, matrix=matrix)
            control = self._cmds.circle(
                name=spec.control_name,
                normal=(1.0, 0.0, 0.0),
                radius=spec.radius,
                degree=3,
                sections=12,
                constructionHistory=False,
            )[0]
            control = self._cmds.parent(control, offset, relative=True)[0]
            control = (self._cmds.ls(control, long=True) or [control])[0]
            if offset != spec.offset_path or control != spec.control_path:
                raise RuntimeError(
                    f"{limb_label} FK 控制路径漂移：{spec.control_name}"
                )
            self._cmds.orientConstraint(
                control,
                driven[0],
                maintainOffset=False,
                name=spec.constraint_name,
            )
        finally:
            if selection:
                self._cmds.select(selection, replace=True)
            else:
                self._cmds.select(clear=True)

    def capture_body_arm_fk_controls(
        self,
        plan: BodyArmFkControlPlan,
    ) -> BodyArmFkControlSnapshot:
        return self._capture_body_limb_fk_controls(plan, "Arm")

    def capture_body_leg_fk_controls(
        self,
        plan: BodyLegFkControlPlan,
    ) -> BodyLegFkControlSnapshot:
        return self._capture_body_limb_fk_controls(plan, "Leg")

    def _capture_body_limb_fk_controls(
        self,
        plan: BodyArmFkControlPlan,
        limb_label: str,
    ) -> BodyArmFkControlSnapshot:
        roots = self._cmds.ls(plan.root_path, long=True, type="transform") or []
        if len(roots) != 1:
            raise FitSkeletonValidationError(
                f"{limb_label} FK 控制根节点无效"
            )
        states: list[BodyArmFkControlState] = []
        for spec in plan.controls:
            offsets = self._cmds.ls(spec.offset_path, long=True, type="transform") or []
            controls = self._cmds.ls(spec.control_path, long=True, type="transform") or []
            constraints = self._cmds.ls(spec.constraint_name, type="orientConstraint") or []
            if len(offsets) != 1 or len(controls) != 1 or len(constraints) != 1:
                raise FitSkeletonValidationError(
                    f"{limb_label} FK 控制或约束无效：{spec.control_name}"
                )
            offset, control, constraint = offsets[0], controls[0], constraints[0]
            offset_parent = self._cmds.listRelatives(
                offset, parent=True, fullPath=True
            ) or []
            control_parent = self._cmds.listRelatives(
                control, parent=True, fullPath=True
            ) or []
            position = self._cmds.xform(
                control, query=True, worldSpace=True, translation=True
            )
            matrix = self._cmds.xform(
                control, query=True, worldSpace=True, matrix=True
            )
            world_axes = tuple(
                self._normalized_vector(
                    tuple(float(value) for value in matrix[index : index + 3])
                )
                for index in (0, 4, 8)
            )
            local_translation = self._cmds.getAttr(f"{control}.translate")[0]
            local_rotation = self._cmds.getAttr(f"{control}.rotate")[0]
            shapes = self._cmds.listRelatives(
                control,
                shapes=True,
                noIntermediate=True,
                fullPath=True,
            ) or []
            targets = self._cmds.orientConstraint(
                constraint,
                query=True,
                targetList=True,
            ) or []
            source = None
            if len(targets) == 1:
                source = (self._cmds.ls(targets[0], long=True) or [targets[0]])[0]
            outputs = self._cmds.listConnections(
                f"{constraint}.constraintRotateX",
                source=False,
                destination=True,
                plugs=True,
            ) or []
            driven_joint = None
            if len(outputs) == 1:
                driven_joint = self._resolve_connected_node(outputs[0])
            states.append(
                BodyArmFkControlState(
                    offset_path=offset,
                    offset_parent_path=offset_parent[0] if offset_parent else None,
                    control_path=control,
                    control_parent_path=control_parent[0] if control_parent else None,
                    constraint_name=constraint,
                    source_control=source,
                    driven_joint=driven_joint,
                    world_position=tuple(float(value) for value in position),
                    world_axes=world_axes,
                    local_translation=tuple(float(value) for value in local_translation),
                    local_rotation=tuple(float(value) for value in local_rotation),
                    shape_type=(self._cmds.nodeType(shapes[0]) if len(shapes) == 1 else None),
                )
            )
        return BodyArmFkControlSnapshot(roots[0], tuple(states))

    def set_body_joint_world_axes(
        self,
        change: BodyJointOrientationChange,
    ) -> None:
        self._require_transaction()
        matches = self._cmds.ls(change.joint, long=True, type="joint") or []
        if len(matches) != 1 or matches[0] != change.joint:
            raise FitSkeletonValidationError(
                f"Body joint 在执行前失效：{change.joint}"
            )
        for axis in ("X", "Y", "Z"):
            attribute = f"{matches[0]}.jointOrient{axis}"
            if not self._cmds.getAttr(attribute, settable=True):
                raise FitSkeletonValidationError(
                    f"Body joint 朝向轴在执行前变为不可写：{attribute}"
                )
        self._transaction_changed = True
        self._set_joint_world_axes(matches[0], change.desired_world_axes)

    def set_body_joint_world_position(
        self,
        joint: str,
        position: tuple[float, float, float],
    ) -> None:
        self._require_transaction()
        matches = self._cmds.ls(joint, long=True, type="joint") or []
        if len(matches) != 1 or matches[0] != joint:
            raise FitSkeletonValidationError(
                f"Body joint 在位置恢复前失效：{joint}"
            )
        for axis in ("x", "y", "z"):
            attribute = f"{matches[0]}.t{axis}"
            if not self._cmds.getAttr(attribute, settable=True):
                raise FitSkeletonValidationError(
                    f"Body joint 位置轴在执行前变为不可写：{attribute}"
                )
        self._transaction_changed = True
        self._cmds.xform(
            matches[0],
            worldSpace=True,
            translation=position,
        )

    def _capture_body_provenance(
        self,
        root: str,
    ) -> BodySkeletonProvenanceState | None:
        exists = {
            field: bool(
                self._cmds.attributeQuery(attribute, node=root, exists=True)
            )
            for field, attribute in _BODY_PROVENANCE_ATTRIBUTES.items()
        }
        if not any(exists.values()):
            return None

        def value(field: str):
            if not exists[field]:
                return None
            return self._cmds.getAttr(
                f"{root}.{_BODY_PROVENANCE_ATTRIBUTES[field]}"
            )

        return BodySkeletonProvenanceState(
            owner=value("owner"),
            artifact_kind=value("artifact_kind"),
            schema_version=value("schema_version"),
            source_container=value("source_container"),
            body_joint_count=value("body_joint_count"),
        )

    def _resolve_connected_node(self, plug: str) -> str:
        node = plug.split(".", 1)[0]
        matches = self._cmds.ls(node, long=True) or [node]
        return matches[0]

    def _dependency_kind(self, node: str) -> BodyExternalDependencyKind:
        node_type = self._cmds.nodeType(node)
        inherited = set(self._cmds.nodeType(node, inherited=True) or [])
        if node_type == "skinCluster":
            return BodyExternalDependencyKind.SKIN_CLUSTER
        if "constraint" in inherited:
            return BodyExternalDependencyKind.CONSTRAINT
        if node_type.startswith("animCurve"):
            return BodyExternalDependencyKind.ANIMATION
        return BodyExternalDependencyKind.CONNECTION
