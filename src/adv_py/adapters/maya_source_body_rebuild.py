"""Recover source FK features from their saved controls and actual drivers."""
from __future__ import annotations

from adv_py.core.body_generic_fk import GenericFkFeaturePolicy
from adv_py.core.character_registry import CharacterRegistryError


def capture_fk_policy(host, registration):
    c = host._cmds
    controls = {}
    keys = {channel.key for channel in registration.channels}
    for node in registration.nodes:
        leaf = node.path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        if (node.node_type == "transform" and leaf.startswith("AdvPy_")
                and leaf.endswith("FK")
                and not leaf.endswith("_InbetweenFK")
                and "|AdvPy_GenericFKControls|" in node.path):
            controls[leaf.removeprefix("AdvPy_")] = node.path
    if "Root_MFK" not in controls:
        raise CharacterRegistryError("来源重建缺少 Root FK 控制身份")
    by_leaf = {}
    for node in registration.nodes:
        by_leaf.setdefault(node.path.rsplit("|", 1)[-1].rsplit(":", 1)[-1], []).append(node)
    scale, compensated, independent, global_controls = set(), set(), set(), set()
    fkx, points = set(), set()
    for stem, control in controls.items():
        leaf = control.rsplit("|", 1)[-1]
        short = leaf.rsplit(":", 1)[-1]
        namespace = leaf[:-len(short)]
        body_stem = stem.removesuffix("FK")
        prefix = "AdvPy_" + body_stem
        orient_name = ("AdvPy_SplineBaseFKOrient" if stem == "SplineBaseFK"
                       else prefix + "FKOrient")
        orients = c.ls(namespace + orient_name, long=True, type="orientConstraint") or []
        if len(orients) != 1:
            raise CharacterRegistryError("来源 FK 朝向驱动缺失或不唯一：" + short)
        outputs = c.listConnections(orients[0] + ".constraintRotateX",
                                   source=False, destination=True, plugs=True) or []
        bendy_constraint = namespace + "AdvPy_BendyDeform" + body_stem
        if not outputs and c.objExists(bendy_constraint):
            if c.nodeType(bendy_constraint) != "parentConstraint":
                raise CharacterRegistryError("来源 Bendy 变形驱动身份无效：" + short)
            drivers = [joint.path for joint in registration.body
                       if joint.path.rsplit("|", 1)[-1].rsplit(":", 1)[-1] == body_stem]
        else:
            if len(outputs) != 1 or not outputs[0].endswith(".rotateX"):
                raise CharacterRegistryError("来源 FK 朝向驱动输出不完整：" + short)
            drivers = c.ls(outputs[0].rsplit(".", 1)[0], long=True) or []
        if len(drivers) != 1 or c.nodeType(drivers[0]) != "joint":
            raise CharacterRegistryError("来源 FK 输出不是唯一机制关节：" + short)
        driver = drivers[0]
        if not outputs:
            host.validate_body_bendy_handoff(driver)
        compound = c.connectionInfo(driver + ".scale", sourceFromDestination=True)
        sources = tuple(c.connectionInfo(driver + ".scale" + axis,
                                         sourceFromDestination=True) for axis in "XYZ")
        if (compound == control + ".scale" or sources == tuple(
                control + ".scale" + axis for axis in "XYZ")):
            scale.add(control)
        bendy_scale = namespace + "AdvPy_BendyDeformScale" + body_stem
        if c.objExists(bendy_scale) and c.connectionInfo(
                bendy_scale + ".input1", sourceFromDestination=True) == control + ".scale":
            scale.add(control)
        point = c.ls(namespace + prefix + "FKPoint", long=True,
                     type="pointConstraint") or []
        if len(point) > 1:
            raise CharacterRegistryError("来源 FK 位置驱动名称重复：" + short)
        if point:
            points.add(short)
        receivers = by_leaf.get("AdvPy_" + stem + "X", ())
        if len(receivers) > 1:
            raise CharacterRegistryError("来源 FKX 名称重复：" + short)
        if receivers and receivers[0].node_type == "joint":
            fkx.add(short)
        offsets = by_leaf.get("AdvPy_" + stem + "Offset", ())
        if len(offsets) != 1:
            raise CharacterRegistryError("来源 FK Offset 缺失或重复：" + short)
        if c.attributeQuery("inheritScale", node=control, exists=True):
            compensated.add(control)
            if not c.getAttr(offsets[0].path + ".inheritsTransform"):
                independent.add(control)
        elif by_leaf.get("AdvPy_" + driver.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
                         + "_FkScaleCompWorldFKPS1"):
            compensated.add(control)
        else:
            parents = c.listRelatives(offsets[0].path, parent=True, fullPath=True) or []
            if (len(parents) == 1 and c.nodeType(parents[0]) == "joint"
                    and not c.getAttr(parents[0] + ".segmentScaleCompensate")
                    and not c.getAttr(driver + ".segmentScaleCompensate")):
                compensated.add(control)
        if "generic.global." + short + ".Global" in keys:
            global_controls.add(control)
    followers = frozenset(leaf.removeprefix("AdvPy_GenericFKFollow_")
                          for leaf in by_leaf if leaf.startswith("AdvPy_GenericFKFollow_"))
    # Generic Aim semantic stems contain the generated prefix; Fit selection
    # uses the original source name shared by both side controls.
    aim_sources = frozenset(channel.key.split(".")[2].removeprefix("AdvPy_")
                           .removesuffix("_FitAim")
                           for channel in registration.channels
                           if channel.key.startswith("generic.aim.")
                           and channel.key.endswith(".follow"))
    return GenericFkFeaturePolicy(
        source_rp_dynamics=any(key.startswith('source.rp.') for key in keys),
        scale_controls=frozenset(scale), compensated_controls=frozenset(compensated),
        global_controls=frozenset(global_controls), aim_sources=aim_sources,
        follower_sources=followers, independent_controls=frozenset(independent),
        fkx_joint_controls=frozenset(fkx), point_controls=frozenset(points))
