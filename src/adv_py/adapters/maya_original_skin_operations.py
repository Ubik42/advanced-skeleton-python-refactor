"""ADV 6.925 native skin utilities: vertex copy and MotionSystem detach/attach.

The routines below translate the source operations, not surface transfer or a
new influence remapping policy. Maya remains responsible for normalization.
"""
from __future__ import annotations

from contextlib import contextmanager
import re
import shlex


@contextmanager
def _operation(commands, label):
    namespace = commands.namespaceInfo(currentNamespace=True, absoluteName=True)
    if namespace != ":":
        commands.namespace(set=":")
    commands.undoInfo(openChunk=True, chunkName=label)
    try:
        yield
    except Exception:
        commands.undoInfo(closeChunk=True)
        # An empty chunk is not an undo entry. Never undo the user's prior
        # operation when source validation fails before a scene mutation.
        if commands.undoInfo(query=True, undoName=True) == label:
            commands.undo()
        raise
    else:
        commands.undoInfo(closeChunk=True)
    finally:
        if namespace != ":":
            commands.namespace(set=namespace)


def _last_skin(commands, geometry):
    skin = ""
    for node in commands.listHistory(geometry, pruneDagObjects=True) or []:
        if commands.nodeType(node) == "skinCluster":
            skin = node
    return skin


def _object_transform(commands, item):
    objects = commands.ls(item, objectsOnly=True) or []
    if not objects:
        raise ValueError("Object not found: " + item)
    node = objects[0]
    if commands.nodeType(node) == "mesh":
        node = commands.listRelatives(node, parent=True)[0]
    return node


def copy_skin_for_selected_vertices(*, cmds=None) -> int:
    """asCopySkinForVerts, 71062–71229: same-index source vertices/local joints.

    Source may be a mesh or its vertices. Destination vertices can span more
    than one mesh. Influence weights below .001 are ignored by Maya's query;
    missing source indices are skipped, exactly as in the original procedure.
    """
    if cmds is None:
        from maya import cmds
    selected = tuple(cmds.ls(selection=True) or ())
    if len(selected) < 2:
        raise ValueError("Select source mesh or verts, then destination vertices")
    if "." not in selected[-1]:
        raise ValueError("Last selection must be destination vertices")
    source = _object_transform(cmds, selected[0])
    skin = _last_skin(cmds, source)
    if not skin:
        raise ValueError(f'Source "{source}" has no skinCluster')
    method = cmds.getAttr(skin + ".skinningMethod")
    joints = cmds.listConnections(skin + ".matrix") or []
    source_namespace = (joints[0].rsplit(":", 1)[0] + ":"
                        if joints and ":" in joints[0] else "")
    destinations = {}
    for component in cmds.filterExpand(selectionMask=31) or []:
        target = _object_transform(cmds, component)
        if target != source:
            destinations.setdefault(target, []).append(component)
    if not destinations:
        raise ValueError("Select destination vertices on a second mesh")
    copied = 0
    with _operation(cmds, "Copy skin for verts"):
        for target, components in destinations.items():
            if not cmds.listRelatives(target, shapes=True, noIntermediate=True):
                continue
            target_skin = _last_skin(cmds, target)
            if target_skin:
                current = cmds.listConnections(target_skin + ".matrix") or []
                if source_namespace:
                    for joint in current:
                        if joint.startswith(source_namespace):
                            try:
                                cmds.skinCluster(target_skin, edit=True, removeInfluence=joint)
                            except RuntimeError:
                                pass  # catchQuiet in the original
                current = cmds.listConnections(target_skin + ".matrix") or []
                short_names = [joint.rsplit(":", 1)[-1] for joint in current]
                for joint in joints:
                    short = joint.rsplit(":", 1)[-1]
                    if short in short_names:
                        continue
                    if cmds.objExists(short) and cmds.nodeType(short) == "joint":
                        cmds.skinCluster(target_skin, edit=True, lockWeights=False,
                                         weight=0, addInfluence=short)
                        short_names.append(short)
            else:
                bind_joints = []
                for joint in joints:
                    short = joint.rsplit(":", 1)[-1]
                    if (cmds.objExists(short) and cmds.nodeType(short) == "joint"
                            and short not in bind_joints):
                        bind_joints.append(short)
                if not bind_joints:
                    raise ValueError(f'No matching local joints to bind "{target}"')
                cmds.select(bind_joints, replace=True)
                cmds.select(target, add=True)
                from .maya_original_skin_history import new_original_skin_clusters
                target_skin = new_original_skin_clusters(commands=cmds, namespace="")[0]
            for component in components:
                match = re.search(r"\[([^\]]+)\]", component)
                source_vertex = source + ".vtx[" + match.group(1) + "]"
                if not cmds.objExists(source_vertex):
                    continue
                influences = cmds.skinPercent(skin, source_vertex, ignoreBelow=.001,
                                              query=True, transform=None) or []
                values = cmds.skinPercent(skin, source_vertex, ignoreBelow=.001,
                                          query=True, value=True) or []
                weights = [(joint.rsplit(":", 1)[-1], value)
                           for joint, value in zip(influences, values)
                           if cmds.objExists(joint.rsplit(":", 1)[-1])]
                if weights:
                    cmds.skinPercent(target_skin, component, transformValue=weights)
            cmds.setAttr(target_skin + ".skinningMethod", method)
            copied += 1
        cmds.select(selected, replace=True)
    return copied


def detach_motion_system(namespace: str = "", *, cmds=None) -> int:
    """asDetachMotionSystem, 71335–71359: save every incoming joint connection."""
    if cmds is None:
        from maya import cmds
    prefix = namespace.strip(":")
    prefix = prefix + ":" if prefix else ""
    marker = prefix + "asDetachedMotionSystem"
    if cmds.objExists(marker):
        raise ValueError("asDetachedMotionSystem found; MotionSystem is already detached")
    joints = cmds.listRelatives(prefix + "DeformationSystem", type="joint",
                                allDescendents=True) or []
    count = 0
    with _operation(cmds, "Detach MotionSystem"):
        cmds.createNode("transform", name=marker)
        from .maya_original_transform_channels import lock_original_transform_channels
        lock_original_transform_channels(cmds, marker, True, True, True, True)
        script = ""
        for joint in joints:
            connections = cmds.listConnections(joint, source=True, destination=False,
                                                plugs=True, connections=True) or []
            for index in range(0, len(connections), 2):
                destination, source = connections[index:index + 2]
                script += "connectAttr " + source + " " + destination + ";"
                cmds.disconnectAttr(source, destination)
                count += 1
        cmds.addAttr(marker, longName="cmd", dataType="string")
        cmds.setAttr(marker + ".cmd", script, type="string")
    return count


def attach_motion_system(namespace: str = "", *, cmds=None) -> int:
    """asAttachMotionSystem, 71361–71370: replay saved connections without force."""
    if cmds is None:
        from maya import cmds
    prefix = namespace.strip(":")
    marker = (prefix + ":" if prefix else "") + "asDetachedMotionSystem"
    if not cmds.objExists(marker):
        raise ValueError("asDetachedMotionSystem not found")
    script = cmds.getAttr(marker + ".cmd") or ""
    count = 0
    with _operation(cmds, "Attach MotionSystem"):
        for statement in script.split(";"):
            if not statement.strip():
                continue
            tokens = shlex.split(statement)
            if len(tokens) == 3 and tokens[0] == "connectAttr":
                cmds.connectAttr(tokens[1], tokens[2])
            else:
                # A saved scene may contain user-edited MEL. Preserve eval
                # semantics rather than silently discarding an unknown command.
                from maya import mel
                mel.eval(statement + ";")
            count += 1
        cmds.delete(marker)
    return count


def smooth_skin_on_selected(namespace: str = "", *, cmds=None, transactional: bool = True) -> int:
    """asSmoothSkin, 73090–73153, including the source's retained Skin variable.

    This is its Root/Hip/head-Part selection flow and native weightHammerVerts,
    not a whole-mesh smoothWeights replacement. The resulting selection is kept.
    """
    if cmds is None:
        from maya import cmds
    from maya import mel
    from fnmatch import fnmatchcase
    from contextlib import nullcontext
    prefix = namespace.strip(":")
    prefix = prefix + ":" if prefix else ""
    selected = tuple(cmds.ls(selection=True) or ())
    joints = []
    head = prefix + "Head_M"
    if cmds.objExists(head):
        parent = (cmds.listRelatives(head, parent=True) or [""])[0]
        while fnmatchcase(parent, "*Part[0-9]*"):
            joints.append(parent)
            parent = (cmds.listRelatives(parent, parent=True) or [""])[0]
    joints.extend(prefix + leaf for leaf in ("Root_M", "Hip_R", "Hip_L")
                  if cmds.objExists(prefix + leaf))
    from .maya_original_control_identity import original_character_height
    height = original_character_height(cmds, namespace)
    progress = mel.eval("global string $gMainProgressBar; $gMainProgressBar;")
    skin = ""
    affected = 0
    scope = _operation(cmds, "Smooth Skin") if transactional else nullcontext()
    with scope:
        cmds.setToolTo(mel.eval("global string $gSelect; $gSelect;"))
        cmds.softSelect(edit=True, softSelectEnabled=False)
        if cmds.symmetricModelling(query=True, symmetry=True):
            cmds.symmetricModelling(edit=True, symmetry=False)
        try:
            for mesh in selected:
                for node in cmds.listHistory(mesh, pruneDagObjects=True) or []:
                    if cmds.nodeType(node) == "skinCluster":
                        skin = node
                if not skin:
                    raise ValueError("Found no skinCluster on selected object")
                count = int(cmds.polyEvaluate(mesh, vertex=True))
                cmds.progressBar(progress, edit=True, status="Finding Vtx for smoothing",
                                 beginProgress=True, isInterruptable=True,
                                 minValue=0, maxValue=count)
                for vertex in range(count):
                    for index, joint in enumerate(joints):
                        if cmds.progressBar(progress, query=True, isCancelled=True):
                            raise RuntimeError("Interrupted")
                        if index == 0:
                            cmds.progressBar(progress, edit=True, step=1)
                        component = f"{mesh}.vtx[{vertex}]"
                        influences = cmds.skinPercent(skin, component, ignoreBelow=.001,
                                                      query=True, transform=None) or []
                        if joint not in influences:
                            continue
                        cmds.select(component, add=True)
                        if "Root_M" in joint or "Hip_" in joint:
                            x = cmds.xform(component, query=True, worldSpace=True,
                                           translation=True)[0]
                            if height / -5000 < x < height / 5000:
                                cmds.skinPercent(skin, component, transformValue=(joint, 1.))
                if cmds.ls(selection=True):
                    mel.eval("weightHammerVerts;")
                affected += 1
        finally:
            cmds.progressBar(progress, edit=True, endProgress=True)
    return affected
