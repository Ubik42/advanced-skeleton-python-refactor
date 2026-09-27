"""Exercise product Face eyelid Skin transfer from an ADV scene reference."""
from __future__ import annotations

import json
from math import dist, sqrt
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds
from maya.api import OpenMaya as om

from adv_py.adapters.maya_face_source_skin import (
    MayaFaceSourceSkinHost, _mesh_skin)
from adv_py.product.maya_panel_controller import MayaPanelController


def points(name: str):
    selection = om.MSelectionList()
    selection.add(name)
    return [tuple(float(point[axis]) for axis in range(3))
            for point in om.MFnMesh(selection.getDagPath(0)).getPoints(
                om.MSpace.kWorld)]


def auxiliary_weights(mesh: str, joint: str):
    _, _, _, values, names, _, _ = _mesh_skin(cmds, mesh)
    index = [i for i, name in enumerate(names)
             if name.rsplit("|", 1)[-1].rsplit(":", 1)[-1] == joint]
    if len(index) != 1:
        raise AssertionError("外围影响关节缺失或重名：" + joint)
    width = len(names)
    return [values[vertex * width + index[0]]
            for vertex in range(len(values) // width)]


def main() -> None:
    rebuilt, original, original_motion, scene_output, report_path = (
        Path(value).resolve() for value in sys.argv[1:6])
    reference = json.loads(original_motion.read_text(encoding="utf-8"))
    cmds.file(str(rebuilt), open=True, force=True, executeScriptNodes=False)
    cmds.file(str(original), reference=True, namespace="ADVSource",
              ignoreVersion=True, executeScriptNodes=False)
    source = "ADVSource:model:skin"
    controller = MayaPanelController()
    original_skin = _mesh_skin(cmds, source)[1]
    source_before = tuple(auxiliary_weights(
        source, "lowerLidOuterJoint_" + side) for side in ("R", "L"))
    initial = points("head")
    try:
        controller.face_build_original_eye_lid_skin(":", "head")
    except (ValueError, RuntimeError):
        pass
    else:
        raise AssertionError("来源与目标同一网格未被拒绝")
    assert not cmds.objExists("lowerLidOuterJoint_R")
    host = MayaFaceSourceSkinHost()
    target_skin = (cmds.ls("AdvPy_FacePreSkin", type="skinCluster") or [None])[0]
    baseline = host.capture_dense_skin(target_skin)
    original_apply = MayaFaceSourceSkinHost.apply_dense_skin
    def fail_write(self, data):
        raise RuntimeError("injected Skin write failure")
    MayaFaceSourceSkinHost.apply_dense_skin = fail_write
    try:
        try:
            controller.face_build_original_eye_lid_skin(":", source)
        except RuntimeError as error:
            assert "injected" in str(error)
        else:
            raise AssertionError("注入的 Skin 写入故障未触发")
    finally:
        MayaFaceSourceSkinHost.apply_dense_skin = original_apply
    assert not cmds.objExists("lowerLidOuterJoint_R")
    assert host.capture_dense_skin(target_skin) == baseline
    result = controller.face_build_original_eye_lid_skin(":", source)
    assert result["vertex_count"] == len(initial)
    assert result["mapped_segment_influences"] == 100
    assert result["approximated_segments"] == 8
    assert len(result["auxiliary_joints"]) == 2
    assert result["maximum_rest_position_error_cm"] < 1e-4
    for side, expected in zip(("R", "L"), source_before):
        actual = auxiliary_weights("head", "lowerLidOuterJoint_" + side)
        assert max(abs(a-b) for a, b in zip(actual, expected)) < 1e-6
    cmds.undo()
    assert not cmds.objExists("lowerLidOuterJoint_R")
    cmds.redo()
    assert cmds.objExists("lowerLidOuterJoint_R")
    for side, expected in zip(("R", "L"), source_before):
        actual = auxiliary_weights("head", "lowerLidOuterJoint_" + side)
        assert max(abs(a-b) for a, b in zip(actual, expected)) < 1e-6
    assert cmds.referenceQuery(source, isNodeReferenced=True)
    assert _mesh_skin(cmds, source)[1] == original_skin
    for side, expected in zip(("R", "L"), source_before):
        actual = auxiliary_weights(source, "lowerLidOuterJoint_" + side)
        assert max(abs(a-b) for a, b in zip(actual, expected)) < 1e-8
    opened = points("head")
    for side in ("R", "L"):
        cmds.setAttr("ctrlEye_" + side + ".blink", 10.)
    closed = points("head")
    for side in ("R", "L"):
        cmds.setAttr("ctrlEye_" + side + ".blink", 0.)
    moving = [index for index, (a, b) in enumerate(zip(
        reference["head_open_points"], reference["head_closed_points"]))
        if dist(a, b) > 1e-5]
    errors = [dist(tuple(b[axis] - a[axis] for axis in range(3)),
                   tuple(closed[index][axis] - opened[index][axis]
                         for axis in range(3)))
              for index in moving for a, b in [(
                  reference["head_open_points"][index],
                  reference["head_closed_points"][index])]]
    rms = sqrt(sum(error * error for error in errors) / len(errors))
    moving_target = sum(dist(a, b) > 1e-5
                        for a, b in zip(opened, closed))
    scene_output.parent.mkdir(parents=True, exist_ok=True)
    cmds.file(rename=str(scene_output))
    cmds.file(save=True, type="mayaBinary", force=True)
    cmds.file(new=True, force=True)
    cmds.file(str(scene_output), open=True, force=True,
              executeScriptNodes=False)
    for side, expected in zip(("R", "L"), source_before):
        actual = auxiliary_weights("head", "lowerLidOuterJoint_" + side)
        assert max(abs(a-b) for a, b in zip(actual, expected)) < 1e-6
        source_after = auxiliary_weights(source, "lowerLidOuterJoint_" + side)
        assert max(abs(a-b) for a, b in zip(source_after, expected)) < 1e-8
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps({**result,
        "moved_target_vertices": moving_target,
        "reference_moved_vertices": len(moving),
        "closed_motion_rms_cm": round(rms, 8),
        "undo_redo_reopen": True}, ensure_ascii=False,
        indent=2) + "\n", encoding="utf-8")
    print("Original Face eyelid Skin transfer: OK", report_path,
          flush=True)


if __name__ == "__main__":
    main()
