"""Compare every Sam skin weight after original and Python Harden actions."""
from __future__ import annotations

import hashlib
import json
from math import sqrt
from pathlib import Path
import traceback

from maya import cmds, mel
import maya.utils
from PySide2 import QtCore

from adv_py.product.maya_panel_controller import MayaPanelController


MESH = "|Group|Geometry|model:geo|model:body"


def schedule(scene_path: str, original_mel_directory: str,
             output_directory: str) -> None:
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)

    def run() -> None:
        data = {}
        try:
            scene = Path(scene_path)
            source_hash = hashlib.sha256(scene.read_bytes()).hexdigest()
            original_mel = (Path(original_mel_directory) /
                            "ADV原始代码.mel").read_text(encoding="utf-8")
            start = original_mel.index("global proc asHardenWeights ()")
            end = original_mel.index("global proc asApplyDeltaMush ()", start)
            mel.eval(original_mel[start:end])

            def open_scene():
                cmds.file(str(scene.resolve()), open=True, force=True,
                          executeScriptNodes=False)
                cmds.undoInfo(state=True)
                if not cmds.objExists(MESH):
                    raise RuntimeError("公开 Sam 主体网格不存在")
                shape = cmds.listRelatives(MESH, shapes=True,
                    noIntermediate=True, fullPath=True)[0]
                skin = (cmds.ls(cmds.listHistory(shape) or [],
                    type="skinCluster") or [])[0]
                count = int(cmds.polyEvaluate(MESH, vertex=True))
                return shape, skin, count

            def capture(shape, skin, count):
                from maya.api import OpenMaya as om
                from maya.api import OpenMayaAnim as oma

                selected = om.MSelectionList()
                selected.add(skin)
                skin_fn = oma.MFnSkinCluster(selected.getDependNode(0))
                selected = om.MSelectionList()
                selected.add(shape)
                dag = selected.getDagPath(0)
                component_fn = om.MFnSingleIndexedComponent()
                component = component_fn.create(om.MFn.kMeshVertComponent)
                component_fn.addElements(range(count))
                values, width = skin_fn.getWeights(dag, component)
                influence_paths = tuple(path.fullPathName() for path in
                                        skin_fn.influenceObjects())
                locks = tuple(bool(cmds.getAttr(path + ".lockInfluenceWeights"))
                              for path in influence_paths)
                if len(values) != count * width or width != len(influence_paths):
                    raise RuntimeError("Sam 权重矩阵维度无效")
                return tuple(values), width, influence_paths, locks

            shape, skin, count = open_scene()
            progress_window = cmds.window(title="Sam Harden original comparison")
            cmds.columnLayout(adjustableColumn=True)
            progress = cmds.progressBar(maxValue=count)
            cmds.showWindow(progress_window)
            mel.eval('global string $gMainProgressBar; $gMainProgressBar = "' +
                     progress + '";')
            data["stage"] = "original_running"
            (output / "stage.json").write_text(json.dumps(data) + "\n",
                                                encoding="utf-8")
            cmds.select(MESH, replace=True)
            mel.eval("asHardenWeights;")
            original = capture(shape, skin, count)

            data["stage"] = "python_running"
            (output / "stage.json").write_text(json.dumps(data) + "\n",
                                                encoding="utf-8")
            shape, skin, count = open_scene()
            cmds.select(MESH, replace=True)
            MayaPanelController().delta_mush_harden_weights()
            python = capture(shape, skin, count)
            differences = tuple(abs(a - b) for a, b in zip(
                original[0], python[0]))
            maximum = max(differences)
            rms = sqrt(sum(value * value for value in differences) /
                       len(differences))
            checks = {
                "all_weights_match": len(original[0]) == len(python[0])
                    and maximum < 1e-8,
                "influence_order_matches": original[1:3] == python[1:3],
                "joint_locks_match": original[3] == python[3],
                "source_file_unchanged":
                    hashlib.sha256(scene.read_bytes()).hexdigest() == source_hash,
            }
            data = {
                **checks, "asset": scene.name, "vertex_count": count,
                "influence_count": original[1],
                "maximum_weight_error": maximum,
                "rms_weight_error": rms,
                "status": "passed" if all(checks.values()) else "failed",
            }
        except BaseException:
            data = {"error": traceback.format_exc(), "status": "failed"}
        finally:
            (output / "public-harden-compare.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            QtCore.QTimer.singleShot(500, lambda: cmds.quit(force=True))

    maya.utils.executeDeferred(run)
