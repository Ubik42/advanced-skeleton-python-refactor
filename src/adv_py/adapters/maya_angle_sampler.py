"""Maya locator-distance graph for AdvancedSkeleton angleY/Z inputs."""
from __future__ import annotations

from adv_py.core.angle_sampler_deform import AngleSamplerSpec
from .maya_body import MayaBodyBuildHost


class MayaAngleSamplerHost(MayaBodyBuildHost):
    def preflight_angle_sampler(self, spec: AngleSamplerSpec) -> None:
        c = self._cmds
        for path, original in ((spec.parent, spec.source_parent_world_matrix),
                               (spec.target, spec.source_joint_world_matrix)):
            paths = c.ls(path, long=True, type="joint") or []
            if len(paths) != 1 or paths[0] != path:
                raise ValueError("角度采样器源关节缺失：" + path)
            current = c.xform(path, query=True, worldSpace=True, matrix=True)
            if max(abs(a - b) for a, b in zip(current, original)) > 1e-3:
                raise ValueError("角度采样器源关节静止姿态不匹配：" + path)

    def create_angle_sampler(self, spec: AngleSamplerSpec) -> None:
        self._require_transaction()
        c = self._cmds
        self._transaction_changed = True
        stem = f"{spec.stem}_{spec.side}"
        base_parent_name = stem + "AngleSamplerBaseParent"
        base_name = stem + "AngleSamplerBase"
        rotate_name = stem + "AngleSamplerRotate"
        base_parent = c.createNode("transform", name="AdvPy_" + base_parent_name,
                                    parent=spec.parent, skipSelect=True)
        c.xform(base_parent, worldSpace=True,
                matrix=spec.ancestors[base_parent_name]["world_matrix"])
        base = c.createNode("transform", name="AdvPy_" + base_name,
                            parent=base_parent, skipSelect=True)
        c.xform(base, worldSpace=True,
                matrix=spec.ancestors[base_name]["world_matrix"])
        c.pointConstraint(spec.target, base, maintainOffset=False,
                          name="AdvPy_" + base_name + "_pointConstraint")
        rotate = c.createNode("transform", name="AdvPy_" + rotate_name,
                              parent=base, skipSelect=True)
        c.xform(rotate, worldSpace=True,
                matrix=spec.ancestors[rotate_name]["world_matrix"])
        c.orientConstraint(spec.target, rotate, maintainOffset=False,
                           name="AdvPy_" + rotate_name + "_orientConstraint")
        renamed = {base_parent_name: base_parent,
                   base_name: base, rotate_name: rotate}
        for name, node in spec.graph.items():
            if node["type"] != "locator":
                continue
            parent_name = node["parent"]
            transform = c.createNode("transform",
                name="AdvPy_" + node["transform"],
                parent=renamed[parent_name], skipSelect=True)
            c.setAttr(transform + ".translate", *node["translate"])
            c.setAttr(transform + ".rotate", *node["rotate"])
            c.setAttr(transform + ".scale", *node["scale"])
            shape = c.createNode("locator", name="AdvPy_" + name,
                                  parent=transform, skipSelect=True)
            c.setAttr(shape + ".localPosition", *node["local_position"])
            renamed[name] = shape
        for name, node in spec.graph.items():
            kind = node["type"]
            if kind == "locator":
                continue
            target = c.createNode(kind, name="AdvPy_" + name)
            renamed[name] = target
            if kind == "condition":
                c.setAttr(target + ".operation", node["operation"])
                c.setAttr(target + ".firstTerm", node["first_term"])
                c.setAttr(target + ".secondTerm", node["second_term"])
                c.setAttr(target + ".colorIfTrue", *node["true_color"])
                c.setAttr(target + ".colorIfFalse", *node["false_color"])
            elif kind == "unitConversion":
                c.setAttr(target + ".conversionFactor",
                          node["conversion_factor"])
            elif kind == "plusMinusAverage":
                c.setAttr(target + ".operation", node["operation"])
                for index, values in node["input3d"].items():
                    c.setAttr(f"{target}.input3D[{index}]", *values)
            elif kind == "distanceBetween":
                c.setAttr(target + ".point1", *node["point1"])
                c.setAttr(target + ".point2", *node["point2"])
        for name, node in spec.graph.items():
            for destination, source in node["connections"]:
                source_name, source_attr = source.split(".", 1)
                _, destination_attr = destination.split(".", 1)
                c.connectAttr(renamed[source_name] + "." + source_attr,
                              renamed[name] + "." + destination_attr,
                              force=True)
        for axis, source in spec.outputs.items():
            attribute = "angle" + axis
            c.addAttr(spec.target, longName=attribute,
                      attributeType="double", keyable=False)
            name, plug = source.split(".", 1)
            c.connectAttr(renamed[name] + "." + plug,
                          spec.target + "." + attribute)

    def capture_angle_sampler(self, spec: AngleSamplerSpec) -> dict[str, float]:
        return {axis: float(self._cmds.getAttr(
            spec.target + ".angle" + axis)) for axis in spec.outputs}
