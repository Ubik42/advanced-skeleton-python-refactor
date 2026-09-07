from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaFitJointHost
        from adv_py.application import EnsureFitSkeletonSettings
        from adv_py.core import FitSkeletonField, FitSkeletonValidationError

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        container = cmds.createNode("transform", name="PortableFitSettings")
        cmds.addAttr(
            container,
            longName="visGeo",
            attributeType="bool",
            defaultValue=True,
        )
        cmds.addAttr(
            container,
            longName="visGap",
            attributeType="double",
            defaultValue=0.4,
            minValue=0,
            maxValue=1,
        )
        cmds.addAttr(container, longName="preRebuildScript", dataType="string")
        script_text = 'createNode -n "MustNotRun" transform;'
        cmds.setAttr(f"{container}.preRebuildScript", script_text, type="string")

        host = MayaFitJointHost()
        use_case = EnsureFitSkeletonSettings(host)
        cmds.file(modified=False)
        preview = use_case.plan(container, vis_gap_default=0.6)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        result = use_case.apply(container, vis_gap_default=0.6)
        verified = result.verified
        complete = len(verified.present_fields) == len(FitSkeletonField)
        existing_preserved = (
            verified.value(FitSkeletonField.VIS_GEOMETRY) is True
            and verified.value(FitSkeletonField.VIS_GAP) == 0.4
            and verified.value(FitSkeletonField.PRE_REBUILD_SCRIPT) == script_text
        )
        defaults_applied = (
            verified.value(FitSkeletonField.VIS_GEOMETRY_TYPE) == "cylinders"
            and verified.value(FitSkeletonField.LOCK_CENTER_JOINTS) is True
        )
        script_not_executed = not cmds.objExists("MustNotRun")

        cmds.undo()
        undo_restored = (
            cmds.attributeQuery("visGeo", node=container, exists=True)
            and cmds.attributeQuery("visGap", node=container, exists=True)
            and cmds.attributeQuery("preRebuildScript", node=container, exists=True)
            and not cmds.attributeQuery("visGeoType", node=container, exists=True)
            and not cmds.attributeQuery(
                "postRebuildScript", node=container, exists=True
            )
        )

        invalid = cmds.createNode(
            "transform", name="PortableFitSettingsInvalid"
        )
        cmds.addAttr(invalid, longName="visGap", dataType="string")
        cmds.setAttr(f"{invalid}.visGap", "invalid", type="string")
        cmds.file(modified=False)
        invalid_blocked = False
        try:
            use_case.apply(invalid)
        except FitSkeletonValidationError:
            invalid_blocked = True
        invalid_clean = not bool(cmds.file(query=True, modified=True))

        cmds.delete(container, invalid)
        remaining = cmds.ls("PortableFitSettings*", long=True) or []
        passed = all(
            (
                preview_clean,
                len(preview.additions) == len(FitSkeletonField) - 3,
                complete,
                existing_preserved,
                defaults_applied,
                script_not_executed,
                undo_restored,
                invalid_blocked,
                invalid_clean,
                not remaining,
            )
        )
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "fit_skeleton_settings",
            "preview_addition_count": len(preview.additions),
            "preview_did_not_modify_scene": preview_clean,
            "complete_settings": complete,
            "existing_values_preserved": existing_preserved,
            "defaults_applied": defaults_applied,
            "stored_script_not_executed": script_not_executed,
            "single_undo_restored": undo_restored,
            "invalid_schema_blocked": invalid_blocked,
            "invalid_preflight_did_not_modify_scene": invalid_clean,
            "cleanup": not remaining,
            "remaining_nodes": remaining,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "status": "passed" if passed else "failed",
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return 0 if passed else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
