"""Compare original MEL and Python Harden weights in a Maya GUI session."""
from __future__ import annotations

import json
from pathlib import Path
import traceback

from maya import cmds, mel
import maya.utils
from PySide2 import QtCore

from adv_py.product.maya_panel_controller import MayaPanelController


def schedule(original_mel_directory: str, output_directory: str) -> None:
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)

    def run() -> None:
        data = {}
        try:
            source = (Path(original_mel_directory) /
                      "ADV原始代码.mel").read_text(encoding="utf-8")
            start = source.index("global proc asHardenWeights ()")
            end = source.index("global proc asApplyDeltaMush ()", start)
            mel.eval(source[start:end])
            cmds.file(new=True, force=True)
            mesh = cmds.polyPlane(name="HardenCompareMesh", width=4., height=4.,
                                  subdivisionsX=4, subdivisionsY=4)[0]
            joints = []
            for name, position in (("HardenA", -2.), ("HardenB", 0.),
                                   ("HardenC", 2.)):
                cmds.select(clear=True)
                joints.append(cmds.joint(name=name, position=(position, 0., 0.)))
            skin = cmds.skinCluster(*joints, mesh, name="HardenCompareSkin",
                                    toSelectedBones=True,
                                    maximumInfluences=3)[0]
            patterns = ((0.5, 0.5, 0.), (0., 0.5, 0.5),
                        (0.2, 0.6, 0.2), (0.1, 0.2, 0.7),
                        (0.8, 0.1, 0.1))
            for vertex in range(25):
                cmds.skinPercent(skin, f"{mesh}.vtx[{vertex}]",
                    transformValue=tuple(zip(joints, patterns[vertex % 5])))
            scene = output / "harden-source.ma"
            cmds.file(rename=str(scene))
            cmds.file(save=True, type="mayaAscii", force=True)

            def capture():
                from maya.api import OpenMaya as om
                from maya.api import OpenMayaAnim as oma
                selected = om.MSelectionList()
                selected.add(skin)
                skin_fn = oma.MFnSkinCluster(selected.getDependNode(0))
                shape = cmds.listRelatives(mesh, shapes=True,
                    noIntermediate=True, fullPath=True)[0]
                selected = om.MSelectionList()
                selected.add(shape)
                dag = selected.getDagPath(0)
                component_fn = om.MFnSingleIndexedComponent()
                component = component_fn.create(om.MFn.kMeshVertComponent)
                component_fn.addElements(range(25))
                values, width = skin_fn.getWeights(dag, component)
                return tuple(values), width

            window = cmds.window(title="Harden comparison progress")
            cmds.columnLayout(adjustableColumn=True)
            progress = cmds.progressBar(maxValue=25)
            cmds.showWindow(window)
            mel.eval('global string $gMainProgressBar; $gMainProgressBar = "' +
                     progress + '";')

            cmds.select(mesh, replace=True)
            mel.eval("asHardenWeights;")
            original = capture()
            cmds.file(str(scene), open=True, force=True)
            cmds.select(mesh, replace=True)
            MayaPanelController().delta_mush_harden_weights()
            python = capture()
            difference = max(abs(a - b) for a, b in zip(
                original[0], python[0]))
            data.update({
                "vertex_count": 25,
                "influence_count": original[1],
                "maximum_weight_error": difference,
                "original_matches_python": original[1] == python[1]
                    and difference < 1e-8,
            })
            data["passed"] = data["original_matches_python"]
        except BaseException:
            data["error"] = traceback.format_exc()
            data["passed"] = False
        finally:
            (output / "harden-compare.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            QtCore.QTimer.singleShot(500, lambda: cmds.quit(force=True))

    maya.utils.executeDeferred(run)
