from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
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
        from adv_py.application import (
            BuildSyntheticBodyWithHandSourceFit,
            CreateAndImportFitSkeleton,
            CreateFitSkeleton,
            EditFitJointMetadata,
            ExportFitSkeleton,
        )
        from adv_py.core import (
            FitJointField,
            FitJointPatch,
            FitSkeletonField,
            fit_skeleton_documents_match,
        )

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="FitSkeletonCreateImportSelection",
            skipSelect=True,
        )
        host = MayaFitJointHost()

        with tempfile.TemporaryDirectory(
            prefix="adv_py_fit_create_import_"
        ) as directory:
            directory_path = Path(directory)
            document_path = directory_path / "新建五指角色.fit.json"

            source_container = CreateFitSkeleton(host).apply(
                "FitSkeletonSource",
                display_radius=3.0,
            ).state.path
            BuildSyntheticBodyWithHandSourceFit(host).apply(source_container)
            source_snapshot = host.capture_fit_orientation(source_container)
            source_root = next(
                node.path
                for node in source_snapshot.hierarchy.joints
                if node.short_name == "Root"
            )
            EditFitJointMetadata(host).apply(
                [source_root],
                FitJointPatch.from_values(global_translate=True),
            )
            cmds.setAttr(f"{source_container}.visGap", 0.35)
            cmds.setAttr(f"{source_container}.visGeo", True)
            exported = ExportFitSkeleton(host).apply(
                document_path,
                source_container,
            )
            cmds.delete(source_container)

            cmds.flushUndo()
            cmds.undoInfo(stateWithoutFlush=True)
            cmds.select(marker, replace=True)
            cmds.file(modified=False)

            use_case = CreateAndImportFitSkeleton(host)
            preview = use_case.plan(
                document_path,
                "FitSkeleton",
                display_radius=4.0,
            )
            preview_read_only = not bool(cmds.file(query=True, modified=True))
            imported = use_case.apply(
                document_path,
                "FitSkeleton",
                display_radius=4.0,
            )
            target = imported.verified.container.path
            target_settings = host.read_fit_skeleton_settings(target)
            target_snapshot = host.capture_fit_orientation(target)
            target_root = next(
                node.path
                for node in target_snapshot.hierarchy.joints
                if node.short_name == "Root"
            )
            root_metadata = host.read_fit_joint_metadata(target_root)
            selection_preserved = (cmds.ls(selection=True) or []) == [marker]

            cmds.undo()
            undo_removed_container = not cmds.objExists(target)
            file_survived_undo = document_path.is_file()
            marker_survived_undo = cmds.objExists(marker)

            collision = cmds.createNode(
                "transform",
                name="Root",
                skipSelect=True,
            )
            cmds.select(marker, replace=True)
            cmds.file(modified=False)
            collision_preview = use_case.plan(document_path)
            collision_refused = False
            try:
                use_case.apply(document_path)
            except ValueError:
                collision_refused = True
            collision_read_only = not bool(cmds.file(query=True, modified=True))
            collision_preserved = cmds.objExists(collision)
            cmds.delete(collision)

            cmds.upAxis(axis="y", rotateView=False)
            cmds.file(modified=False)
            axis_preview = use_case.plan(document_path)
            axis_refused = False
            try:
                use_case.apply(document_path)
            except ValueError:
                axis_refused = True
            axis_read_only = not bool(cmds.file(query=True, modified=True))
            cmds.upAxis(axis="z", rotateView=False)

            checks = {
                "preview_ready_and_read_only": (
                    preview.ready
                    and preview_read_only
                    and preview.joint_count == 38
                ),
                "created_container_settings_and_full_document": (
                    target == "|FitSkeleton"
                    and len(imported.joint_paths) == 38
                    and len(target_snapshot.hierarchy.joints) == 38
                    and fit_skeleton_documents_match(
                        imported.verified_document,
                        exported.plan.document,
                    )
                    and target_settings.value(FitSkeletonField.VIS_GAP) == 0.35
                    and target_settings.value(FitSkeletonField.VIS_GEOMETRY)
                    is True
                    and FitJointField.GLOBAL_TRANSLATE
                    in root_metadata.present_fields
                    and root_metadata.global_translate is True
                ),
                "custom_display_radius_verified": (
                    abs(imported.verified.container.bounding_size[0] - 8.0)
                    <= 1e-5
                    and abs(
                        imported.verified.container.bounding_size[1] - 8.0
                    )
                    <= 1e-5
                    and abs(imported.verified.container.bounding_size[2])
                    <= 1e-5
                ),
                "selection_preserved": selection_preserved,
                "one_undo_removed_container_and_tree": (
                    undo_removed_container
                    and file_survived_undo
                    and marker_survived_undo
                ),
                "global_name_collision_refused_read_only": (
                    not collision_preview.ready
                    and collision_refused
                    and collision_read_only
                    and not cmds.objExists("FitSkeleton")
                    and collision_preserved
                ),
                "scene_up_axis_mismatch_refused_read_only": (
                    not axis_preview.ready
                    and axis_refused
                    and axis_read_only
                    and not cmds.objExists("FitSkeleton")
                ),
            }

            cmds.delete(marker)

        checks["temporary_directory_removed"] = not directory_path.exists()
        checks["scene_cleanup"] = not (
            cmds.ls(
                "FitSkeleton",
                "FitSkeletonSource",
                "FitSkeletonCreateImportSelection",
                long=True,
            )
            or []
        )
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "fit_skeleton_create_and_import",
            **checks,
            "joint_count": 38,
            "setting_count": len(target_settings.settings),
            "display_radius": 4.0,
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
