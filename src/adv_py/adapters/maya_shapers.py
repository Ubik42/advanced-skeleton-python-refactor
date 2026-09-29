"""Operations on existing AdvancedSkeleton Shapers deformers."""
from __future__ import annotations

import importlib
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
