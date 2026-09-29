"""Operations on existing AdvancedSkeleton Shapers deformers."""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
import sys


def _cmds():
    from maya import cmds
    return cmds


def list_shapers(namespace: str) -> tuple[str, ...]:
    """Return deformers in the selected character namespace."""
    cmds = _cmds()
    prefix = "" if namespace in ("", ":") else namespace.strip(":") + ":"
    nodes = cmds.ls(type="shapersDeformer") or []
    return tuple(sorted(node for node in nodes
                        if node.rsplit("|", 1)[-1].startswith(prefix)
                        and (prefix or ":" not in node.rsplit("|", 1)[-1])))


def _targets(namespace: str, node: str | None) -> tuple[str, ...]:
    available = list_shapers(namespace)
    if node is None:
        return available
    if node not in available:
        raise ValueError("所选 Shapers 变形器不属于当前角色：" + node)
    return (node,)


def select_shapers(namespace: str, node: str | None = None) -> int:
    cmds = _cmds()
    targets = _targets(namespace, node)
    if targets:
        cmds.select(list(targets), replace=True)
    else:
        cmds.select(clear=True)
    return len(targets)


def _python_shapers(cmds):
    for plugin in cmds.pluginInfo(query=True, listPlugins=True) or []:
        if "shapersDeformer" not in (cmds.pluginInfo(
                plugin, query=True, dependNode=True) or []):
            continue
        path = Path(cmds.pluginInfo(plugin, query=True, path=True) or "")
        if path.suffix.lower() != ".py":
            break
        directory = str(path.parent)
        if directory not in sys.path:
            sys.path.insert(0, directory)
        return importlib.import_module("Shapers")
    raise RuntimeError("Shapers 插件未提供可用的重绑命令")


def rebind_shapers(namespace: str, node: str | None = None) -> int:
    """Use the loaded native command or the original Python fallback."""
    cmds = _cmds()
    targets = _targets(namespace, node)
    if not targets:
        return 0
    missing = [target for target in targets if not cmds.objExists(target)]
    if missing:
        raise RuntimeError("Shapers 变形器已不存在：" + ", ".join(missing))
    native = getattr(cmds, "shapersRebuild", None)
    fallback = None if native else _python_shapers(cmds)
    for target in targets:
        if native:
            native(target)
        else:
            fallback.rebuild(target)
    return len(targets)


@dataclass(frozen=True, slots=True)
class ShapersDeleteResult:
    deformers: int
    collapsed_shapes: int
    cleanup_errors: tuple[str, ...]


def _collapse_output_shapes(cmds, mesh: str) -> int:
    """Undo the outputShape -> tweak -> intermediateShape wrapper from MEL."""
    collapsed = 0
    while cmds.objExists(mesh):
        visible = cmds.listRelatives(mesh, shapes=True,
                                     noIntermediate=True, fullPath=True,
                                     type="mesh") or []
        if len(visible) != 1:
            break
        output = visible[0]
        output_input = cmds.connectionInfo(
            output + ".inMesh", sourceFromDestination=True)
        tweak = output_input.split(".", 1)[0] if output_input else ""
        if not tweak or not cmds.objExists(tweak) or cmds.nodeType(tweak) != "tweak":
            break
        tweak_input = cmds.connectionInfo(
            tweak + ".input[0].inputGeometry", sourceFromDestination=True)
        source = tweak_input.split(".", 1)[0] if tweak_input else ""
        if (not source or not cmds.objExists(source)
                or cmds.nodeType(source) != "mesh"
                or not cmds.getAttr(source + ".intermediateObject")):
            break
        source_parent = cmds.listRelatives(source, parent=True,
                                           fullPath=True) or []
        output_parent = cmds.listRelatives(output, parent=True,
                                           fullPath=True) or []
        if (not source_parent or source_parent != output_parent
                or not output.rsplit("|", 1)[-1].startswith(
                    source.rsplit("|", 1)[-1] + "Deformed")):
            break
        destinations = cmds.connectionInfo(
            output + ".worldMesh[0]", destinationFromSource=True) or []
        for destination in destinations:
            if cmds.isConnected(output + ".worldMesh[0]", destination):
                cmds.disconnectAttr(output + ".worldMesh[0]", destination)
        cmds.setAttr(source + ".intermediateObject", False)
        cmds.delete(output)
        if cmds.objExists(tweak):
            cmds.delete(tweak)
        for destination in destinations:
            if cmds.objExists(destination):
                cmds.connectAttr(source + ".worldMesh[0]", destination,
                                 force=True)
        collapsed += 1
    return collapsed


def delete_shapers(namespace: str) -> ShapersDeleteResult:
    """Remove current-character deformers and restore their mesh history."""
    cmds = _cmds()
    targets = list_shapers(namespace)
    selection = cmds.ls(selection=True, long=True) or []
    affected: set[str] = set()
    errors: list[str] = []
    collapsed = 0
    cmds.undoInfo(openChunk=True, chunkName="删除 Shapers")
    try:
        for node in targets:
            if not cmds.objExists(node):
                continue
            for geometry in cmds.deformer(node, query=True, geometry=True) or []:
                kind = cmds.nodeType(geometry)
                if kind == "mesh":
                    affected.update(cmds.listRelatives(
                        geometry, parent=True, fullPath=True) or [])
                elif kind == "transform":
                    affected.add(geometry)
                try:
                    cmds.deformer(node, edit=True, remove=True,
                                  geometry=geometry)
                except RuntimeError as error:
                    errors.append(f"{node}：无法移除 {geometry}（{error}）")
            if cmds.objExists(node):
                try:
                    cmds.delete(node)
                except RuntimeError as error:
                    errors.append(f"{node}：无法删除变形器（{error}）")
        for mesh in sorted(affected):
            if cmds.objExists(mesh):
                try:
                    collapsed += _collapse_output_shapes(cmds, mesh)
                except RuntimeError as error:
                    errors.append(f"{mesh}：无法清理形状层（{error}）")
        root = ("" if namespace in ("", ":")
                else namespace.strip(":") + ":") + "ShaperControls"
        if cmds.objExists(root):
            try:
                cmds.delete(root)
            except RuntimeError as error:
                errors.append(f"{root}：无法删除控制组（{error}）")
        existing = [node for node in selection if cmds.objExists(node)]
        if existing:
            cmds.select(existing, replace=True)
        else:
            cmds.select(clear=True)
    finally:
        cmds.undoInfo(closeChunk=True)
    remaining = [node for node in targets if cmds.objExists(node)]
    if remaining:
        errors.append("仍存在 Shapers 变形器：" + ", ".join(remaining))
    return ShapersDeleteResult(len(targets) - len(remaining), collapsed,
                               tuple(errors))
