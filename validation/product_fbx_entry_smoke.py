"""Independent-process FBX publish and reimport from a generated body scene."""
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


def _fixture(scene: Path) -> None:
    import maya.standalone

    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (BuildOrientedBodySkeleton,
            BuildSyntheticBodySourceFit, CreateFitSkeleton)

        cmds.file(new=True, force=True)
        cmds.upAxis(axis="z", rotateView=False)
        host = MayaBodyBuildHost()
        fit = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(fit)
        BuildOrientedBodySkeleton(host).apply(fit)
        for frame, x in ((1, 0.), (3, 4.), (5, 8.)):
            cmds.setKeyframe("|Root_M", attribute="translateX",
                             time=frame, value=x)
        cmds.file(rename=str(scene))
        cmds.file(save=True, type="mayaAscii", force=True)
    finally:
        maya.standalone.uninitialize()


def _inspect_fbx(source: Path) -> None:
    import maya.standalone

    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        cmds.file(new=True, force=True)
        cmds.loadPlugin("fbxmaya", quiet=True)
        cmds.file(str(source), i=True, type="FBX", ignoreVersion=True,
                  mergeNamespacesOnClash=False, options="fbx")
        joints = cmds.ls(type="joint", long=True) or []
        frames = {}
        for frame in (1, 3, 5):
            cmds.currentTime(frame)
            roots = cmds.ls("RootMotion", type="joint", long=True) or []
            frames[str(frame)] = (list(cmds.xform(roots[0], query=True,
                worldSpace=True, translation=True)) if len(roots) == 1 else None)
        print(json.dumps({"joints": len(joints), "frames": frames}), flush=True)
    finally:
        maya.standalone.uninitialize()


def main(mayapy: Path, report: Path) -> int:
    report.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="adv-py-fbx-product-",
                                     dir=report.parent.resolve()) as directory:
        folder = Path(directory)
        scene, artifact = folder / "source.ma", folder / "published.fbx"
        fixture = subprocess.run([str(mayapy), str(Path(__file__)),
                                  "--fixture", str(scene)], cwd=ROOT,
                                 capture_output=True, text=True, timeout=120)
        if fixture.returncode:
            raise RuntimeError("fixture failed: " + fixture.stderr[-1000:])
        source_hash = sha256(scene.read_bytes()).hexdigest()
        published = _run(mayapy, "fbx-publish", str(scene), "--namespace", ":",
                         "--start", "1", "--end", "5", "--output", str(artifact))
        reduced_artifact = folder / "reduced.fbx"
        reduced = _run(mayapy, "fbx-publish", str(scene), "--namespace", ":",
                       "--start", "1", "--end", "5", "--curve-policy",
                       "lossless_linear", "--output", str(reduced_artifact))
        imported = subprocess.run([str(mayapy), str(Path(__file__)), "--inspect",
                                   str(artifact)], cwd=ROOT, capture_output=True,
                                  text=True, timeout=120) if artifact.exists() else None
        rows = []
        if imported is not None:
            for line in imported.stdout.splitlines():
                try:
                    row = json.loads(line)
                    if isinstance(row, dict) and "joints" in row:
                        rows.append(row)
                except ValueError:
                    pass
        inspected = rows[-1] if rows else None
        collision = _run(mayapy, "fbx-publish", str(scene), "--namespace", ":",
                         "--start", "1", "--end", "5", "--output", str(artifact))
        rejected = folder / "rejected.fbx"
        bad_range = _run(mayapy, "fbx-publish", str(scene), "--namespace", ":",
                         "--start", "5", "--end", "1", "--output", str(rejected))
        positions = (inspected or {}).get("frames", {})
        checks = {
            "published_binary_fbx": published[0] == 0 and artifact.exists()
                and artifact.read_bytes().startswith(b"Kaydara FBX Binary")
                and published[1] is not None and published[1]["joints"] == 30,
            "reimported_independent_skeleton": imported is not None
                and imported.returncode == 0 and inspected is not None
                and inspected["joints"] == 31,
            "reimported_root_motion": all(positions.get(str(frame)) is not None
                for frame in (1, 3, 5)) and positions["1"][0] < positions["3"][0]
                < positions["5"][0],
            "lossless_curve_policy_publishes": reduced[0] == 0
                and reduced_artifact.exists() and reduced[1] is not None
                and reduced[1]["curve_policy"] == "lossless_linear"
                and reduced[1]["removed_linear_keys"] > 0,
            "collision_rejected": collision[0] == 2,
            "invalid_range_rejected": bad_range[0] == 2 and not rejected.exists(),
            "source_scene_unchanged": source_hash == sha256(scene.read_bytes()).hexdigest(),
        }
        payload = {**checks, "status": "passed" if all(checks.values()) else "failed"}
        if not all(checks.values()):
            payload["diagnostics"] = {"published": published[2][-1000:],
                "reduced": reduced[2][-1000:],
                "imported": imported.stderr[-1000:] if imported else "no FBX",
                "inspected": inspected, "bad_range": bad_range[2][-500:]}
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    if sys.argv[1] == "--fixture":
        _fixture(Path(sys.argv[2]))
    elif sys.argv[1] == "--inspect":
        _inspect_fbx(Path(sys.argv[2]))
    else:
        raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
