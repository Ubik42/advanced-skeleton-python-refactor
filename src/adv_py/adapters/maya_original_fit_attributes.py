"""Literal asGetScale/asEnsureAllFitJointAttrs, ADV 6.925, 7968–8083."""
from __future__ import annotations


def original_fit_scale(commands, fit="FitSkeleton"):
    if not commands.objExists(fit):
        return 1.
    maximum = 0.
    for joint in commands.listRelatives(fit, fullPath=True, allDescendents=True, type="joint") or []:
        maximum = max(maximum, commands.xform(joint, query=True, worldSpace=True, translation=True)[1])
    return max(maximum / 17.176163 if maximum > 0 else 1., .01)


def ensure_original_fit_attributes(commands, fit, deformation_system, rla_child):
    """Source order matters: parents precede ends, old values migrate in place.

    Preserve the source's fatYAbs branch literally. It deletes fatFrontAbs,
    not fatYAbs; a scene containing that legacy attribute can fail on the
    subsequent connection just as the reference does. Do not silently repair
    legacy business behavior while claiming a faithful port.
    """
    c = commands
    selection = c.ls(selection=True) or []
    joints = c.listRelatives(fit, allDescendents=True, type="joint") or []
    try:
        for joint in reversed(joints):
            ensure_original_fit_joint_attributes(c, joint, fit, rla_child)
        if c.objExists(deformation_system):
            for joint in c.listRelatives(deformation_system, allDescendents=True, type="joint") or []:
                for attribute in ("fatFront", "fatWidth"):
                    if not c.objExists(joint + "." + attribute):
                        c.addAttr(joint, longName=attribute, attributeType="double", keyable=True, minValue=0, defaultValue=1)
                for old, new in (("fatY", "fatFront"), ("fatZ", "fatWidth")):
                    if c.objExists(joint + "." + old):
                        c.setAttr(joint + "." + new, c.getAttr(joint + "." + old))
                        c.deleteAttr(joint + "." + old)
    finally:
        try:
            c.select(selection, replace=True) if selection else c.select(clear=True)
        except RuntimeError:
            pass


def ensure_original_fit_joint_attributes(c, joint, fit, rla_child):
    """asEnsureFitJointAttrs, 8005–8083; also valid before creating FitSkeleton."""
    scale = original_fit_scale(c, fit)
    primary = c.getAttr(fit + ".primaryAxis", asString=True) if c.objExists(fit + ".primaryAxis") else "X"
    if not c.objExists(joint + ".fat"):
        value = 1.
        child = rla_child(joint)
        if child:
            value = abs(c.getAttr(child + ".translate" + primary)) / 4
            position = c.xform(joint, query=True, worldSpace=True, translation=True)
            if -.01 * scale < position[0] < .01 * scale:
                value *= 2
            if value < .0001:
                value = scale
        else:
            parent = (c.listRelatives(joint, parent=True, type="joint") or [""])[0]
            if parent and c.objExists(parent + ".fat"):
                value = c.getAttr(parent + ".fat")
        c.addAttr(joint, longName="fat", attributeType="double", keyable=True, minValue=0, defaultValue=value)
    if not c.objExists(joint + ".fatFront"):
        value = c.getAttr(joint + ".fat")
        c.deleteAttr(joint + ".fat")
        c.addAttr(joint, longName="fat", attributeType="double", keyable=True, minValue=0, defaultValue=value)
        c.addAttr(joint, longName="fatFront", attributeType="double", keyable=True, minValue=0, defaultValue=1)
    if not c.objExists(joint + ".fatWidth"):
        c.addAttr(joint, longName="fatWidth", attributeType="double", keyable=True, minValue=0, defaultValue=1)
    for attribute in ("fatFrontAbs", "fatWidthAbs"):
        if not c.objExists(joint + "." + attribute):
            c.addAttr(joint, longName=attribute, attributeType="double", keyable=False)
    for old, new in (("fatY", "fatFront"), ("fatZ", "fatWidth")):
        if c.objExists(joint + "." + old):
            c.setAttr(joint + "." + new, c.getAttr(joint + "." + old))
            c.deleteAttr(joint + "." + old)
    if c.objExists(joint + ".fatYAbs"):
        c.deleteAttr(joint + ".fatFrontAbs")
    if c.objExists(joint + ".fatZabs"):
        c.deleteAttr(joint + ".fatZabs")
    fat_node = joint.rsplit("|", 1)[-1] + "Fat"
    if c.objExists(fat_node):
        c.delete(fat_node)
    c.createNode("multiplyDivide", name=fat_node)
    for source, target in ((joint + ".fat", fat_node + ".input1Y"),
                           (joint + ".fat", fat_node + ".input1Z"),
                           (joint + ".fatFront", fat_node + ".input2Y"),
                           (joint + ".fatWidth", fat_node + ".input2Z"),
                           (fat_node + ".outputY", joint + ".fatFrontAbs"),
                           (fat_node + ".outputZ", joint + ".fatWidthAbs")):
        c.connectAttr(source, target, force=True)
