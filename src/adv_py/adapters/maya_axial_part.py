"""Maya construction of exact-name axial deformation influences."""
from __future__ import annotations

from math import isfinite
from typing import Mapping

from adv_py.core.axial_part_deform import AxialPartSpec
from .maya_body import MayaBodyBuildHost


class MayaAxialPartHost(MayaBodyBuildHost):
    def preflight_axial_part_guide(self, spec: AxialPartSpec,
                                  guide: Mapping[str, object]) -> None:
        nodes = guide.get("nodes")
        drivers = guide.get("drivers")
        if not isinstance(nodes, dict) or not isinstance(drivers, dict):
            raise ValueError("轴向分段导向缺少原版节点图")
        stem = spec.name.split("Part", 1)[0]
        for name in (spec.name, "FKX" + spec.name,
                     "FKPS1" + spec.name, "FKPS2" + spec.name,
                     "FK" + stem + "_M",
                     "FKX" + stem + "_M",
                     "InbetweenBase" + stem + "_M",
                     "InbetweenTarget" + stem + "_M"):
            row = nodes.get(name)
            if (not isinstance(row, dict) or not isinstance(
                    row.get("world_matrix"), list)
                    or len(row["world_matrix"]) != 16):
                raise ValueError("轴向分段导向缺少矩阵：" + name)
            if not all(isfinite(float(value)) for value in row["world_matrix"]):
                raise ValueError("轴向分段导向矩阵含非有限数值：" + name)
        point_parent = nodes["FKPS2" + spec.name].get("parent", "")
        first_point_parent = nodes["FKPS1" + spec.name].get("parent", "")
        expected_anchor = ("FKX" + stem + "_M" if "Part1" in spec.name
                           else "FKX" + stem + "Part1_M")
        if (not point_parent.endswith("|FKPS1" + spec.name)
                or not first_point_parent.endswith("|" + expected_anchor)):
            raise ValueError("轴向分段位置父链与原版不符：" + spec.name)
        blend = drivers.get(spec.name.replace("_M", "InbetweenBM_M"))
        bias_name = (f"FK{stem}{'Mid' if 'Part1' in spec.name else 'End'}BiasRV_M")
        bias = drivers.get(bias_name)
        if (not isinstance(blend, dict) or blend.get("type") != "blendMatrix"
                or not any("rotateWeight" in destination and
                           source == bias_name + ".outValue"
                           for destination, source in blend.get("connections", []))):
            raise ValueError("轴向分段导向缺少原版旋转权重：" + spec.name)
        if (not isinstance(bias, dict) or bias.get("type") != "remapValue"
                or not isinstance(bias.get("out_value"), (int, float))
                or not isfinite(bias["out_value"])
                or not 0.0 <= bias["out_value"] <= 1.0):
            raise ValueError("轴向分段原版旋转权重无效：" + bias_name)
        c = self._cmds
        control = "AdvPy_Torso" + stem + "_MFK"
        matches = c.ls(control, long=True, type="transform") or []
        if len(matches) != 1:
            raise ValueError("轴向分段缺少躯干 FK 控制：" + control)
        source = nodes["FK" + stem + "_M"]["world_matrix"]
        current = c.xform(matches[0], query=True, worldSpace=True, matrix=True)
        if max(abs(float(a) - float(b)) for a, b in zip(
                source, current)) > 1e-3:
            raise ValueError("轴向分段控制器与原版静止姿态不符：" + stem)

    def _create_axial_fk_target(self, spec: AxialPartSpec,
                                guide: Mapping[str, object]) -> tuple[str, str]:
        c = self._cmds
        nodes = guide["nodes"]
        stem = spec.name.split("Part", 1)[0]
        control = (c.ls("AdvPy_Torso" + stem + "_MFK",
                        long=True, type="transform") or [])[0]
        offset = (c.listRelatives(control, parent=True, fullPath=True) or [])[0]
        upstream_name = {"Spine1": "RootPart2_M",
                         "Neck": "Spine1Part2_M"}.get(stem)
        if upstream_name is not None:
            frame_name = "AdvPy_AxialFrame" + stem + "_M"
            proxy_name = "AdvPy_AxialControl" + stem + "_M"
            if "Part1" in spec.name:
                upstream = (c.ls("AdvPy_AxialFKX" + upstream_name, long=True,
                                 type="transform") or [])[0]
                offset = c.createNode("transform",
                                      name=frame_name,
                                      parent=upstream, skipSelect=True)
                c.xform(offset, worldSpace=True,
                        matrix=nodes["FKX" + stem + "_M"]["world_matrix"])
                proxy = c.createNode("transform",
                                     name=proxy_name,
                                     parent=offset, skipSelect=True)
                c.xform(proxy, worldSpace=True,
                        matrix=nodes["FK" + stem + "_M"]["world_matrix"])
                c.setAttr(proxy + ".rotateOrder",
                          nodes["FK" + stem + "_M"]["rotate_order"])
                c.connectAttr(control + ".rotate", proxy + ".rotate")
                control = proxy
            else:
                offset = (c.ls(frame_name, long=True,
                               type="transform") or [])[0]
                control = (c.ls(proxy_name, long=True,
                                type="transform") or [])[0]
        anchor_name = "AdvPy_AxialFKX" + stem + "_M"
        base_name = "AdvPy_AxialBase" + stem + "_M"
        target_name = "AdvPy_AxialTarget" + stem + "_M"
        if "Part1" in spec.name:
            anchor = c.createNode("transform", name=anchor_name,
                                  parent=offset, skipSelect=True)
            c.xform(anchor, worldSpace=True,
                    matrix=nodes["FKX" + stem + "_M"]["world_matrix"])
            base = c.createNode("transform", name=base_name,
                                parent=offset, skipSelect=True)
            c.xform(base, worldSpace=True, matrix=nodes[
                "InbetweenBase" + stem + "_M"]["world_matrix"])
            target = c.createNode("transform", name=target_name,
                                  parent=control, skipSelect=True)
            c.xform(target, worldSpace=True, matrix=nodes[
                "InbetweenTarget" + stem + "_M"]["world_matrix"])
            parent = anchor
        else:
            parent = (c.ls("AdvPy_AxialFKX" + stem + "Part1_M",
                           long=True, type="transform") or [])[0]
            base = (c.ls(base_name, long=True, type="transform") or [])[0]
            target = (c.ls(target_name, long=True, type="transform") or [])[0]
        helper = c.createNode("transform", name="AdvPy_AxialFKX" + spec.name,
                              parent=parent, skipSelect=True)
        c.xform(helper, worldSpace=True,
                matrix=nodes["FKX" + spec.name]["world_matrix"])
        point_target = c.createNode("transform", name="AdvPy_AxialPoint"
                                    + spec.name, parent=parent,
                                    skipSelect=True)
        c.xform(point_target, worldSpace=True,
                matrix=nodes["FKPS2" + spec.name]["world_matrix"])
        blend = c.createNode("blendMatrix", name="AdvPy_AxialBlend_" + spec.name)
        c.connectAttr(base + ".worldMatrix[0]", blend + ".inputMatrix")
        c.connectAttr(target + ".worldMatrix[0]",
                      blend + ".target[0].targetMatrix")
        bias_name = (f"FK{stem}{'Mid' if 'Part1' in spec.name else 'End'}BiasRV_M")
        c.setAttr(blend + ".target[0].rotateWeight",
                  guide["drivers"][bias_name]["out_value"])
        relative = c.createNode("multMatrix", name="AdvPy_AxialRelative_"
                                + spec.name)
        c.connectAttr(blend + ".outputMatrix", relative + ".matrixIn[0]")
        c.connectAttr(offset + ".worldInverseMatrix[0]",
                      relative + ".matrixIn[1]")
        decompose = c.createNode("decomposeMatrix", name="AdvPy_AxialDecompose_"
                                 + spec.name)
        c.connectAttr(relative + ".matrixSum", decompose + ".inputMatrix")
        c.connectAttr(decompose + ".outputRotate", helper + ".rotate")
        if "Part1" in spec.name:
            c.connectAttr(decompose + ".outputRotate", anchor + ".rotate")
        return helper, point_target

    def create_axial_part(self, spec: AxialPartSpec,
                          guide: Mapping[str, object] | None = None) -> None:
        self._require_transaction()
        c = self._cmds
        self._transaction_changed = True
        joint = c.createNode("joint", name=spec.name, parent=spec.parent,
                             skipSelect=True)
        joint = (c.ls(joint, long=True) or [joint])[0]
        if joint != spec.path:
            raise RuntimeError("轴向分段关节路径漂移")
        c.addAttr(joint, longName="advPyAuxiliaryInfluenceKind",
                  dataType="string")
        c.setAttr(joint + ".advPyAuxiliaryInfluenceKind",
                  "axial-part-v1", type="string", lock=True)
        c.xform(joint, worldSpace=True, translation=spec.position)
        if guide is None:
            point_targets = (spec.start, spec.end)
            orient_targets = point_targets
        else:
            orient_target, point_target = self._create_axial_fk_target(
                spec, guide)
            point_targets = (point_target,)
            orient_targets = (orient_target,)
        point = c.pointConstraint(*point_targets, joint,
                                  maintainOffset=False,
                                  name=spec.name + "_pointConstraint")[0]
        orient = c.orientConstraint(*orient_targets, joint,
                                    maintainOffset=False,
                                    name=spec.name + "_orientConstraint")[0]
        for node, command in ((point, c.pointConstraint),
                              (orient, c.orientConstraint)):
            aliases = command(node, query=True, weightAliasList=True) or []
            if len(aliases) == 2:
                c.setAttr(node + "." + aliases[0], 1.0 - spec.fraction)
                c.setAttr(node + "." + aliases[1], spec.fraction)
            elif len(aliases) != 1 or guide is None:
                raise RuntimeError("轴向分段约束目标无效")

    def capture_axial_part(self, spec: AxialPartSpec
                           ) -> tuple[str, str, tuple[float, float, float]]:
        c = self._cmds
        matches = c.ls(spec.path, long=True, type="joint") or []
        if len(matches) != 1:
            raise RuntimeError("轴向分段关节缺失")
        parent = (c.listRelatives(matches[0], parent=True,
                                  fullPath=True) or [""])[0]
        position = tuple(float(v) for v in c.xform(matches[0], query=True,
                         worldSpace=True, translation=True))
        return matches[0], parent, position
