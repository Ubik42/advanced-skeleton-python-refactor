"""Attach OPM Tweaker controls without replacing existing joint drivers."""
from __future__ import annotations

from adv_py.core.fit_tweaker import (
    FitTweakerPlan, FitTweakerSourceState, FitTweakerSpec,
)

from .maya_adv_icons import create_adv_icon


def _matrix(values) -> tuple[float, ...]:
    if len(values) == 1 and isinstance(values[0], (tuple, list)):
        values = values[0]
    return tuple(float(value) for value in values)


def _determinant3(matrix: tuple[float, ...]) -> float:
    a, b, c = matrix[0], matrix[1], matrix[2]
    d, e, f = matrix[4], matrix[5], matrix[6]
    g, h, i = matrix[8], matrix[9], matrix[10]
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)


class MayaFitTweakerMixin:
    def preflight_fit_tweakers(self, plan: FitTweakerPlan) -> tuple[FitTweakerSourceState, ...]:
        c = self._cmds
        if not plan.controls:
            return ()
        if (c.ls(plan.system_path.rsplit("|", 1)[0], long=True,
                 type="transform") or []) != [
                     plan.system_path.rsplit("|", 1)[0]]:
            raise ValueError("Tweaker MotionSystem 不存在")
        if (c.ls(plan.global_control_path, long=True,
                 type="transform") or []) != [plan.global_control_path]:
            raise ValueError("Tweaker 总控不存在")
        if c.attributeQuery("tweakerVis", node=plan.global_control_path,
                            exists=True):
            raise ValueError("总控已有 tweakerVis 属性")
        names = (plan.system_path.rsplit("|", 1)[-1],)
        names += tuple(name for spec in plan.controls
                       for name in spec.node_names)
        if len(set(names)) != len(names) or any(
                self.find_name_collisions(name) for name in names):
            raise ValueError("Tweaker 节点名称冲突")
        states = []
        for spec in plan.controls:
            nodes = c.ls(spec.target_path, long=True, type="joint") or []
            if nodes != [spec.target_path]:
                raise ValueError("Tweaker 目标关节缺失或不唯一："
                                 + spec.target_path)
            parent = c.listRelatives(spec.target_path, parent=True,
                                     fullPath=True) or []
            if len(parent) > 1:
                raise ValueError("Tweaker 目标关节父级不唯一："
                                 + spec.target_path)
            if c.getAttr(spec.target_path + ".offsetParentMatrix",
                         lock=True):
                raise ValueError("Tweaker 目标矩阵已锁定："
                                 + spec.target_path)
            if not c.getAttr(spec.target_path + ".offsetParentMatrix",
                             settable=True) and not c.connectionInfo(
                                 spec.target_path + ".offsetParentMatrix",
                                 isDestination=True):
                raise ValueError("Tweaker 目标矩阵不可写："
                                 + spec.target_path)
            opm = _matrix(c.getAttr(spec.target_path
                                    + ".offsetParentMatrix"))
            local = _matrix(c.getAttr(spec.target_path + ".matrix"))
            world = _matrix(c.xform(spec.target_path, query=True,
                                    worldSpace=True, matrix=True))
            if (len(opm) != 16 or len(local) != 16
                    or len(world) != 16
                    or abs(_determinant3(local)) < 1e-10):
                raise ValueError("Tweaker 目标矩阵无效："
                                 + spec.target_path)
            states.append(FitTweakerSourceState(
                parent[0] if parent else None, c.connectionInfo(
                    spec.target_path + ".offsetParentMatrix",
                    sourceFromDestination=True) or None,
                opm, world))
        return tuple(states)

    def create_fit_tweaker_system(self, plan: FitTweakerPlan) -> None:
        self._require_transaction()
        if not plan.controls:
            return
        c = self._cmds
        system = c.createNode("transform",
                              name=plan.system_path.rsplit("|", 1)[-1],
                              parent=plan.system_path.rsplit("|", 1)[0],
                              skipSelect=True)
        self._transaction_changed = True
        if (c.ls(system, long=True) or []) != [plan.system_path]:
            raise RuntimeError("TweakerSystem 路径漂移")
        c.addAttr(plan.global_control_path, longName="tweakerVis",
                  attributeType="bool", defaultValue=True,
                  keyable=False)
        c.setAttr(plan.global_control_path + ".tweakerVis",
                  channelBox=True)
        c.connectAttr(plan.global_control_path + ".tweakerVis",
                      system + ".visibility")

    def capture_fit_tweaker_system(self, plan: FitTweakerPlan) -> bool:
        c = self._cmds
        if not plan.controls:
            return True
        return (c.ls(plan.system_path, long=True,
                     type="transform") == [plan.system_path]
                and c.attributeQuery("tweakerVis",
                                     node=plan.global_control_path,
                                     exists=True)
                and c.connectionInfo(
                    plan.system_path + ".visibility",
                    sourceFromDestination=True)
                == plan.global_control_path + ".tweakerVis")

    def create_fit_tweaker(
        self, plan: FitTweakerPlan, spec: FitTweakerSpec,
        state: FitTweakerSourceState,
    ) -> None:
        self._require_transaction()
        c = self._cmds
        offset = c.createNode("transform",
                              name=spec.offset_path.rsplit("|", 1)[-1],
                              parent=plan.system_path, skipSelect=True)
        selection = c.ls(selection=True, long=True) or []
        try:
            control = create_adv_icon(
                c, name=spec.control_path.rsplit("|", 1)[-1],
                parent=offset, template="Tweaker_icon", radius=0.5,
                fallback_normal=(1.0, 0.0, 0.0),
                fallback_sections=12)
        finally:
            if selection:
                c.select(selection, replace=True)
            else:
                c.select(clear=True)
        x_path = c.createNode("transform",
                              name=spec.x_path.rsplit("|", 1)[-1],
                              parent=control, skipSelect=True)
        self._transaction_changed = True
        for node, expected in ((offset, spec.offset_path),
                               (control, spec.control_path),
                               (x_path, spec.x_path)):
            if (c.ls(node, long=True) or []) != [expected]:
                raise RuntimeError("Tweaker 控制层路径漂移：" + expected)
        base = c.createNode("multMatrix", name=spec.base_world_name)
        offset_mm = c.createNode("multMatrix",
                                 name=spec.offset_matrix_name)
        inverse = c.createNode("inverseMatrix",
                               name=spec.local_inverse_name)
        final = c.createNode("multMatrix",
                             name=spec.final_matrix_name)
        c.connectAttr(spec.target_path + ".matrix",
                      base + ".matrixIn[0]")
        if state.offset_matrix_source:
            c.connectAttr(state.offset_matrix_source,
                          base + ".matrixIn[1]")
        else:
            c.setAttr(base + ".matrixIn[1]",
                      *state.static_offset_matrix, type="matrix")
        if state.parent_path is not None:
            c.connectAttr(state.parent_path + ".worldMatrix[0]",
                          base + ".matrixIn[2]")
        c.connectAttr(base + ".matrixSum",
                      offset_mm + ".matrixIn[0]")
        c.connectAttr(plan.system_path + ".worldInverseMatrix[0]",
                      offset_mm + ".matrixIn[1]")
        c.connectAttr(offset_mm + ".matrixSum",
                      offset + ".offsetParentMatrix")
        c.connectAttr(spec.target_path + ".matrix",
                      inverse + ".inputMatrix")
        c.connectAttr(inverse + ".outputMatrix",
                      final + ".matrixIn[0]")
        c.connectAttr(spec.x_path + ".worldMatrix[0]",
                      final + ".matrixIn[1]")
        if state.parent_path is not None:
            c.connectAttr(state.parent_path + ".worldInverseMatrix[0]",
                          final + ".matrixIn[2]")
        if state.offset_matrix_source:
            c.disconnectAttr(state.offset_matrix_source,
                             spec.target_path + ".offsetParentMatrix")
        c.connectAttr(final + ".matrixSum",
                      spec.target_path + ".offsetParentMatrix")

    def capture_fit_tweaker(
        self, plan: FitTweakerPlan, spec: FitTweakerSpec,
        state: FitTweakerSourceState,
    ) -> bool:
        c = self._cmds
        links = (
            (spec.target_path + ".matrix",
             spec.base_world_name + ".matrixIn[0]"),
            (spec.base_world_name + ".matrixSum",
             spec.offset_matrix_name + ".matrixIn[0]"),
            (plan.system_path + ".worldInverseMatrix[0]",
             spec.offset_matrix_name + ".matrixIn[1]"),
            (spec.offset_matrix_name + ".matrixSum",
             spec.offset_path + ".offsetParentMatrix"),
            (spec.target_path + ".matrix",
             spec.local_inverse_name + ".inputMatrix"),
            (spec.local_inverse_name + ".outputMatrix",
             spec.final_matrix_name + ".matrixIn[0]"),
            (spec.x_path + ".worldMatrix[0]",
             spec.final_matrix_name + ".matrixIn[1]"),
            (spec.final_matrix_name + ".matrixSum",
             spec.target_path + ".offsetParentMatrix"),
        )
        if state.parent_path is not None:
            links += (
                (state.parent_path + ".worldMatrix[0]",
                 spec.base_world_name + ".matrixIn[2]"),
                (state.parent_path + ".worldInverseMatrix[0]",
                 spec.final_matrix_name + ".matrixIn[2]"),
            )
        if state.offset_matrix_source:
            links += ((state.offset_matrix_source,
                       spec.base_world_name + ".matrixIn[1]"),)
        elif any(abs(a - b) > 1e-8 for a, b in zip(
                _matrix(c.getAttr(spec.base_world_name
                                  + ".matrixIn[1]")),
                state.static_offset_matrix)):
            return False
        if any(c.connectionInfo(destination,
                                sourceFromDestination=True) != source
               for source, destination in links):
            return False
        current = _matrix(c.xform(spec.target_path, query=True,
                                  worldSpace=True, matrix=True))
        return (len(current) == 16 and all(
            abs(a - b) <= 1e-4
            for a, b in zip(current, state.world_matrix)))
