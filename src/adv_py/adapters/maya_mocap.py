from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from adv_py.core.mocap_source import (
    MOCAP_TRANSFORM_ATTRIBUTES,
    MocapChannelSnapshot,
    MocapDriverKind,
    MocapJointSnapshot,
    MocapSourceSnapshot,
    MocapSourceValidationError,
)
from adv_py.core.body_skeleton import BodySkeletonSnapshot
from adv_py.core.mocap_connection import (
    MocapBodyConnectionPlan,
    MocapBodyConnectionSnapshot,
    MocapConstraintKind,
    MocapConstraintState,
    MocapTargetInputState,
    MocapTargetPose,
)
from adv_py.core.mocap_mapping import MocapMappingValidationError


class MayaMocapSourceReader:
    """Read an explicit Maya joint hierarchy without modifying scene state."""

    def __init__(self) -> None:
        from maya import cmds  # type: ignore[import-not-found]

        self._cmds = cmds

    def capture_mocap_source(self, root_name: str) -> MocapSourceSnapshot:
        roots = self._cmds.ls(root_name, long=True, type="joint") or []
        if len(roots) != 1:
            raise MocapSourceValidationError(
                f"MoCap 根关节必须明确且唯一：{root_name}"
            )
        root = roots[0]
        paths = self._cmds.listRelatives(
            root,
            allDescendents=True,
            type="joint",
            fullPath=True,
        ) or []
        paths.append(root)
        ordered_paths = sorted(set(paths), key=lambda path: (path.count("|"), path))
        joints: list[MocapJointSnapshot] = []
        channels: list[MocapChannelSnapshot] = []

        for path in ordered_paths:
            leaf = path.rsplit("|", 1)[-1]
            namespace, separator, name = leaf.rpartition(":")
            if not separator:
                namespace, name = "", leaf
            parents = self._cmds.listRelatives(
                path, parent=True, fullPath=True
            ) or []
            joint_parent = None
            if parents and self._cmds.nodeType(parents[0]) == "joint":
                joint_parent = parents[0]
            joints.append(MocapJointSnapshot(
                path=path,
                name=name,
                namespace=namespace,
                joint_parent=joint_parent,
            ))

            for attribute in MOCAP_TRANSFORM_ATTRIBUTES:
                source_plugs = self._cmds.listConnections(
                    f"{path}.{attribute}",
                    source=True,
                    destination=False,
                    plugs=True,
                ) or []
                if not source_plugs:
                    continue
                if len(source_plugs) != 1:
                    raise MocapSourceValidationError(
                        f"MoCap 通道输入不唯一：{path}.{attribute}"
                    )
                source_plug = str(source_plugs[0])
                source_node = source_plug.rsplit(".", 1)[0]
                node_type = str(self._cmds.nodeType(source_node))
                is_animation_curve = node_type.startswith("animCurve")
                key_times = ()
                if is_animation_curve:
                    values = self._cmds.keyframe(
                        source_node, query=True, timeChange=True
                    ) or []
                    key_times = tuple(sorted({float(value) for value in values}))
                channels.append(MocapChannelSnapshot(
                    joint_path=path,
                    attribute=attribute,
                    driver_kind=(
                        MocapDriverKind.ANIMATION_CURVE
                        if is_animation_curve
                        else MocapDriverKind.OTHER
                    ),
                    driver_path=source_plug,
                    key_times=key_times,
                ))

        return MocapSourceSnapshot(
            root=root,
            joints=tuple(joints),
            channels=tuple(channels),
        )


class MayaMocapMappingReader:
    """Compose the dedicated MoCap reader with the canonical Body reader."""

    def __init__(self) -> None:
        from .maya_body import MayaBodyBuildHost

        self._source_reader = MayaMocapSourceReader()
        self._body_reader = MayaBodyBuildHost()

    def capture_mocap_source(self, root_name: str) -> MocapSourceSnapshot:
        return self._source_reader.capture_mocap_source(root_name)

    def capture_body_skeleton(self, root_name: str) -> BodySkeletonSnapshot:
        return self._body_reader.capture_body_skeleton(root_name)


class MayaMocapConnectionHost(MayaMocapMappingReader):
    """Create and remove only the temporary constraints described by a plan."""

    def __init__(self) -> None:
        super().__init__()
        self._cmds = self._source_reader._cmds
        self._transaction_active = False
        self._transaction_changed = False

    @contextmanager
    def transaction(self, label: str) -> Iterator[None]:
        if self._transaction_active:
            raise RuntimeError("Maya MoCap host 不支持嵌套事务")
        if not self._cmds.undoInfo(query=True, state=True):
            raise MocapMappingValidationError("MoCap 临时驱动需要启用 Maya Undo")
        self._transaction_active = True
        self._transaction_changed = False
        self._cmds.undoInfo(openChunk=True, chunkName=label)
        try:
            yield
        except Exception:
            self._cmds.undoInfo(closeChunk=True)
            if self._transaction_changed:
                self._cmds.undo()
            raise
        else:
            self._cmds.undoInfo(closeChunk=True)
        finally:
            self._transaction_active = False
            self._transaction_changed = False

    def find_mocap_name_collisions(
        self, plan: MocapBodyConnectionPlan
    ) -> tuple[str, ...]:
        return tuple(
            spec.name for spec in plan.constraints
            if self._cmds.ls(spec.name) or []
        )

    def capture_mocap_target_inputs(
        self, plan: MocapBodyConnectionPlan
    ) -> tuple[MocapTargetInputState, ...]:
        states = []
        for spec in plan.constraints:
            for attribute in spec.target_attributes:
                sources = self._cmds.listConnections(
                    f"{spec.target_path}.{attribute}",
                    source=True,
                    destination=False,
                    plugs=True,
                ) or []
                if len(sources) > 1:
                    raise MocapMappingValidationError(
                        f"Body 目标通道输入不唯一：{spec.target_path}.{attribute}"
                    )
                source_node = None
                if sources:
                    source_node = self._resolve_node(str(sources[0]).rsplit(".", 1)[0])
                    source_leaf = source_node.rsplit("|", 1)[-1]
                    if any(source_leaf == item.name for item in plan.constraints):
                        source_node = source_leaf
                states.append(MocapTargetInputState(
                    spec.target_path, attribute, source_node
                ))
        return tuple(states)

    def capture_mocap_target_poses(
        self, plan: MocapBodyConnectionPlan
    ) -> tuple[MocapTargetPose, ...]:
        return tuple(
            MocapTargetPose(
                spec.target_path,
                tuple(float(value) for value in self._cmds.xform(
                    spec.target_path, query=True, worldSpace=True, matrix=True
                )),
            )
            for spec in plan.constraints
        )

    def create_mocap_constraints(self, plan: MocapBodyConnectionPlan) -> None:
        self._require_transaction()
        self._transaction_changed = True
        for spec in plan.constraints:
            command = (
                self._cmds.parentConstraint
                if spec.kind is MocapConstraintKind.PARENT
                else self._cmds.orientConstraint
            )
            created = command(
                spec.source_path,
                spec.target_path,
                maintainOffset=True,
                name=spec.name,
            ) or []
            created_name = (
                "" if len(created) != 1
                else self._resolve_node(created[0]).rsplit("|", 1)[-1]
            )
            if created_name != spec.name:
                raise MocapMappingValidationError(
                    f"MoCap 临时约束名称漂移：{spec.name}"
                )

    def capture_mocap_connection(
        self, plan: MocapBodyConnectionPlan
    ) -> MocapBodyConnectionSnapshot:
        states = []
        for spec in plan.constraints:
            nodes = self._cmds.ls(spec.name, long=True) or []
            if not nodes:
                continue
            if len(nodes) != 1 or self._cmds.nodeType(nodes[0]) != spec.kind.value:
                raise MocapMappingValidationError(
                    f"MoCap 临时约束名称被非预期节点占用：{spec.name}"
                )
            constraint = nodes[0]
            command = (
                self._cmds.parentConstraint
                if spec.kind is MocapConstraintKind.PARENT
                else self._cmds.orientConstraint
            )
            targets = command(constraint, query=True, targetList=True) or []
            output_attribute = (
                "constraintTranslateX"
                if spec.kind is MocapConstraintKind.PARENT
                else "constraintRotateX"
            )
            outputs = self._cmds.listConnections(
                f"{constraint}.{output_attribute}",
                source=False,
                destination=True,
                plugs=True,
            ) or []
            if len(targets) != 1 or len(outputs) != 1:
                raise MocapMappingValidationError(
                    f"MoCap 临时约束连接数量无效：{spec.name}"
                )
            states.append(MocapConstraintState(
                spec.name,
                self._resolve_node(targets[0]),
                self._resolve_node(str(outputs[0]).rsplit(".", 1)[0]),
                spec.kind,
            ))
        return MocapBodyConnectionSnapshot(
            tuple(states), self.capture_mocap_target_inputs(plan)
        )

    def delete_mocap_constraints(self, plan: MocapBodyConnectionPlan) -> None:
        self._require_transaction()
        nodes = []
        for spec in plan.constraints:
            values = self._cmds.ls(spec.name, long=True) or []
            if len(values) != 1 or self._cmds.nodeType(values[0]) != spec.kind.value:
                raise MocapMappingValidationError(
                    f"拒绝删除非预期 MoCap 节点：{spec.name}"
                )
            nodes.append(values[0])
        self._transaction_changed = True
        self._cmds.delete(nodes)

    def _resolve_node(self, name: str) -> str:
        values = self._cmds.ls(name, long=True) or []
        if len(values) != 1:
            raise MocapMappingValidationError(f"Maya 节点路径不唯一：{name}")
        return str(values[0])

    def _require_transaction(self) -> None:
        if not self._transaction_active:
            raise RuntimeError("MoCap 场景修改必须在事务内执行")
