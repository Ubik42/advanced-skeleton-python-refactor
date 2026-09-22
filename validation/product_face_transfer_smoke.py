"""Transfer a sculpt to a subdivided mesh through independent Maya processes."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "validation")]

from product_entry_smoke import _run


def _fixture(source: Path, output: Path) -> None:
    import maya.standalone

    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaFaceHost

        cmds.file(str(source), open=True, force=True)
        host = MayaFaceHost(namespace="hero")
        original = host.scene_address("|FaceNeutral")
        dense = cmds.duplicate(original, name="hero:FaceNeutralDense",
                               returnRootsOnly=True)[0]
        cmds.delete(dense, constructionHistory=True)
        cmds.polySmooth(dense, divisions=1)
        cmds.delete(dense, constructionHistory=True)
        far = cmds.duplicate(dense, name="hero:FaceNeutralFar",
                             returnRootsOnly=True)[0]
        cmds.move(0, 0, 5, far + ".vtx[*]", relative=True, objectSpace=True)
        cmds.file(rename=str(output))
        cmds.file(save=True, type="mayaAscii", force=True)
    finally:
        maya.standalone.uninitialize()


def _inspect(scene: Path, asset_path: Path) -> None:
    import maya.standalone

    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaFaceHost
        from adv_py.application import (BuildFaceBlendShapes,
            load_face_target_asset)
        from adv_py.core import FaceShapeKind, FaceTarget

        cmds.file(str(scene), open=True, force=True)
        host = MayaFaceHost(namespace="hero")
        source = host.capture_face_mesh("|FaceNeutral")
        neutral = host.capture_face_mesh("|FaceNeutralDense")
        sculpt = host.capture_face_mesh("|DenseSmile")
        expected = load_face_target_asset(asset_path).points_for(neutral)
        error = max(abs(a - b) for actual, wanted in zip(sculpt.points, expected)
                    for a, b in zip(actual, wanted))
        built = BuildFaceBlendShapes(host).apply("|FaceNeutralDense",
            (FaceTarget("smile_R", FaceShapeKind.EXPRESSION, "|DenseSmile"),))
        before = host.capture_face_mesh("|FaceNeutralDense").points
        cmds.setAttr(host.scene_address(built.plan.control_path) + ".smile_R", 1.)
        after = host.capture_face_mesh("|FaceNeutralDense").points
        deformation = max(abs(a - b) for first, second in zip(before, after)
                          for a, b in zip(first, second))
        print(json.dumps({"source_vertices": source.vertex_count,
            "target_vertices": neutral.vertex_count, "max_error": error,
            "max_deformation": deformation}), flush=True)
    finally:
        maya.standalone.uninitialize()


def _result(process: subprocess.CompletedProcess[str]) -> dict | None:
    for line in reversed(process.stdout.splitlines()):
        try:
            value = json.loads(line)
            if isinstance(value, dict) and "max_error" in value:
                return value
        except ValueError:
            pass
    return None


def main(mayapy: Path, source: Path, report: Path) -> int:
    report.parent.mkdir(parents=True, exist_ok=True)
    source = source.resolve(strict=True)
    source_hash = sha256(source.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="adv-py-face-transfer-",
                                     dir=report.parent.resolve()) as directory:
        folder = Path(directory)
        scene = folder / "two-topologies.ma"
        setup = subprocess.run([str(mayapy), str(Path(__file__)), "--fixture",
                                str(source), str(scene)], cwd=ROOT,
                               capture_output=True, text=True, timeout=120)
        if setup.returncode:
            raise RuntimeError("fixture failed: " + setup.stderr[-1200:])
        scene_hash = sha256(scene.read_bytes()).hexdigest()
        original = folder / "source.asset.json"
        transferred = folder / "dense.asset.json"
        imported_scene = folder / "dense-imported.ma"
        exported = _run(mayapy, "face-asset-export", str(scene),
            "--namespace", "hero", "--neutral", "|FaceNeutral",
            "--name", "smile_R", "--kind", "expression",
            "--target", "|SmileTarget", "--output", str(original))
        transfer = _run(mayapy, "face-asset-transfer", str(scene),
            "--namespace", "hero", "--source-neutral", "|FaceNeutral",
            "--target-neutral", "|FaceNeutralDense", "--asset", str(original),
            "--max-distance", "0.001", "--output", str(transferred))
        imported = (_run(mayapy, "face-asset-import", str(scene),
            "--namespace", "hero", "--neutral", "|FaceNeutralDense",
            "--asset", str(transferred), "--target", "|DenseSmile",
            "--output", str(imported_scene)) if transferred.exists()
            else (1, None, "transferred asset missing"))
        inspected = (subprocess.run([str(mayapy), str(Path(__file__)), "--inspect",
            str(imported_scene), str(transferred)], cwd=ROOT,
            capture_output=True, text=True, timeout=120)
            if imported_scene.exists() else None)
        details = _result(inspected) if inspected else None
        refused_path = folder / "refused.asset.json"
        refused = _run(mayapy, "face-asset-transfer", str(scene),
            "--namespace", "hero", "--source-neutral", "|FaceNeutral",
            "--target-neutral", "|FaceNeutralFar", "--asset", str(original),
            "--max-distance", "0.001", "--output", str(refused_path))
        checks = {
            "source_asset_exported": exported[0] == 0 and original.exists(),
            "different_topology_asset_transferred": transfer[0] == 0
                and transferred.exists() and transfer[1] is not None
                and transfer[1]["changed_vertices"] > 0,
            "imported_geometry_and_blendshape_verified": imported[0] == 0
                and inspected is not None and inspected.returncode == 0
                and details is not None and details["target_vertices"]
                > details["source_vertices"] and details["max_error"] < 1e-6
                and details["max_deformation"] > .01,
            "far_surface_rejected_without_asset": refused[0] == 2
                and not refused_path.exists(),
            "source_scenes_unchanged": source_hash == sha256(source.read_bytes()).hexdigest()
                and scene_hash == sha256(scene.read_bytes()).hexdigest(),
        }
        payload = {**checks, "details": details,
                   "status": "passed" if all(checks.values()) else "failed"}
        if not all(checks.values()):
            payload["diagnostics"] = {"export": exported[2][-800:],
                "transfer": transfer[2][-900:], "import": imported[2][-900:],
                "inspect": inspected.stderr[-900:] if inspected else "missing",
                "refused": refused[2][-700:]}
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    if sys.argv[1] == "--fixture":
        _fixture(Path(sys.argv[2]), Path(sys.argv[3]))
    elif sys.argv[1] == "--inspect":
        _inspect(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2]),
                              Path(sys.argv[3])))
