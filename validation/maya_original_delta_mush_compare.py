"""Compare the original 6.925 Apply MEL with the Python action on public Sam."""
from __future__ import annotations

import hashlib
import json
from math import sqrt
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
MESH = "|Group|Geometry|model:geo|model:body"


def main(scene: Path, original_mel: Path, report: Path) -> int:
    import maya.standalone

    maya.standalone.initialize(name="python")
    try:
        from maya import cmds, mel
        from adv_py.product.maya_panel_controller import MayaPanelController

        if original_mel.is_dir():
            original_mel = original_mel / "ADV原始代码.mel"
        source = original_mel.read_text(encoding="utf-8")
        start = source.index("global proc asApplyDeltaMush ()")
        end = source.index("global proc asWrapExlude ()", start)
        mel.eval(source[start:end])
        scene_hash = hashlib.sha256(scene.read_bytes()).hexdigest()

        def run(original: bool):
            cmds.file(str(scene.resolve()), open=True, force=True,
                      executeScriptNodes=False)
            cmds.undoInfo(state=True)
            cmds.setAttr("FKShoulder_R.rotateX", 25.)
            cmds.select(MESH, replace=True)
            if original:
                mel.eval("asApplyDeltaMush;")
            else:
                MayaPanelController().delta_mush_apply()
            shape = cmds.listRelatives(MESH, shapes=True,
                noIntermediate=True, fullPath=True)[0]
            history = cmds.listHistory(shape, pruneDagObjects=True) or []
            mush = cmds.ls(history, type="deltaMush") or []
            skins = cmds.ls(history, type="skinCluster") or []
            if len(mush) != 1 or len(skins) != 1:
                raise RuntimeError(f"变形栈不唯一：{history}")
            node = mush[0]
            return {
                "positions": tuple(float(value) for value in cmds.xform(
                    MESH + ".vtx[*]", query=True, worldSpace=True,
                    translation=True)),
                "vertex_count": int(cmds.polyEvaluate(MESH, vertex=True)),
                "node": node,
                "after_skin": history.index(node) < history.index(skins[0]),
                "parameters": tuple(cmds.getAttr(node + "." + attribute)
                    for attribute in ("smoothingIterations", "smoothingStep",
                                      "pinBorderVertices", "envelope")),
                "scale_connected": tuple(cmds.isConnected(
                    "MainScaleMultiplyDivide.output" + axis,
                    node + ".s" + axis.lower()) for axis in "XYZ"),
            }

        original = run(True)
        python = run(False)
        delta = tuple(abs(a - b) for a, b in zip(
            original["positions"], python["positions"]))
        max_error = max(delta)
        rms_error = sqrt(sum(value * value for value in delta) / len(delta))
        checks = {
            "vertex_count_matches": original["vertex_count"] ==
                python["vertex_count"] == 18151,
            "both_after_skin": original["after_skin"] and python["after_skin"],
            "parameters_match": original["parameters"] == python["parameters"],
            "scale_connections_match": original["scale_connected"] ==
                python["scale_connected"] == (True, True, True),
            "vertices_match": max_error < 1e-5,
            "source_file_unchanged": hashlib.sha256(scene.read_bytes()).hexdigest()
                == scene_hash,
        }
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({
            **checks, "asset": scene.name,
            "original_node": original["node"],
            "python_node": python["node"],
            "maximum_position_error_cm": max_error,
            "rms_position_error_cm": rms_error,
            "original_parameters": original["parameters"],
            "python_parameters": python["parameters"],
            "status": "passed" if all(checks.values()) else "failed",
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])))
