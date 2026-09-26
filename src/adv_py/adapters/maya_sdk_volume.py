"""Recreate original SDK graphs against rebuilt deformation parents."""
from __future__ import annotations

from adv_py.core.sdk_volume_deform import SdkVolumeSpec
from .maya_body import MayaBodyBuildHost


class MayaSdkVolumeHost(MayaBodyBuildHost):
    def _build_graph(self, spec: SdkVolumeSpec, sdk: str) -> None:
        c = self._cmds
        graph = spec.guide["sdk_sources"]
        renamed = {}
        for source_name, node in graph.items():
            new_name = "AdvPy_" + source_name
            renamed[source_name] = c.createNode(node["type"], name=new_name)
        for source_name, node in graph.items():
            target = renamed[source_name]
            kind = node["type"]
            if kind.startswith("animCurve"):
                for value, output in node["keys"]:
                    c.setKeyframe(target, float=value, value=output)
                c.setAttr(target + ".preInfinity", node["pre_infinity"])
                c.setAttr(target + ".postInfinity", node["post_infinity"])
                c.keyTangent(target, edit=True,
                             weightedTangents=node["weighted_tangents"])
                for index, (inside, outside) in enumerate(zip(
                        node["in_tangent_types"], node["out_tangent_types"])):
                    c.keyTangent(target, edit=True, index=(index, index),
                                 inTangentType=inside, outTangentType=outside)
            elif kind == "unitConversion":
                c.setAttr(target + ".conversionFactor",
                          node["conversion_factor"])
            elif kind == "blendWeighted":
                for index, weight in node["weights"].items():
                    c.setAttr(f"{target}.weight[{index}]", weight)

        def resolve(plug: str) -> str:
            node, attribute = plug.split(".", 1)
            if node in renamed:
                return renamed[node] + "." + attribute
            if node == spec.driver_name:
                paths = c.ls(node, long=True, type="joint") or []
                if len(paths) != 1:
                    raise RuntimeError("体积驱动关节缺失：" + node)
                return paths[0] + "." + attribute
            raise RuntimeError("体积曲线包含未知连接：" + plug)

        for source_name, node in graph.items():
            for destination, origin in node["connections"]:
                destination_attr = destination.split(".", 1)[1]
                c.connectAttr(resolve(origin), renamed[source_name] + "."
                              + destination_attr, force=True)
        sdk_row = spec.guide["target_chain"][1]
        for attr, sources in sdk_row["inputs"].items():
            if not sources or attr in ("translate", "rotate", "scale"):
                continue
            if len(sources) != 1:
                raise RuntimeError("体积 SDK 属性需要唯一来源：" + attr)
            c.connectAttr(resolve(sources[0]), sdk + "." + attr, force=True)

    def preflight_sdk_volume_parent(self, spec: SdkVolumeSpec) -> None:
        c = self._cmds
        paths = c.ls(spec.parent, long=True, type="joint") or []
        if len(paths) != 1 or paths[0] != spec.parent:
            raise ValueError("体积关节的变形父关节缺失：" + spec.parent)
        source = spec.guide.get("parent_world_matrix")
        if not isinstance(source, (list, tuple)) or len(source) != 16:
            raise ValueError("体积关节导向缺少父关节静止矩阵：" + spec.name)
        current = c.xform(spec.parent, query=True, worldSpace=True, matrix=True)
        if max(abs(float(a) - b) for a, b in zip(source, current)) > 1e-3:
            raise ValueError("体积关节的来源和目标父关节姿态不匹配：" + spec.name)

    def create_sdk_volume_joint(self, spec: SdkVolumeSpec) -> None:
        self._require_transaction()
        c = self._cmds
        self._transaction_changed = True
        chain = spec.guide["target_chain"]
        base = c.createNode("transform", name="AdvPy_VolumeBase_" + spec.name,
                            parent=spec.parent, skipSelect=True)
        c.xform(base, worldSpace=True, matrix=chain[3]["world_matrix"])
        parent = base
        for index, prefix in ((2, "Offset"), (1, "SDK"), (0, "Target")):
            row = chain[index]
            node = c.createNode("transform", name="AdvPy_Volume" + prefix
                                + "_" + spec.name, parent=parent,
                                skipSelect=True)
            c.setAttr(node + ".translate", *row["translate"])
            c.setAttr(node + ".rotate", *row["rotate"])
            c.setAttr(node + ".scale", *row["scale"])
            parent = node
            if index == 1:
                sdk = node
        self._build_graph(spec, sdk)
        joint = c.createNode("joint", name=spec.name, parent=spec.parent,
                             skipSelect=True)
        joint = (c.ls(joint, long=True) or [joint])[0]
        c.setAttr(joint + ".rotateOrder", spec.guide["joint_rotate_order"])
        c.setAttr(joint + ".jointOrient", *spec.guide["joint_orient"])
        c.xform(joint, worldSpace=True, matrix=spec.guide["joint_world_matrix"])
        c.parentConstraint(parent, joint, maintainOffset=False,
                           name="AdvPy_VolumeConstraint_" + spec.name)
        scale_drivers = spec.guide.get("joint_scale_driver", [])
        if len(scale_drivers) != 1 or scale_drivers[0]["type"] != "multiplyDivide":
            raise RuntimeError("体积关节缺少原版缩放混合图：" + spec.name)
        scale_row = scale_drivers[0]
        scale = c.createNode("multiplyDivide",
                             name="AdvPy_VolumeScale_" + spec.name)
        c.setAttr(scale + ".input1", *scale_row["input1"])
        c.setAttr(scale + ".input2", *scale_row["input2"])
        expected = {
            scale_row["name"] + ".input1": parent + ".scale",
            scale_row["name"] + ".input2": sdk + ".scale",
        }
        original_target = spec.guide["target"] + ".scale"
        original_sdk = spec.guide["target_chain"][1]["name"] + ".scale"
        if dict(scale_row["connections"]) != {
                scale_row["name"] + ".input1": original_target,
                scale_row["name"] + ".input2": original_sdk}:
            raise RuntimeError("体积关节缩放输入与原版不符：" + spec.name)
        for destination, source in expected.items():
            c.connectAttr(source, scale + "." + destination.split(".", 1)[1])
        c.connectAttr(scale + ".output", joint + ".scale")
        c.addAttr(joint, longName="advPyAuxiliaryInfluenceKind", dataType="string")
        c.setAttr(joint + ".advPyAuxiliaryInfluenceKind",
                  "sdk-volume-v1", type="string", lock=True)

    def capture_sdk_volume_joint(self, spec: SdkVolumeSpec) -> tuple[str, str]:
        c = self._cmds
        paths = c.ls(spec.path, long=True, type="joint") or []
        if len(paths) != 1:
            raise RuntimeError("胸部体积关节缺失：" + spec.name)
        parent = (c.listRelatives(paths[0], parent=True, fullPath=True) or [""])[0]
        return paths[0], parent
