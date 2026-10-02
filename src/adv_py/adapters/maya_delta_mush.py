"""Literal Body Delta Mush and harden-weight flow, ADV 6.925 71231–71333."""
from __future__ import annotations

from contextlib import contextmanager

from .maya_deform_skinning import open_native_bake_deformer


@contextmanager
def _skin_operation(cmds, label):
    """Keep one undo action without changing native deformer/weight policy."""
    cmds.undoInfo(openChunk=True, chunkName=label)
    try:
        yield
    except Exception:
        cmds.undoInfo(closeChunk=True)
        if cmds.undoInfo(query=True, undoName=True) == label:
            cmds.undo()
        raise
    else:
        cmds.undoInfo(closeChunk=True)


def _last_pruned_skin(cmds, mesh):
    skin = ""
    for node in cmds.listHistory(mesh, pruneDagObjects=True) or []:
        if cmds.nodeType(node) == "skinCluster":
            skin = node
    return skin


def harden_weights_on_selected(*, cmds=None, namespace: str = "") -> tuple[str, ...]:
    """asHardenWeights keeps native threshold, influence order and normalization."""
    if cmds is None:
        from maya import cmds
    from maya import mel
    selection = tuple(cmds.ls(selection=True) or ())
    progress = mel.eval("global string $gMainProgressBar; $gMainProgressBar;")
    processed = []
    # MEL retains maxTransform between vertices. Do not replace its > test
    # with a sorted joint list, a new empty-weight failure or an API argmax.
    maximum_transform = ""
    with _skin_operation(cmds, "Harden weights"):
        for mesh in selection:
            if not cmds.listRelatives(mesh, shapes=True, noIntermediate=True):
                continue
            skin = _last_pruned_skin(cmds, mesh)
            if not skin:
                raise ValueError(f'Object:"{mesh}" has not skinCluster')
            for joint in cmds.listConnections(skin + ".matrix") or []:
                cmds.setAttr(joint + ".lockInfluenceWeights", 0)
            count = int(cmds.polyEvaluate(mesh, vertex=True))
            cmds.progressBar(progress, edit=True, status="Hardening Vtx weight",
                             beginProgress=True, isInterruptable=True,
                             minValue=0, maxValue=count)
            try:
                for vertex in range(count):
                    if cmds.progressBar(progress, query=True, isCancelled=True):
                        raise RuntimeError("Interrupted")
                    cmds.progressBar(progress, edit=True, step=1)
                    component = f"{mesh}.vtx[{vertex}]"
                    influences = cmds.skinPercent(skin, component, ignoreBelow=.001,
                                                  query=True, transform=None) or []
                    values = cmds.skinPercent(skin, component, ignoreBelow=.001,
                                              query=True, value=True) or []
                    maximum = 0.
                    for influence, weight in zip(influences, values):
                        if weight > maximum:
                            maximum, maximum_transform = weight, influence
                    cmds.skinPercent(skin, component,
                                      transformValue=(maximum_transform, 1.))
            finally:
                cmds.progressBar(progress, edit=True, endProgress=True)
            processed.append(mesh)
    return tuple(processed)


def connect_delta_mush_scale(*, cmds=None, namespace: str = "") -> tuple[str, ...]:
    """asConnectDeltaMushScale connects all native nodes in character scope.

    X alone is the original already-connected guard. Existing Y/Z input
    connections are not forcibly replaced; their native errors remain visible.
    """
    if cmds is None:
        from maya import cmds
    prefix = namespace.strip(":")
    prefix = prefix + ":" if prefix else ""
    main, scale = prefix + "Main", prefix + "MainScaleMultiplyDivide"
    if not cmds.objExists(main):
        return ()
    nodes = cmds.ls(prefix + "*", type="deltaMush") if prefix else cmds.ls(type="deltaMush")
    connected = []
    for node in nodes or []:
        if cmds.isConnected(scale + ".outputX", node + ".sx"):
            continue
        for axis in "XYZ":
            cmds.connectAttr(scale + ".output" + axis, node + ".s" + axis.lower())
        connected.append(node)
    return tuple(connected)


def apply_delta_mush_to_selected(*, cmds=None, namespace: str = "") -> tuple[str, ...]:
    """asApplyDeltaMush passes the native selection and Maya deformer defaults."""
    if cmds is None:
        from maya import cmds
    with _skin_operation(cmds, "Apply DeltaMush"):
        nodes = cmds.deltaMush(smoothingIterations=10, smoothingStep=.5,
                               pinBorderVertices=True, envelope=1.)
        connect_delta_mush_scale(cmds=cmds, namespace=namespace)
    return tuple(nodes or ())


def open_delta_mush_bake_tool(*, cmds=None, namespace: str = "") -> str:
    """Select the original Body mesh and skeleton for Maya BakeDeformerTool."""
    if cmds is None:
        from maya import cmds
    if not isinstance(namespace, str):
        raise ValueError("角色命名空间无效")
    prefix = ":" + (namespace.strip(":") + ":" if namespace.strip(":")
                    else "")
    root = prefix + "Root_M"
    omitted = {"skinCageShape", "skinSubShape", "BoxSkinMeshShape"}
    future = cmds.listHistory(root, future=True) or () if cmds.objExists(root) else ()
    mesh = ""
    for node in future:
        if cmds.nodeType(node) != "mesh":
            continue
        if node.rsplit("|", 1)[-1].rsplit(":", 1)[-1] in omitted:
            continue
        parents = cmds.listRelatives(node, parent=True, fullPath=True) or ()
        mesh = parents[0] if parents else ""
        break
    options = (
            ("performBakeDeformerSrcMesh", mesh),
            ("performBakeDeformerSrcSkeleton", root),
            ("performBakeDeformerDstMesh", mesh),
            ("performBakeDeformerDstSkeleton", root))
    # The original tool also opens with an empty mesh when Root_M has no
    # downstream geometry. Leave that choice to Maya's BakeDeformerTool.
    for key, value in options:
        cmds.optionVar(stringValue=(key, value))
    open_native_bake_deformer()
    return mesh
