"""Mirror a controller's actual rotation drive without changing user keys."""
from __future__ import annotations

import json
import re
from dataclasses import replace

from adv_py.core.control_orientation import ControlOrientationValidationError
from adv_py.core.character_registry import REGISTRY_NAME, encode_registration


_LINK = "advPyMirroredBehaviorNode"
_DESTINATIONS = "advPyMirroredDestinations"
_CHILDREN = "advPyMirroredChildren"
_NODES = "advPyMirroredUtilityNodes"


def _refresh_registered_children(host, registration, children):
    if not children:
        return
    changed = set(children)
    updated = replace(registration, nodes=tuple(
        host._registry_node(node.path) if node.path in changed else node
        for node in registration.nodes))
    host._validate_character_registration(updated)
    c = host._cmds
    document = REGISTRY_NAME + ".advPyRegistryDocument"
    c.setAttr(document, lock=False)
    c.setAttr(document, encode_registration(updated), type="string")
    c.setAttr(document, lock=True)


def _paired_body_probes(host):
    from maya.api import OpenMaya as om

    c = host._cmds
    registration = host.read_character_registration()
    paths = {joint.path for joint in registration.body}
    result = []
    for right in sorted(paths):
        if not re.search(r"_R(?=\||$)", right):
            continue
        left = re.sub(r"_R(?=\||$)", "_L", right)
        if left not in paths:
            continue
        probes = []
        for path in (right, left):
            frame = om.MMatrix(c.xform(
                path, query=True, worldSpace=True, matrix=True))
            origin = tuple(frame[index] for index in range(12, 15))
            inverse = frame.inverse()
            probes.append(tuple(
                om.MPoint(origin[0] + offset[0],
                          origin[1] + offset[1],
                          origin[2] + offset[2]) * inverse
                for offset in ((0., 0., 0.), (0., 1., 0.),
                               (0., 0., 1.))))
        result.append((right, left, probes[0], probes[1]))
    if not result:
        raise ControlOrientationValidationError("角色没有可用于对称校准的 Body 骨骼")
    return tuple(result)


def _sample_probes(host, probes):
    from maya.api import OpenMaya as om

    c = host._cmds
    result = []
    for right, left, right_local, left_local in probes:
        pair = []
        for path, points in ((right, right_local), (left, left_local)):
            frame = om.MMatrix(c.xform(
                path, query=True, worldSpace=True, matrix=True))
            pair.append(tuple(tuple((point * frame)[axis]
                                    for axis in range(3)) for point in points))
        result.append(tuple(pair))
    return tuple(result)


def _sample_axis(host, probes, control, axis, value):
    c = host._cmds
    plug = control + ".rotate" + axis
    if abs(float(c.getAttr(plug))) > 1e-7:
        raise ControlOrientationValidationError(
            f"镜像行为校准要求零旋转：{control}")
    c.setAttr(plug, value)
    try:
        return _sample_probes(host, probes)
    finally:
        c.setAttr(plug, 0.0)


def _reflection_error(neutral, source, target):
    error = movement = 0.0
    for before_pair, source_pair, target_pair in zip(neutral, source, target):
        for old_right, moved_right, old_left, moved_left in zip(
                before_pair[0], source_pair[0],
                before_pair[1], target_pair[1]):
            for axis in range(3):
                right_delta = moved_right[axis] - old_right[axis]
                left_delta = moved_left[axis] - old_left[axis]
                expected = (-1.0 if axis == 0 else 1.0) * right_delta
                error += (left_delta - expected) ** 2
                movement += right_delta ** 2
    return error, movement


def _calibration_pose(host, probes, right):
    """Use an observable IK state when the current FK state hides the drive."""
    c = host._cmds
    neutral = _sample_probes(host, probes)
    movement = tuple(_reflection_error(
        neutral, _sample_axis(host, probes, right, axis, 10.),
        neutral)[1] for axis in "XYZ")
    if all(value >= 1e-8 for value in movement):
        return neutral, (), movement
    settings = tuple(
        name + "." + attribute + side
        for name, attribute in (("AdvPy_ArmSettings", "armIkFk_"),
                                ("AdvPy_LegSettings", "legIkFk_"))
        for side in ("R", "L")
        if c.objExists(name + "." + attribute + side)
        and c.getAttr(name + "." + attribute + side, settable=True))
    originals = tuple((plug, c.getAttr(plug)) for plug in settings)
    for plug, _ in originals:
        c.setAttr(plug, 1.)
    ik_neutral = _sample_probes(host, probes)
    ik_movement = tuple(_reflection_error(
        ik_neutral, _sample_axis(host, probes, right, axis, 10.),
        ik_neutral)[1] for axis in "XYZ")
    if all(value >= 1e-8 for value in ik_movement):
        return ik_neutral, originals, ik_movement
    for plug, value in originals:
        c.setAttr(plug, value)
    return neutral, (), movement


def _rotation_destinations(c, control):
    links = c.listConnections(
        control + ".rotate", source=False, destination=True,
        plugs=True, connections=True) or []
    if len(links) % 2:
        raise ControlOrientationValidationError("控制器旋转输出连接不完整")
    destinations = []
    for source, destination in zip(links[::2], links[1::2]):
        if (source.split(".", 1)[1] != "rotate"
                or c.ls(source.split(".", 1)[0], long=True)[0] != control):
            continue
        if c.nodeType(destination.split(".", 1)[0]) != "orientConstraint":
            raise ControlOrientationValidationError(
                f"镜像行为尚不能安全接管此旋转驱动：{destination}")
        destinations.append(destination)
    return tuple(dict.fromkeys(destinations))


def _existing_node(c, control):
    if not c.attributeQuery(_LINK, node=control, exists=True):
        return None
    found = c.listConnections(control + "." + _LINK,
                              source=True, destination=False,
                              type="multiplyDivide") or []
    if len(found) > 1:
        raise ControlOrientationValidationError("镜像行为驱动连接歧义")
    return found[0] if found else None


def sync_mirrored_behavior(host, control, enabled):
    """Install or remove a calibrated sign correction on the left control."""
    if not re.search(r"_L(?=(?:FK|IK|PV)?$)",
                     control.rsplit("|", 1)[-1]):
        return
    c = host._cmds
    existing = _existing_node(c, control)
    if not enabled:
        if existing is None:
            return
        registration = host.read_character_registration()
        try:
            destinations = tuple(json.loads(c.getAttr(
                existing + "." + _DESTINATIONS)))
            children = tuple(json.loads(c.getAttr(existing + "." + _CHILDREN)))
            utilities = tuple(json.loads(c.getAttr(existing + "." + _NODES)))
        except (ValueError, TypeError) as exc:
            raise ControlOrientationValidationError(
                "镜像行为驱动目标记录无效") from exc
        for destination in destinations:
            if not c.objExists(destination):
                raise ControlOrientationValidationError(
                    f"镜像行为原驱动目标已失效：{destination}")
            c.connectAttr(control + ".rotate", destination, force=True)
        for child in children:
            offset = child + ".offsetParentMatrix"
            if not c.objExists(offset):
                raise ControlOrientationValidationError(
                    f"镜像行为子控制层级已失效：{child}")
            source = c.connectionInfo(offset, sourceFromDestination=True)
            if not source or source.split(".", 1)[0] != utilities[-1]:
                raise ControlOrientationValidationError(
                    f"镜像行为子控制层级驱动已变化：{child}")
            c.disconnectAttr(source, offset)
            c.setAttr(offset, 1., 0., 0., 0.,
                      0., 1., 0., 0.,
                      0., 0., 1., 0.,
                      0., 0., 0., 1., type="matrix")
        if utilities:
            c.delete(list(utilities))
        c.delete(existing)
        c.deleteAttr(control + "." + _LINK)
        _refresh_registered_children(host, registration, children)
        return
    if existing is not None:
        sync_mirrored_behavior(host, control, False)

    right = re.sub(r"_L(?=(?:FK|IK|PV|Offset)?(?:\||$))", "_R", control)
    if right == control or not c.objExists(right):
        raise ControlOrientationValidationError(
            f"镜像行为需要已登记的右侧配对控制器：{control}")
    for source in (right, control):
        for axis in "XYZ":
            plug = source + ".rotate" + axis
            if (abs(float(c.getAttr(plug))) > 1e-7
                    or c.listConnections(plug, source=True,
                                         destination=False)):
                raise ControlOrientationValidationError(
                    f"镜像行为要求双侧控制器处于零旋转构建姿态：{source}")
    registration = host.read_character_registration()
    destinations = _rotation_destinations(c, control)
    probes = _paired_body_probes(host)
    neutral, mode_restore, movements = _calibration_pose(host, probes, right)
    children = c.listRelatives(control, children=True, fullPath=True,
                               type="transform") or []
    if not destinations:
        if all(value < 1e-8 for value in movements):
            return
        if not children:
            raise ControlOrientationValidationError(
                f"控制器旋转影响 Body，但没有可补偿的旋转驱动：{control}")
    name = "AdvPy_MirroredBehavior_" + control.rsplit("|", 1)[-1]
    if c.objExists(name):
        raise ControlOrientationValidationError("镜像行为驱动节点名称冲突：" + name)
    node = c.createNode("multiplyDivide", name=name, skipSelect=True)
    c.addAttr(node, longName=_DESTINATIONS, dataType="string")
    c.setAttr(node + "." + _DESTINATIONS,
              json.dumps(destinations), type="string")
    c.addAttr(control, longName=_LINK, attributeType="message")
    c.connectAttr(node + ".message", control + "." + _LINK)
    c.connectAttr(control + ".rotate", node + ".input1")
    for destination in destinations:
        c.connectAttr(node + ".output", destination, force=True)
    c.addAttr(node, longName=_CHILDREN, dataType="string")
    c.setAttr(node + "." + _CHILDREN, json.dumps(children), type="string")
    utilities = []
    if children:
        opposite = c.createNode("transform", name=name + "_OppositeRotation",
                                skipSelect=True)
        utilities.append(opposite)
        c.setAttr(opposite + ".hiddenInOutliner", True)
        for attribute in ("translate", "rotateAxis", "scale"):
            c.setAttr(opposite + "." + attribute,
                      *c.getAttr(control + "." + attribute)[0],
                      type="double3")
        c.setAttr(opposite + ".rotateOrder",
                  c.getAttr(control + ".rotateOrder"))
        negative = c.createNode("multiplyDivide", name=name + "_Negate",
                                skipSelect=True)
        utilities.append(negative)
        c.setAttr(negative + ".input2", 1., 1., 1., type="double3")
        c.connectAttr(control + ".rotate", negative + ".input1")
        c.connectAttr(negative + ".output", opposite + ".rotate")
        double = c.createNode("multMatrix", name=name + "_ChildCompensation",
                              skipSelect=True)
        utilities.append(double)
        c.connectAttr(opposite + ".matrix", double + ".matrixIn[0]")
        c.connectAttr(control + ".inverseMatrix", double + ".matrixIn[1]")
        for child in children:
            offset = child + ".offsetParentMatrix"
            if c.listConnections(offset, source=True, destination=False):
                raise ControlOrientationValidationError(
                    f"子控制层级已有位移矩阵驱动：{child}")
            original = c.getAttr(offset)
            if any(abs(value - (1.0 if index % 5 == 0 else 0.0)) > 1e-7
                   for index, value in enumerate(original)):
                raise ControlOrientationValidationError(
                    f"子控制层级已有非单位位移矩阵：{child}")
            c.connectAttr(double + ".matrixSum", offset)
    c.addAttr(node, longName=_NODES, dataType="string")
    c.setAttr(node + "." + _NODES, json.dumps(utilities), type="string")
    for axis in "XYZ":
        source_pose = _sample_axis(host, probes, right, axis, 10.0)
        candidates = []
        for sign in (1.0, -1.0):
            for child_sign in (1.0, -1.0):
                c.setAttr(node + ".input2" + axis, sign)
                if children:
                    c.setAttr(negative + ".input2" + axis, child_sign)
                target_pose = _sample_axis(host, probes, control, axis, 10.0)
                candidates.append((_reflection_error(
                    neutral, source_pose, target_pose), sign, child_sign))
        (error, movement), sign, child_sign = min(
            candidates, key=lambda item: item[0][0])
        c.setAttr(node + ".input2" + axis, sign)
        if children:
            c.setAttr(negative + ".input2" + axis, child_sign)
        if movement < 1e-8:
            raise ControlOrientationValidationError(
                f"镜像行为无法观测到 {axis} 轴的 Body 运动：{right}")
        if error > max(1e-6, movement * .01):
            pair_errors = sorted(((pair[0].rsplit('|', 1)[-1],
                                   _reflection_error((neutral[index],),
                                                     (source_pose[index],),
                                                     (target_pose[index],))[0])
                                  for index, pair in enumerate(probes)),
                                 key=lambda item: item[1], reverse=True)
            raise ControlOrientationValidationError(
                f"镜像行为 {axis} 轴实际 Body 动作未达到对称要求："
                f"误差 {error:.5g}，动作量 {movement:.5g}，"
                f"主要骨骼 {pair_errors[:3]}")
    _refresh_registered_children(host, registration, children)
    for plug, value in mode_restore:
        c.setAttr(plug, value)
