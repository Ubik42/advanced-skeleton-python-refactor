"""Fresh-process geometry and binding check for an imported face asset."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def main(scene: Path, built: bool, merged_asset: Path | None = None) -> int:
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaFaceHost
        from adv_py.application import load_face_target_asset

        cmds.file(str(scene.resolve()), open=True, force=True)
        host = MayaFaceHost(namespace="hero")
        registration = host.read_character_registration()
        if merged_asset is None:
            original = host.capture_face_mesh("|SmileTarget")
            imported = host.capture_face_mesh("|ImportedSmile")
            expected_points = original.points
            target_path = "|ImportedSmile"
        else:
            imported = host.capture_face_mesh("|MergedSmile")
            expected_points = load_face_target_asset(merged_asset).points_for(
                host.capture_face_mesh("|FaceNeutral"))
            target_path = "|MergedSmile"
        difference = max(abs(a - b) for first, second in
            zip(expected_points, imported.points) for a, b in zip(first, second))
        provenance = json.loads(host.read_face_target_provenance(target_path))
        deformation = 0.
        channels = 0
        if built:
            head = next(joint.path for joint in registration.body
                        if joint.path.rsplit("|", 1)[-1] == "Head_M")
            control = head + "|AdvPy_FaceControls"
            channels = len(host.read_face_manifest(control))
            neutral = host.capture_face_mesh("|FaceNeutral").points
            cmds.setAttr(host.scene_address(control) + ".smile_R", 1.)
            changed = host.capture_face_mesh("|FaceNeutral").points
            deformation = max(abs(a - b) for first, second in
                zip(neutral, changed) for a, b in zip(first, second))
        print(json.dumps({"status": "ok", "joint_count": len(registration.body),
            "max_target_error": difference,
            "source": provenance.get("source"),
            "channel": provenance.get("channel"),
            "face_channels": channels, "max_deformation": deformation}))
        return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), sys.argv[2] == "built",
        Path(sys.argv[3]) if sys.argv[2] == "merged" else None))
