"""Read the saved product output in a fresh Maya process."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def main(scene: Path, control: str) -> int:
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaFaceHost
        cmds.file(str(scene.resolve()), open=True, force=True)
        host = MayaFaceHost(namespace="hero")
        registration = host.read_character_registration()
        target = host.capture_face_mesh("|BlinkTarget")
        provenance = host.read_face_target_provenance("|BlinkTarget")
        manifest = host.read_face_manifest(control)
        cmds.currentTime(40)
        quiet = host.capture_face_mesh("|FaceNeutral").points
        cmds.currentTime(44)
        spoken = host.capture_face_mesh("|FaceNeutral").points
        mesh_delta = max(abs(a - b) for first, second in zip(quiet, spoken)
                         for a, b in zip(first, second))
        value = float(cmds.getAttr(host.scene_address(control) + ".viseme_A",
                                   time=44))
        print(json.dumps({"status": "ok", "joint_count": len(registration.body),
            "target_vertices": target.vertex_count,
            "provenance_channel": json.loads(provenance)["channel"],
            "face_channels": len(manifest), "mesh_delta": mesh_delta,
            "viseme_at_44": value}, ensure_ascii=False))
        return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), sys.argv[2]))
