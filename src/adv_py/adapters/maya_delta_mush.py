"""Apply Maya Delta Mush after skinning to explicitly selected meshes."""
from __future__ import annotations


def apply_delta_mush_to_selected(*, cmds=None) -> tuple[str, ...]:
    if cmds is None:
        from maya import cmds

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
        if cmds.ls(history, type="deltaMush"):
            raise ValueError(f"目标已有 Delta Mush：{mesh}")
        leaf = mesh.rsplit("|", 1)[-1]
        namespace, _, short_name = leaf.rpartition(":")
        name = (namespace + ":" if namespace else "") + (
            "AdvPy_DeltaMush_" + short_name)
        if cmds.objExists(name):
            raise ValueError(f"Delta Mush 名称已被占用：{name}")
        targets.append((mesh, shapes[0], skins[0], name))
    if len({item[3] for item in targets}) != len(targets):
        raise ValueError("所选网格生成了重复的 Delta Mush 名称")

    changed = False
    cmds.undoInfo(openChunk=True, chunkName="应用 Delta Mush")
    try:
        created = []
        for mesh, _shape, skin, name in targets:
            changed = True
            nodes = cmds.deltaMush(mesh, name=name, after=True)
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
