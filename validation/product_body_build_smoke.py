"""Build and reopen a complete registered body from a generated Fit scene."""
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


def _fixture(scene: Path, segments: int = 2) -> None:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (CreateFitSkeleton,
            BuildSyntheticBodySourceFit, BuildVariableBodySourceFit)

        cmds.upAxis(axis="z", rotateView=False)
        cmds.undoInfo(state=True)
        if segments != 2:
            cmds.namespace(addNamespace="hero")
        host = MayaBodyBuildHost(namespace="hero" if segments != 2 else None)
        container = CreateFitSkeleton(host).apply().state.path
        if segments == 2:
            BuildSyntheticBodySourceFit(host).apply(container)
        else:
            BuildVariableBodySourceFit(host).apply(container,
                spine_segments=segments, with_hand=True)
        cmds.file(rename=str(scene))
        cmds.file(save=True, type="mayaAscii", force=True)
    finally:
        maya.standalone.uninitialize()


def _inspect(scene: Path, namespace: str = ":") -> None:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import ResolveBodyCharacter, CaptureBodyCharacterPose

        cmds.file(str(scene), open=True, force=True)
        host = MayaBodyBuildHost(namespace=None if namespace == ":" else namespace)
        registration = ResolveBodyCharacter(host).execute()
        pose = CaptureBodyCharacterPose(host).execute()
        print(json.dumps({"status": "ok", "joints": len(registration.body),
            "channels": len(registration.channels),
            "pose_channels": len(pose.channels),
            "digest": registration.compatibility_digest}), flush=True)
    finally:
        maya.standalone.uninitialize()


def main(mayapy: Path, report: Path) -> int:
    report.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="adv-py-body-build-",
                                     dir=report.parent.resolve()) as directory:
        folder = Path(directory)
        source = folder / "fit-only.ma"
        built = folder / "registered-body.ma"
        fixture = subprocess.run([str(mayapy), str(Path(__file__)), "--fixture",
            str(source)], cwd=ROOT, capture_output=True, text=True, timeout=120)
        if fixture.returncode:
            raise RuntimeError("fixture failed: " + fixture.stderr[-1200:])
        original_hash = sha256(source.read_bytes()).hexdigest()
        build = _run(mayapy, "body-build", str(source), "--namespace", ":",
            "--output", str(built))
        inspect = (subprocess.run([str(mayapy), str(Path(__file__)), "--inspect",
            str(built)], cwd=ROOT, capture_output=True, text=True, timeout=120)
            if built.exists() else None)
        details = None
        if inspect:
            for line in reversed(inspect.stdout.splitlines()):
                try:
                    row = json.loads(line)
                    if row.get("status") == "ok":
                        details = row
                        break
                except (ValueError, AttributeError):
                    pass
        checks = {
            "built_from_fit_and_registered": build[0] == 0 and build[1] is not None
                and built.exists() and build[1]["joints"] == 30,
            "reopened_pose_and_registration": inspect is not None
                and inspect.returncode == 0 and details is not None
                and details["joints"] == 30
                and details["channels"] == details["pose_channels"]
                and details["digest"] == build[1]["compatibility_digest"],
            "source_unchanged": original_hash == sha256(source.read_bytes()).hexdigest(),
        }
        variable_source = folder / "variable-fit.ma"
        variable_built = folder / "variable-registered.ma"
        variable_fixture = subprocess.run([str(mayapy), str(Path(__file__)),
            "--fixture", str(variable_source), "4"], cwd=ROOT,
            capture_output=True, text=True, timeout=120)
        if variable_fixture.returncode:
            raise RuntimeError("variable fixture failed: "
                               + variable_fixture.stderr[-1200:])
        variable_hash = sha256(variable_source.read_bytes()).hexdigest()
        variable_build = _run(mayapy, "body-build", str(variable_source),
            "--namespace", "hero", "--spine-segments", "4",
            "--head-aim", "--output", str(variable_built))
        variable_inspect = (subprocess.run([str(mayapy), str(Path(__file__)),
            "--inspect", str(variable_built), "hero"], cwd=ROOT,
            capture_output=True, text=True, timeout=120)
            if variable_built.exists() else None)
        variable_details = None
        if variable_inspect:
            for line in reversed(variable_inspect.stdout.splitlines()):
                try:
                    row = json.loads(line)
                    if row.get("status") == "ok":
                        variable_details = row
                        break
                except (ValueError, AttributeError):
                    pass
        checks["variable_named_character_reopened"] = (
            variable_build[0] == 0 and variable_build[1] is not None
            and variable_inspect is not None and variable_inspect.returncode == 0
            and variable_details is not None and variable_details["joints"] > 70
            and variable_details["channels"] == variable_details["pose_channels"]
            and variable_details["digest"] == variable_build[1]["compatibility_digest"]
            and variable_hash == sha256(variable_source.read_bytes()).hexdigest())
        rejected_output = folder / "rejected.ma"
        rejected = _run(mayapy, "body-build", str(source), "--namespace", ":",
            "--fit", "MissingFit", "--output", str(rejected_output))
        checks["bad_fit_rejected_without_scene"] = (
            rejected[0] == 2 and not rejected_output.exists()
            and original_hash == sha256(source.read_bytes()).hexdigest())
        payload = {**checks, "details": details,
            "variable_details": variable_details,
            "status": "passed" if all(checks.values()) else "failed"}
        if not all(checks.values()):
            payload["diagnostics"] = {"build": build[2][-1200:],
                "inspect": inspect.stderr[-1200:] if inspect else "missing",
                "variable_build": variable_build[2][-1200:],
                "variable_inspect": variable_inspect.stderr[-1200:]
                    if variable_inspect else "missing",
                "rejected": rejected[2][-1200:]}
        report.write_text(json.dumps(payload, ensure_ascii=False, indent=2)
                          + "\n", encoding="utf-8")
        return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    if sys.argv[1] == "--fixture":
        _fixture(Path(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 2)
    elif sys.argv[1] == "--inspect":
        _inspect(Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else ":")
    else:
        raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
