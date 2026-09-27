"""Show evaluated head-and-eye OBJ poses in the Maya viewport."""
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
                for mesh_label in ("head", "right-eye", "left-eye"):
                    key = label + "-" + mesh_label
                    nodes = cmds.file(str(source / (key + ".obj")),
                        i=True, type="OBJ", options="mo=1",
                        ignoreVersion=True, returnNewNodes=True)
                    shapes = cmds.ls(nodes, long=True, type="mesh",
                                     noIntermediate=True) or []
                    parents = {path for shape in shapes for path in
                               (cmds.listRelatives(shape, parent=True,
                                                   fullPath=True) or [])}
                    if len(parents) != 1:
                        raise RuntimeError(key + " OBJ 网格数量无效")
                    meshes[key] = cmds.rename(next(iter(parents)),
                                             key.replace("-", "_"))
                    cmds.polySoftEdge(meshes[key], angle=180,
                                      constructionHistory=False)
                    cmds.setAttr(meshes[key] + ".visibility", label == "open")
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
            eye_bounds = [cmds.exactWorldBoundingBox(meshes[
                "open-" + mesh_label])
                for mesh_label in ("right-eye", "left-eye")]
            x_min = min(bounds[0] for bounds in eye_bounds)
            x_max = max(bounds[3] for bounds in eye_bounds)
            y_min = min(bounds[1] for bounds in eye_bounds)
            y_max = max(bounds[4] for bounds in eye_bounds)
            cmds.setAttr(camera + ".orthographicWidth",
                         max((x_max - x_min) * 1.55, .5))
            cmds.setAttr(camera + ".translateY", (y_min + y_max) / 2.)
            for label, frame in (("open", 1), ("blink", 10)):
                for key, mesh in meshes.items():
                    cmds.setAttr(mesh + ".visibility",
                                 key.startswith(label + "-"))
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
