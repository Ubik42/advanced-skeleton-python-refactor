"""Capture the evaluated Maya Face rig without reimporting or smoothing OBJ.

Call schedule from a Maya GUI session. The source scene is opened read only;
shader and pose changes exist only in the temporary GUI session.
"""
from __future__ import annotations

import json
from pathlib import Path
import traceback

from maya import cmds
import maya.utils
from PySide2 import QtCore, QtGui


def _red_pixels(path: Path) -> int:
    image = QtGui.QImage(str(path)).convertToFormat(
        QtGui.QImage.Format_RGBA8888)
    if image.isNull():
        raise RuntimeError("Maya 截图无法读取：" + str(path))
    pixels = bytes(image.constBits())
    return sum(1 for index in range(0, len(pixels), 4)
               if pixels[index] > 80
               and pixels[index] - pixels[index + 1] > 35
               and pixels[index] > pixels[index + 1] * 1.25
               and pixels[index] > pixels[index + 2] * 1.25)


def schedule(scene_path: str, output_path: str,
             aim_x_cm: float = 0., aim_y_cm: float = 0.) -> None:
    scene = Path(scene_path).resolve()
    output = Path(output_path).resolve()
    output.mkdir(parents=True, exist_ok=True)

    def run() -> None:
        result = {"scene": scene.name, "aim_x_cm": aim_x_cm,
                  "aim_y_cm": aim_y_cm}
        try:
            cmds.file(str(scene), open=True, force=True,
                      executeScriptNodes=False)
            head = (cmds.ls("head", type="transform") or [None])[0]
            if head is None:
                raise RuntimeError("Face 头部网格缺失")
            eye_meshes = [cmds.skinCluster("AdvPy_EyeSkin_" + suffix,
                                          query=True, geometry=True)[0]
                          for suffix in ("R", "L")]
            for fit in cmds.ls("FaceFitSkeleton", type="transform") or []:
                cmds.setAttr(fit + ".visibility", False)
            # The original combined eye can remain visible after Face Pre.
            # Color it too, so it cannot mask one of the skinned eyes in grey.
            eye_meshes.extend(cmds.ls("eyeOutter", type="transform") or [])
            for label, color, meshes in (
                    ("Head", (.55, .55, .55), [head]),
                    ("Eye", (.8, .18, .12), eye_meshes)):
                shader = cmds.shadingNode("lambert" if label == "Head"
                                          else "surfaceShader", asShader=True,
                                          name="AdvPyRigSnapshot" + label)
                cmds.setAttr(shader + (".color" if label == "Head"
                                     else ".outColor"), *color, type="double3")
                group = cmds.sets(renderable=True, noSurfaceShader=True,
                                  empty=True, name=shader + "SG")
                cmds.connectAttr(shader + ".outColor",
                                 group + ".surfaceShader", force=True)
                for mesh in set(meshes):
                    cmds.sets(mesh, edit=True, forceElement=group)
            panel = (cmds.getPanel(type="modelPanel") or [None])[0]
            if panel is None:
                raise RuntimeError("Maya 图形会话缺少视口")
            cmds.select(clear=True)
            cmds.setFocus(panel)
            cmds.lookThru(panel, "front")
            cmds.modelEditor(panel, edit=True,
                             displayAppearance="smoothShaded",
                             displayTextures=False, grid=False,
                             joints=False, nurbsCurves=False)
            camera = cmds.modelPanel(panel, query=True, camera=True)
            bounds = [cmds.exactWorldBoundingBox(mesh)
                      for mesh in eye_meshes[:2]]
            x_min = min(item[0] for item in bounds)
            x_max = max(item[3] for item in bounds)
            y_min = min(item[1] for item in bounds)
            y_max = max(item[4] for item in bounds)
            cmds.setAttr(camera + ".orthographicWidth",
                         max((x_max - x_min) * 1.55, .5))
            cmds.setAttr(camera + ".translateY", (y_min + y_max) / 2.)
            initial = {suffix + axis: cmds.getAttr(
                "AdvPy_EyeAim_" + suffix + ".translate" + axis)
                for suffix in ("R", "L") for axis in "XY"}
            for label, blink in (("open", 0.), ("blink", 10.)):
                cmds.currentTime(1, edit=True)
                for suffix in ("R", "L"):
                    for axis, offset in (("X", aim_x_cm), ("Y", aim_y_cm)):
                        cmds.setAttr("AdvPy_EyeAim_" + suffix +
                                     ".translate" + axis,
                                     initial[suffix + axis] + offset)
                    cmds.setAttr("ctrlEye_" + suffix + ".blink", blink)
                cmds.refresh(force=True)
                result[label] = cmds.playblast(format="image",
                    compression="png", viewer=False, offScreen=True,
                    showOrnaments=False, startTime=1, endTime=1,
                    widthHeight=(1280, 900), percent=100,
                    filename=str(output / label), forceOverwrite=True)
                result[label + "_red_pixels"] = _red_pixels(
                    output / (label + ".0001.png"))
            result["passed"] = all((output / (label + ".0001.png")).is_file()
                                   for label in ("open", "blink"))
        except BaseException:
            result["error"] = traceback.format_exc()
            result["passed"] = False
        finally:
            (output / "report.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            QtCore.QTimer.singleShot(500, lambda: cmds.quit(force=True))

    maya.utils.executeDeferred(run)
