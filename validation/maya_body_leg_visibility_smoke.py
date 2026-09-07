from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def visible(cmds, path: str) -> bool:
    return bool(cmds.getAttr(f"{path}.visibility"))


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (
            BuildBodyLegBlend,
            BuildBodyLegFkMechanismControls,
            BuildBodyLegIkControls,
            BuildBodyLegMechanisms,
            BuildBodyLegVisibility,
            BuildOrientedBodySkeleton,
            BuildSyntheticBodySourceFit,
            CreateFitSkeleton,
        )

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode("transform", name="PortableLegVisibilitySelection", skipSelect=True)
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        BuildOrientedBodySkeleton(host).apply(container)
        BuildBodyLegMechanisms(host).apply(container)
        fk = BuildBodyLegFkMechanismControls(host).apply(container).snapshot
        blend = BuildBodyLegBlend(host).apply(container).snapshot
        ik = BuildBodyLegIkControls(host).apply(container).snapshot
        cmds.select(marker, replace=True)

        use_case = BuildBodyLegVisibility(host)
        cmds.file(modified=False)
        preview = use_case.plan(container)
        preview_clean = not bool(cmds.file(query=True, modified=True))
        result = use_case.apply(container)

        by_side = {side.side.value: side for side in result.plan.visibility.sides}
        default_fk = all(
            visible(cmds, side.fk_offset_path)
            and all(not visible(cmds, path) for path in side.ik_offset_paths)
            for side in by_side.values()
        )
        cmds.undoInfo(stateWithoutFlush=False)
        cmds.setAttr(f"{blend.settings_path}.legIkFk_R", 1.0)
        right = by_side["R"]
        left = by_side["L"]
        right_ik = (
            not visible(cmds, right.fk_offset_path)
            and all(visible(cmds, path) for path in right.ik_offset_paths)
        )
        left_independent = (
            visible(cmds, left.fk_offset_path)
            and all(not visible(cmds, path) for path in left.ik_offset_paths)
            and cmds.getAttr(f"{blend.settings_path}.legIkFk_L") == 0.0
        )
        cmds.setAttr(f"{blend.settings_path}.legIkFk_R", 0.0)
        cmds.undoInfo(stateWithoutFlush=True)

        checks = {
            "preview_ready": preview.ready,
            "preview_did_not_modify_scene": preview_clean,
            "two_independent_sides": len(result.snapshot.sides) == 2,
            "default_fk_only": default_fk,
            "right_switches_to_ik": right_ik,
            "left_side_independent": left_independent,
            "selection_preserved": (cmds.ls(selection=True) or []) == [marker],
        }
        cmds.undo()
        all_offsets = tuple(
            path
            for side in by_side.values()
            for path in (side.fk_offset_path, *side.ik_offset_paths)
        )
        checks["single_undo_removes_only_visibility"] = (
            all(cmds.objExists(path) for path in all_offsets)
            and all(
                not (cmds.listConnections(
                    f"{path}.visibility", source=True, destination=False, plugs=True
                ) or [])
                for path in all_offsets
            )
            and all(visible(cmds, path) for path in all_offsets)
            and cmds.objExists(fk.root_path)
            and cmds.objExists(ik.root_path)
            and cmds.objExists(blend.settings_path)
        )

        cleanup_targets = (
            "|AdvPy_LegIKControls",
            "|AdvPy_LegFKControls",
            "|AdvPy_LegMechanisms",
            "|AdvPy_LegSettings",
            "|Root_M",
            container,
            marker,
        )
        existing = [path for path in cleanup_targets if cmds.objExists(path)]
        if existing:
            cmds.delete(existing)
        remaining = cmds.ls("Root_M", "FitSkeleton", "AdvPy_Leg*", marker, long=True) or []
        checks["cleanup"] = not remaining
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "body_leg_fk_ik_mode_visibility",
            **checks,
            "remaining_nodes": remaining,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "status": "passed" if passed else "failed",
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0 if passed else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
