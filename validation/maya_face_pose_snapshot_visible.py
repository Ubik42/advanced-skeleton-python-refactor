"""Show two Maya-evaluated Face pose OBJ snapshots in one Maya viewport."""
from __future__ import annotations

import json
from pathlib import Path
import traceback

from maya import cmds
import maya.utils
from PySide2 import QtCore


def schedule(source_directory: str, output_directory: str) -> None:
    source = Path(source_directory).resolve()
    output = Path(output_directory).resolve()
    output.mkdir(parents=True, exist_ok=True)

    def run() -> None:
        data = {}
        try:
            cmds.file(new=True, force=True)
            cmds.loadPlugin("objExport", quiet=True)
            meshes = {}
            for label in ("open", "blink"):
                nodes = cmds.file(str(source / (label + "-head.obj")),
                    i=True, type="OBJ", options="mo=1",
                    ignoreVersion=True, returnNewNodes=True)
                shapes = cmds.ls(nodes, long=True, type="mesh",
                                 noIntermediate=True) or []
                parents = {path for shape in shapes for path in
                           (cmds.listRelatives(shape, parent=True,
                                               fullPath=True) or [])}
                if len(parents) != 1:
                    raise RuntimeError(label + " OBJ 网格数量无效")
                meshes[label] = cmds.rename(next(iter(parents)),
                                           label + "Head")
                cmds.polySoftEdge(meshes[label], angle=180,
                                  constructionHistory=False)
            cmds.setAttr(meshes["blink"] + ".visibility", False)
            cmds.select(clear=True)
            panel = (cmds.getPanel(type="modelPanel") or [None])[0]
            if panel is None:
                raise RuntimeError("Maya 图形会话缺少视口")
            cmds.setFocus(panel)
            cmds.lookThru(panel, "front")
            cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded",
                             displayTextures=False, grid=False,
                             joints=False, nurbsCurves=False)
            camera = cmds.modelPanel(panel, query=True, camera=True)
            cmds.setAttr(camera + ".orthographicWidth", 14)
            cmds.setAttr(camera + ".translateY", 175.7)
            for label, frame in (("open", 1), ("blink", 10)):
                cmds.setAttr(meshes["open"] + ".visibility",
                             label == "open")
                cmds.setAttr(meshes["blink"] + ".visibility",
                             label == "blink")
                cmds.currentTime(frame, edit=True)
                cmds.refresh(force=True)
                data[label] = cmds.playblast(format="image",
                    compression="png", viewer=False, offScreen=True,
                    showOrnaments=False, startTime=frame, endTime=frame,
                    widthHeight=(1280, 900), percent=100,
                    filename=str(output / ("snapshot-" + label)),
                    forceOverwrite=True)
            data["passed"] = (bool(list(output.glob("snapshot-open.*.png")))
                              and bool(list(output.glob("snapshot-blink.*.png"))))
        except BaseException:
            data["error"] = traceback.format_exc()
            data["passed"] = False
        finally:
            (output / "snapshot-visible.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            QtCore.QTimer.singleShot(500, lambda: cmds.quit(force=True))

    maya.utils.executeDeferred(run)
