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
            raise FitSkeletonValidationError(f"Arm FK 控制根名称冲突：{name}")
        self._transaction_changed = True
        created = self._cmds.createNode(
            "transform",
            name=name,
            skipSelect=True,
        )
        return (self._cmds.ls(created, long=True) or [created])[0]

    def create_body_arm_ik_root(self, name: str) -> str:
        return self.create_body_control_root(name)

    def create_body_arm_blend(self, plan: BodyArmBlendPlan) -> None:
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            self._create_body_arm_blend_nodes(plan)
        finally:
            if selection:
                self._cmds.select(selection, replace=True)
            else:
                self._cmds.select(clear=True)

    def _create_body_arm_blend_nodes(self, plan: BodyArmBlendPlan) -> None:
        self._require_transaction()
        names = [plan.settings_name]
        for side in plan.sides:
            names.append(side.reverse_name)
            names.extend(joint.constraint_name for joint in side.joints)
        if any(self.find_name_collisions(name) for name in names):
            raise FitSkeletonValidationError("Arm IK/FK 输出名称冲突")
        self._transaction_changed = True
        settings = self._cmds.createNode("transform", name=plan.settings_name, skipSelect=True)
        settings = (self._cmds.ls(settings, long=True) or [settings])[0]
        if settings != plan.settings_path:
            raise RuntimeError("Arm IK/FK 设置节点路径漂移")
        for side in plan.sides:
            self._cmds.addAttr(settings, longName=side.attribute, attributeType="double", minValue=0.0, maxValue=1.0, defaultValue=0.0, keyable=True)
            plug = f"{settings}.{side.attribute}"
            reverse = self._cmds.createNode("reverse", name=side.reverse_name)
            self._cmds.connectAttr(plug, f"{reverse}.inputX")
            for joint in side.joints:
                if any(not self._cmds.objExists(path) for path in (joint.body_joint, joint.fk_driver, joint.ik_driver)):
                    raise FitSkeletonValidationError("Arm IK/FK 驱动或 Body joint 失效")
                constraint = self._cmds.orientConstraint(joint.fk_driver, joint.ik_driver, joint.body_joint, maintainOffset=False, name=joint.constraint_name)[0]
                aliases = self._cmds.orientConstraint(constraint, query=True, weightAliasList=True) or []
                if len(aliases) != 2:
                    raise RuntimeError("Arm IK/FK 双源权重别名无效")
                self._cmds.connectAttr(f"{reverse}.outputX", f"{constraint}.{aliases[0]}")
                self._cmds.connectAttr(plug, f"{constraint}.{aliases[1]}")

    def capture_body_arm_blend(self, plan: BodyArmBlendPlan) -> BodyArmBlendSnapshot:
        def normalized_plug(value: str | None) -> str | None:
            if value is None or "." not in value:
                return value
            node, attribute = value.split(".", 1)
            paths = self._cmds.ls(node, long=True) or [node]
            return f"{paths[0]}.{attribute}"

        settings_nodes = self._cmds.ls(plan.settings_path, long=True, type="transform") or []
        if len(settings_nodes) != 1:
            raise FitSkeletonValidationError("Arm IK/FK 设置节点无效")
        settings = settings_nodes[0]
        side_states = []
        for side in plan.sides:
            plug = f"{settings}.{side.attribute}"
            reverse_nodes = self._cmds.ls(side.reverse_name, type="reverse") or []
            if len(reverse_nodes) != 1 or not self._cmds.objExists(plug):
                raise FitSkeletonValidationError("Arm IK/FK 属性或 reverse 无效")
            reverse = reverse_nodes[0]
            reverse_sources = self._cmds.listConnections(f"{reverse}.inputX", source=True, destination=False, plugs=True) or []
            joint_states = []
            for spec in side.joints:
                constraints = self._cmds.ls(spec.constraint_name, type="orientConstraint") or []
                if len(constraints) != 1:
                    raise FitSkeletonValidationError("Arm IK/FK 约束无效")
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
                joint_states.append(BodyArmBlendJointState(constraint, driven, target_paths, weight_sources[0] if len(weight_sources) > 0 else None, weight_sources[1] if len(weight_sources) > 1 else None))
            side_states.append(BodyArmBlendSideState(side.side, plug, float(self._cmds.getAttr(plug)), reverse, normalized_plug(reverse_sources[0]) if len(reverse_sources) == 1 else None, tuple(joint_states)))
        return BodyArmBlendSnapshot(settings, tuple(side_states))

    def create_body_arm_ik(self, spec: BodyArmIkSpec) -> None:
        self._require_transaction()
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            for name in (spec.wrist_offset_name, spec.wrist_control_name, spec.pole_offset_name, spec.pole_control_name, spec.handle_name, spec.pole_constraint_name):
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
            if wrist is None or pole is None or len(handles) != 1 or len(constraints) != 1:
                raise FitSkeletonValidationError("Arm IK 节点集合无效")
            handle = handles[0]
            wp = self._cmds.listRelatives(wrist, parent=True, fullPath=True) or []
            pp = self._cmds.listRelatives(pole, parent=True, fullPath=True) or []
            hp = self._cmds.listRelatives(handle, parent=True, fullPath=True) or []
            joint_list = tuple((self._cmds.ls(value, long=True) or [value])[0] for value in (self._cmds.ikHandle(handle, query=True, jointList=True) or []))
            targets = self._cmds.poleVectorConstraint(constraints[0], query=True, targetList=True) or []
            pole_source = (self._cmds.ls(targets[0], long=True) or [targets[0]])[0] if len(targets) == 1 else None
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
            ))
        return BodyArmIkSnapshot(roots[0], tuple(states))

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

    def create_body_arm_fk_control(self, spec: BodyArmFkControlSpec) -> None:
        self._require_transaction()
        selection = self._cmds.ls(selection=True, long=True) or []
        for name in (spec.offset_name, spec.control_name, spec.constraint_name):
            if self.find_name_collisions(name):
                raise FitSkeletonValidationError(f"Arm FK 控制名称冲突：{name}")
        parent = self._cmds.ls(spec.parent_path, long=True, type="transform") or []
        driven = self._cmds.ls(spec.driven_joint, long=True, type="joint") or []
        if len(parent) != 1 or len(driven) != 1:
            raise FitSkeletonValidationError(
                f"Arm FK 控制父级或驱动关节失效：{spec.control_name}"
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
                raise RuntimeError(f"Arm FK 控制路径漂移：{spec.control_name}")
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
        roots = self._cmds.ls(plan.root_path, long=True, type="transform") or []
        if len(roots) != 1:
            raise FitSkeletonValidationError("Arm FK 控制根节点无效")
        states: list[BodyArmFkControlState] = []
        for spec in plan.controls:
            offsets = self._cmds.ls(spec.offset_path, long=True, type="transform") or []
            controls = self._cmds.ls(spec.control_path, long=True, type="transform") or []
            constraints = self._cmds.ls(spec.constraint_name, type="orientConstraint") or []
            if len(offsets) != 1 or len(controls) != 1 or len(constraints) != 1:
                raise FitSkeletonValidationError(
                    f"Arm FK 控制或约束无效：{spec.control_name}"
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
