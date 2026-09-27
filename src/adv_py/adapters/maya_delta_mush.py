"""AdvancedSkeleton Body Delta Mush operations on selected skinned meshes."""
from __future__ import annotations

from adv_py.core.body_game_engine import BodyGameEnginePolicy, BodyOperation


def _require_delta_mush_available(cmds, namespace: str) -> None:
    if not isinstance(namespace, str):
        raise ValueError("角色命名空间无效")
    scope = namespace.strip(":")
    fit = (scope + ":" if scope else "") + "FitSkeleton"
    if not cmds.objExists(fit):
        return
    enabled = (cmds.attributeQuery("gameEngine", node=fit, exists=True)
               and bool(cmds.getAttr(fit + ".gameEngine")))
    BodyGameEnginePolicy(bool(enabled)).require(BodyOperation.DELTA_MUSH)


def _selected_skinned_meshes(cmds):
    selection = tuple(cmds.ls(selection=True, long=True) or ())
    if not selection:
        raise ValueError("请先选择已蒙皮的多边形网格")
    targets = []
    for mesh in selection:
        if cmds.nodeType(mesh) != "transform":
            raise ValueError(f"请选择网格 Transform：{mesh}")
        shapes = cmds.listRelatives(
            mesh, shapes=True, noIntermediate=True, fullPath=True) or []
        if len(shapes) != 1 or cmds.nodeType(shapes[0]) != "mesh":
            raise ValueError(f"目标不是单一多边形网格：{mesh}")
        history = cmds.listHistory(shapes[0], pruneDagObjects=True) or []
        skins = cmds.ls(history, type="skinCluster") or []
        if len(skins) != 1:
            raise ValueError(f"目标需要唯一的 SkinCluster：{mesh}")
        targets.append((mesh, shapes[0], skins[0], history))
    return selection, targets


def harden_weights_on_selected(*, cmds=None,
                               namespace: str = "") -> tuple[str, ...]:
    """Assign each vertex fully to its strongest influence, as asHardenWeights does."""
    if cmds is None:
        from maya import cmds
    from maya.api import OpenMaya as om
    from maya.api import OpenMayaAnim as oma

    _require_delta_mush_available(cmds, namespace)
    selection, targets = _selected_skinned_meshes(cmds)
    planned = []
    for mesh, shape, skin, _history in targets:
        selected = om.MSelectionList()
        selected.add(skin)
        skin_fn = oma.MFnSkinCluster(selected.getDependNode(0))
        selected = om.MSelectionList()
        selected.add(shape)
        dag = selected.getDagPath(0)
        count = int(cmds.polyEvaluate(mesh, vertex=True))
        component_fn = om.MFnSingleIndexedComponent()
        component = component_fn.create(om.MFn.kMeshVertComponent)
        component_fn.addElements(range(count))
        values, width = skin_fn.getWeights(dag, component)
        influences = tuple(path.fullPathName()
                           for path in skin_fn.influenceObjects())
        if (width != len(influences)
                or len(values) != count * width):
            raise RuntimeError(f"Skin 权重矩阵维度无效：{mesh}")
        groups = [[] for _ in influences]
        for vertex in range(count):
            start = vertex * width
            winner = max(range(width), key=lambda index: values[start + index])
            if values[start + winner] <= 0.001:
                raise ValueError(f"顶点缺少有效 Skin 权重：{mesh}.vtx[{vertex}]")
            groups[winner].append(vertex)
        planned.append((mesh, shape, skin, count, influences, groups))
    changed = False
    cmds.undoInfo(openChunk=True, chunkName="硬化蒙皮权重")
    try:
        for mesh, shape, skin, count, influences, groups in planned:
            for influence in influences:
                plug = influence + ".lockInfluenceWeights"
                if cmds.getAttr(plug):
                    changed = True
                    cmds.setAttr(plug, 0)
            for influence, indices in zip(influences, groups):
                if not indices:
                    continue
                components = [f"{mesh}.vtx[{index}]" for index in indices]
                changed = True
                cmds.skinPercent(skin, components,
                                 transformValue=(influence, 1.),
                                 zeroRemainingInfluences=True,
                                 normalize=True)
            selected = om.MSelectionList()
            selected.add(skin)
            skin_fn = oma.MFnSkinCluster(selected.getDependNode(0))
            selected = om.MSelectionList()
            selected.add(shape)
            dag = selected.getDagPath(0)
            component_fn = om.MFnSingleIndexedComponent()
            component = component_fn.create(om.MFn.kMeshVertComponent)
            component_fn.addElements(range(count))
            readback, width = skin_fn.getWeights(dag, component)
            if width != len(influences) or len(readback) != count * width:
                raise RuntimeError(f"硬化后的 Skin 权重维度无效：{mesh}")
            for influence_index, indices in enumerate(groups):
                for vertex in indices:
                    if (abs(readback[vertex * width + influence_index] - 1.) > 1e-6
                            or any(abs(readback[vertex * width + other]) > 1e-6
                                   for other in range(width)
                                   if other != influence_index)):
                        raise RuntimeError(f"硬化后的 Skin 权重读回不匹配：{mesh}.vtx[{vertex}]")
        cmds.select(selection, replace=True)
    except Exception:
        cmds.undoInfo(closeChunk=True)
        if changed:
            cmds.undo()
        raise
    else:
        cmds.undoInfo(closeChunk=True)
    return tuple(mesh for mesh, *_rest in planned)


def apply_delta_mush_to_selected(*, cmds=None,
                                 namespace: str = "") -> tuple[str, ...]:
    if cmds is None:
        from maya import cmds

    _require_delta_mush_available(cmds, namespace)
    selection, skinned = _selected_skinned_meshes(cmds)
    targets = []
    for mesh, shape, skin, history in skinned:
        if cmds.ls(history, type="deltaMush"):
            raise ValueError(f"目标已有 Delta Mush：{mesh}")
        leaf = mesh.rsplit("|", 1)[-1]
        namespace, _, short_name = leaf.rpartition(":")
        name = (namespace + ":" if namespace else "") + (
            "AdvPy_DeltaMush_" + short_name)
        if cmds.objExists(name):
            raise ValueError(f"Delta Mush 名称已被占用：{name}")
        scopes = (namespace + ":", "") if namespace else ("",)
        scale = None
        for scope in scopes:
            if not cmds.objExists(scope + "Main"):
                continue
            candidate = scope + "MainScaleMultiplyDivide"
            if not cmds.objExists(candidate):
                raise ValueError(f"角色主缩放节点缺失：{candidate}")
            scale = candidate
            break
        targets.append((mesh, shape, skin, name, scale))
    if len({item[3] for item in targets}) != len(targets):
        raise ValueError("所选网格生成了重复的 Delta Mush 名称")

    changed = False
    cmds.undoInfo(openChunk=True, chunkName="应用 Delta Mush")
    try:
        created = []
        for mesh, _shape, skin, name, scale in targets:
            changed = True
            nodes = cmds.deltaMush(mesh, name=name, after=True,
                                   smoothingIterations=10, smoothingStep=0.5,
                                   pinBorderVertices=True, envelope=1.)
            if len(nodes) != 1 or not cmds.objExists(nodes[0]):
                raise RuntimeError(f"Delta Mush 未创建：{mesh}")
            deformer = nodes[0]
            shapes = cmds.listRelatives(
                mesh, shapes=True, noIntermediate=True, fullPath=True) or []
            if len(shapes) != 1 or cmds.nodeType(shapes[0]) != "mesh":
                raise RuntimeError(f"Delta Mush 后网格形状无效：{mesh}")
            history = cmds.listHistory(shapes[0], pruneDagObjects=True) or []
            if deformer not in history or skin not in history:
                raise RuntimeError(f"Delta Mush 与 Skin 连接未写入：{mesh} "
                                   f"deformer={deformer} skin={skin} "
                                   f"history={history}")
            if history.index(deformer) >= history.index(skin):
                raise RuntimeError(f"Delta Mush 未位于 Skin 之后：{mesh}")
            if scale is not None:
                for axis in "XYZ":
                    source = f"{scale}.output{axis}"
                    destination = f"{deformer}.s{axis.lower()}"
                    cmds.connectAttr(source, destination, force=True)
                    if not cmds.isConnected(source, destination):
                        raise RuntimeError(f"Delta Mush 主缩放未连接：{destination}")
            created.append(deformer)
        cmds.select(selection, replace=True)
    except Exception:
        cmds.undoInfo(closeChunk=True)
        if changed:
            cmds.undo()
        raise
    else:
        cmds.undoInfo(closeChunk=True)
        return tuple(created)
