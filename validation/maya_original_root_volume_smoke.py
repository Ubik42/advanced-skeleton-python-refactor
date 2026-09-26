"""Compare rebuilt RootA influences with the public AdvancedSkeleton scene."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _matrix(cmds, path: str) -> tuple[float, ...]:
    return tuple(cmds.xform(path, query=True, worldSpace=True, matrix=True))


def main(scene: Path, report: Path) -> int:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters.maya_body import MayaBodyBuildHost
        from adv_py.adapters.maya_root_volume import MayaRootVolumeHost
        from adv_py.application.registered_body_build import BuildRegisteredBodyCharacter
        from adv_py.application.root_volume_deform import BuildRootVolumeDeform
        from adv_py.application.character_registry import ResolveBodyCharacter

        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        fits = cmds.ls("FitSkeleton", type="transform", long=True) or []
        if len(fits) != 1:
            raise ValueError("原版场景需要唯一 FitSkeleton")
        rows = []
        rest = {}
        for side in ("R", "L"):
            name = "RootAJoint_" + side
            rest[name] = _matrix(cmds, name)
            rows.append({
                "name": name,
                "parent": (cmds.listRelatives(name, parent=True) or [None])[0],
                "target_parent": "OffsetRootA_" + side,
                "joint_local_translate": cmds.getAttr(name + ".translate")[0],
                "joint_local_rotate": cmds.getAttr(name + ".rotate")[0],
                "joint_orient": cmds.getAttr(name + ".jointOrient")[0],
                "joint_local_scale": cmds.getAttr(name + ".scale")[0],
                "joint_rotate_order": cmds.getAttr(name + ".rotateOrder"),
            })
        guide = {"root_world_matrix": _matrix(cmds, "Root_M"),
                 "joints": rows}
        fit_parent = (cmds.listRelatives(fits[0], parent=True,
                                        fullPath=True) or [""])[0]
        cmds.delete(tuple(path for path in (cmds.listRelatives(
            fit_parent, children=True, fullPath=True) or ()) if path != fits[0]))
        built = BuildRegisteredBodyCharacter(MayaBodyBuildHost()).apply(
            fits[0], infer_missing_labels=True)
        wrong_matrix = list(guide["root_world_matrix"])
        wrong_matrix[12] += 1.0
        wrong_guide = {**guide, "root_world_matrix": wrong_matrix}
        mismatched_guide_rejected = False
        try:
            BuildRootVolumeDeform(MayaRootVolumeHost()).apply(wrong_guide)
        except ValueError:
            mismatched_guide_rejected = all(
                not cmds.objExists(row["name"]) for row in rows)

        class FaultHost(MayaRootVolumeHost):
            calls = 0

            def create_root_volume_joint(self, spec):
                super().create_root_volume_joint(spec)
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("injected fault")

        fault_rolled_back = False
        try:
            BuildRootVolumeDeform(FaultHost()).apply(guide)
        except RuntimeError as exc:
            fault_rolled_back = str(exc) == "injected fault" and all(
                not cmds.objExists(row["name"]) for row in rows)
        specs = BuildRootVolumeDeform(MayaRootVolumeHost()).apply(guide)
        rest_error = max(abs(a - b) for spec in specs
                         for a, b in zip(rest[spec.name], _matrix(cmds, spec.path)))
        cmds.undo()
        undo_removed = all(not cmds.objExists(spec.path) for spec in specs)
        cmds.redo()
        redo_restored = all(cmds.objExists(spec.path) for spec in specs)
        before = {spec.name: _matrix(cmds, spec.path) for spec in specs}
        global_control = built.rig.plan.global_control.control_path
        cmds.setAttr(global_control + ".translateX", 2.0)
        after = {spec.name: _matrix(cmds, spec.path) for spec in specs}
        motion = {name: after[name][12] - before[name][12] for name in before}
        cmds.setAttr(global_control + ".translateX", 0.0)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "root_volume.ma"
            cmds.file(rename=str(path))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(str(path), open=True, force=True,
                      executeScriptNodes=False)
            reopened = all(cmds.objExists(spec.path) for spec in specs)
            registered = len(ResolveBodyCharacter(MayaBodyBuildHost()).execute().body)
        data = {
            "source": scene.name, "root_volume_count": len(specs),
            "maximum_original_rest_matrix_error": rest_error,
            "fault_rolled_back": fault_rolled_back,
            "mismatched_guide_rejected": mismatched_guide_rejected,
            "undo_removed": undo_removed, "redo_restored": redo_restored,
            "global_translate_x": motion,
            "save_reopen_retained": reopened,
            "registered_body_count": registered,
        }
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        if (len(specs) != 2 or rest_error > 1e-4 or not fault_rolled_back
                or not mismatched_guide_rejected
                or not undo_removed or not redo_restored or not reopened
                or registered != 74 or any(abs(v - 2.0) > 1e-4
                                            for v in motion.values())):
            raise AssertionError(data)
        return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
