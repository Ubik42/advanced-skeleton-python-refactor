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


def _fixture(source: Path, output: Path, target_only: Path) -> None:
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
        cmds.delete(host.scene_address("|FaceNeutral"),
                    host.scene_address("|SmileTarget"))
        cmds.file(rename=str(target_only))
        cmds.file(save=True, type="mayaAscii", force=True)
    finally:
        maya.standalone.uninitialize()


def _inspect(scene: Path, asset_path: Path,
             geometry_path: Path | None = None) -> None:
    import maya.standalone

    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaFaceHost
        from adv_py.application import (BuildFaceBlendShapes,
            load_face_target_asset, load_face_neutral_geometry)
        from adv_py.core import FaceShapeKind, FaceTarget

        cmds.file(str(scene), open=True, force=True)
        host = MayaFaceHost(namespace="hero")
        source = (load_face_neutral_geometry(geometry_path).mesh
                  if geometry_path else host.capture_face_mesh("|FaceNeutral"))
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
        target_only = folder / "target-only.ma"
        setup = subprocess.run([str(mayapy), str(Path(__file__)), "--fixture",
                                str(source), str(scene), str(target_only)], cwd=ROOT,
                               capture_output=True, text=True, timeout=120)
        if setup.returncode:
            raise RuntimeError("fixture failed: " + setup.stderr[-1200:])
        scene_hash = sha256(scene.read_bytes()).hexdigest()
        target_hash = sha256(target_only.read_bytes()).hexdigest()
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
        geometry_path = folder / "source.geometry.json"
        geometry_export = _run(mayapy, "face-geometry-export", str(scene),
            "--namespace", "hero", "--neutral", "|FaceNeutral",
            "--output", str(geometry_path))
        cross_asset = folder / "cross.asset.json"
        cross_transfer = (_run(mayapy, "face-asset-transfer", str(target_only),
            "--namespace", "hero", "--source-geometry", str(geometry_path),
            "--target-neutral", "|FaceNeutralDense", "--asset", str(original),
            "--max-distance", "0.001", "--output", str(cross_asset))
            if geometry_path.exists() else (1, None, "geometry missing"))
        cross_scene = folder / "cross-imported.ma"
        cross_import = (_run(mayapy, "face-asset-import", str(target_only),
            "--namespace", "hero", "--neutral", "|FaceNeutralDense",
            "--asset", str(cross_asset), "--target", "|DenseSmile",
            "--output", str(cross_scene)) if cross_asset.exists()
            else (1, None, "cross asset missing"))
        cross_inspected = (subprocess.run([str(mayapy), str(Path(__file__)),
            "--inspect", str(cross_scene), str(cross_asset), str(geometry_path)],
            cwd=ROOT, capture_output=True, text=True, timeout=120)
            if cross_scene.exists() else None)
        cross_details = _result(cross_inspected) if cross_inspected else None
        corrupt_geometry = folder / "corrupt.geometry.json"
        if geometry_path.exists():
            damaged = json.loads(geometry_path.read_text(encoding="utf-8"))
            damaged["payload"]["points"][0][0] += 1.
            corrupt_geometry.write_text(json.dumps(damaged), encoding="utf-8")
        corrupt_output = folder / "corrupt.asset.json"
        corrupt_rejected = (_run(mayapy, "face-asset-transfer", str(target_only),
            "--namespace", "hero", "--source-geometry", str(corrupt_geometry),
            "--target-neutral", "|FaceNeutralDense", "--asset", str(original),
            "--max-distance", "0.001", "--output", str(corrupt_output))
            if corrupt_geometry.exists() else (1, None, "corrupt geometry missing"))
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
            "source_geometry_document_exported": geometry_export[0] == 0
                and geometry_path.exists() and geometry_export[1] is not None
                and geometry_export[1]["vertices"] == 4,
            "cross_scene_transfer_import_and_binding": cross_transfer[0] == 0
                and cross_import[0] == 0 and cross_inspected is not None
                and cross_inspected.returncode == 0 and cross_details is not None
                and cross_details["max_error"] < 1e-6
                and cross_details["max_deformation"] > .01,
            "corrupt_geometry_rejected_without_asset": corrupt_rejected[0] == 2
                and not corrupt_output.exists(),
            "imported_geometry_and_blendshape_verified": imported[0] == 0
                and inspected is not None and inspected.returncode == 0
                and details is not None and details["target_vertices"]
                > details["source_vertices"] and details["max_error"] < 1e-6
                and details["max_deformation"] > .01,
            "far_surface_rejected_without_asset": refused[0] == 2
                and not refused_path.exists(),
            "source_scenes_unchanged": source_hash == sha256(source.read_bytes()).hexdigest()
                and scene_hash == sha256(scene.read_bytes()).hexdigest()
                and target_hash == sha256(target_only.read_bytes()).hexdigest(),
        }
        payload = {**checks, "details": details, "cross_scene_details": cross_details,
                   "status": "passed" if all(checks.values()) else "failed"}
        if not all(checks.values()):
            payload["diagnostics"] = {"export": exported[2][-800:],
                "transfer": transfer[2][-900:], "import": imported[2][-900:],
                "geometry_export": geometry_export[2][-800:],
                "cross_transfer": cross_transfer[2][-800:],
                "cross_import": cross_import[2][-800:],
                "cross_inspect": cross_inspected.stderr[-800:]
                    if cross_inspected else "missing",
                "corrupt_rejected": corrupt_rejected[2][-800:],
                "inspect": inspected.stderr[-900:] if inspected else "missing",
                "refused": refused[2][-700:]}
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    if sys.argv[1] == "--fixture":
        _fixture(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
    elif sys.argv[1] == "--inspect":
        _inspect(Path(sys.argv[2]), Path(sys.argv[3]),
                 Path(sys.argv[4]) if len(sys.argv) > 4 else None)
    else:
        raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2]),
                              Path(sys.argv[3])))
