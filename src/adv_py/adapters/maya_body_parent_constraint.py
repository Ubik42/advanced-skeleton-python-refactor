"""Maya scene boundary for the ADV Body parent-constraint helper."""
from __future__ import annotations

from adv_py.core.body_parent_constraint import (
    BodyParentConstraintInput, BodyParentConstraintPlan,
    BodyParentConstraintState,
)

def _matrix(values) -> tuple[float, ...]:
    if len(values) == 1 and isinstance(values[0], (tuple, list)):
        values = values[0]
    return tuple(float(value) for value in values)


class MayaBodyParentConstraintMixin:
    """Constraint methods shared with the ordinary Body build host."""

    def __init__(self, *, namespace: str | None = None,
                 use_offset_parent_matrix: bool = False) -> None:
        if type(use_offset_parent_matrix) is not bool:
            raise ValueError("Body Parent Constraint 矩阵开关无效")
        super().__init__(namespace=namespace)
        self._use_offset_parent_matrix = use_offset_parent_matrix

    def capture_parent_constraint_input(
        self, driver: str, driven: str, maintain_offset: bool,
    ) -> BodyParentConstraintInput:
        c = self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds
        drivers = c.ls(driver, long=True) or []
        drivens = c.ls(driven, long=True) or []
        if len(drivers) != 1 or len(drivens) != 1:
            raise ValueError("Body Parent Constraint 来源或目标不存在／不唯一")
        if any(c.nodeType(node) not in ("transform", "joint")
               for node in (drivers[0], drivens[0])):
            raise ValueError("Body Parent Constraint 只接受 Transform 或 Joint")
        if drivers[0] != driver or drivens[0] != driven or driver == driven:
            raise ValueError("Body Parent Constraint 需要不同的完整 DAG 路径")
        if self.namespace is not None and not all(
                self._cmds.identity.owns(node) for node in (driver, driven)):
            raise ValueError("约束来源和目标必须属于当前角色")
        if driver.startswith(driven + "|"):
            raise ValueError("不能用目标的后代驱动目标")
        parent = (c.listRelatives(driven, parent=True, fullPath=True) or [None])[0]
        offset = None
        if maintain_offset:
            from maya.api import OpenMaya as om  # type: ignore[import-not-found]
            driven_world = om.MMatrix(_matrix(c.getAttr(driven + ".worldMatrix[0]")))
            driver_world = om.MMatrix(_matrix(c.getAttr(driver + ".worldMatrix[0]")))
            offset = tuple(driven_world * driver_world.inverse())
        leaf = driven.rsplit("|", 1)[-1]
        stem, _, side = leaf.rpartition("_")
        mm = stem + "MM_" + side
        pm = stem + "PM_" + side
        return BodyParentConstraintInput(
            driver=driver, driven=driven, driven_parent=parent,
            driven_is_joint=c.nodeType(driven) == "joint",
            rotate_order=int(c.getAttr(driven + ".rotateOrder")),
            use_offset_parent_matrix=self._use_offset_parent_matrix,
            maintain_offset=maintain_offset, offset_matrix=offset,
            existing_mult_matrix=bool(c.objExists(mm)
                                      and c.nodeType(mm) == "multMatrix"),
            existing_pick_matrix=bool(c.objExists(pm)
                                       and c.nodeType(pm) == "pickMatrix"),
        )

    def preflight_parent_constraint(
        self, plan: BodyParentConstraintPlan,
    ) -> None:
        c = self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds
        for name, kind in plan.create_nodes:
            if c.objExists(name):
                raise ValueError(f"{kind} 节点名称已被占用：{name}")
        if plan.mode == "constraint":
            for kind in ("parentConstraint", "scaleConstraint"):
                if c.listConnections(plan.input.driven, source=True,
                                     destination=False, type=kind):
                    raise ValueError("目标已有约束：" + kind)
            return
        if plan.mult_matrix and c.objExists(plan.mult_matrix):
            if c.nodeType(plan.mult_matrix) != "multMatrix":
                raise ValueError("已有矩阵节点类型不符")
            for index, _ in plan.matrix_inputs:
                plug = f"{plan.mult_matrix}.matrixIn[{index}]"
                if c.connectionInfo(plug, isDestination=True):
                    raise ValueError("已有矩阵输入被占用：" + plug)
        new_nodes = {name for name, _ in plan.create_nodes}
        for _, target in plan.output_connections:
            if target.split(".", 1)[0] in new_nodes:
                continue
            if c.connectionInfo(target, isDestination=True):
                raise ValueError("约束目标输入已被占用：" + target)
        if plan.reset_local_transform:
            attrs = ("translate", "rotate", "scale") + (
                ("jointOrient",) if plan.reset_joint_orient else ())
            if any(c.getAttr(plan.input.driven + "." + attr, lock=True)
                   for attr in attrs):
                raise ValueError("目标变换通道已锁定")

    def create_parent_constraint(self, plan: BodyParentConstraintPlan) -> None:
        self._require_transaction()
        c = self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds
        source = plan.input
        self._transaction_changed = True
        if plan.mode == "constraint":
            c.parentConstraint(source.driver, source.driven,
                               maintainOffset=source.maintain_offset)
            if not source.skip_scale:
                c.scaleConstraint(source.driver, source.driven,
                                  maintainOffset=source.maintain_offset)
            return
        for name, kind in plan.create_nodes:
            c.createNode(kind, name=name)
        for index, value in plan.matrix_inputs:
            target = f"{plan.mult_matrix}.matrixIn[{index}]"
            if isinstance(value, str):
                c.connectAttr(value, target, force=True)
            else:
                c.setAttr(target, *value, type="matrix")
        if plan.reset_local_transform:
            for attr, value in (("translate", (0, 0, 0)),
                                ("rotate", (0, 0, 0)),
                                ("scale", (1, 1, 1))):
                c.setAttr(source.driven + "." + attr, *value)
        if plan.reset_joint_orient:
            c.setAttr(source.driven + ".jointOrient", 0, 0, 0)
        if plan.pick_matrix and (plan.mode in ("pick_matrix", "pick_decompose")):
            c.setAttr(plan.pick_matrix + ".useScale", not source.skip_scale)
        if plan.decompose_matrix:
            c.setAttr(plan.decompose_matrix + ".inputRotateOrder",
                      source.rotate_order)
        for upstream, target in plan.output_connections:
            c.connectAttr(upstream, target, force=True)

    def capture_parent_constraint_state(
        self, plan: BodyParentConstraintPlan,
    ) -> BodyParentConstraintState:
        c = self._cmds.raw if hasattr(self._cmds, "raw") else self._cmds
        source = plan.input
        node_names = (plan.mult_matrix, plan.pick_matrix, plan.decompose_matrix)
        nodes = tuple((name, c.nodeType(name)) for name in node_names
                      if name and c.objExists(name))
        matrix_inputs = []
        for index, value in plan.matrix_inputs:
            target = f"{plan.mult_matrix}.matrixIn[{index}]"
            incoming = c.connectionInfo(target, sourceFromDestination=True)
            matrix_inputs.append((index, incoming if isinstance(value, str)
                                  else _matrix(c.getAttr(target))))
        connections = []
        if plan.mode == "constraint":
            actual = set(c.listConnections(source.driven, source=True,
                                           destination=False,
                                           type="parentConstraint") or [])
            if actual:
                connections.append((source.driver,
                                    source.driven + ".parentConstraint"))
            actual = set(c.listConnections(source.driven, source=True,
                                           destination=False,
                                           type="scaleConstraint") or [])
            if actual and not source.skip_scale:
                connections.append((source.driver,
                                    source.driven + ".scaleConstraint"))
        else:
            connections = [(c.connectionInfo(target,
                           sourceFromDestination=True), target)
                           for _, target in plan.output_connections]
        def vector(attribute: str) -> tuple[float, float, float]:
            return tuple(float(v) for v in c.getAttr(
                source.driven + "." + attribute)[0])
        return BodyParentConstraintState(
            node_types=nodes, matrix_inputs=tuple(matrix_inputs),
            output_connections=tuple(connections),
            local_translate=vector("translate"),
            local_rotate=vector("rotate"),
            local_scale=vector("scale"),
            joint_orient=vector("jointOrient") if source.driven_is_joint else None,
            pick_use_scale=(bool(c.getAttr(plan.pick_matrix + ".useScale"))
                            if plan.pick_matrix and plan.mode in (
                                "pick_matrix", "pick_decompose") else None),
            decompose_rotate_order=(int(c.getAttr(
                plan.decompose_matrix + ".inputRotateOrder"))
                if plan.decompose_matrix else None),
        )
