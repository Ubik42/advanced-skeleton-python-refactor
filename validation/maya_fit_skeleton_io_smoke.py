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


def max_vector_error(left, right):
    return max(abs(a - b) for a, b in zip(left, right))


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaFitJointHost
        from adv_py.application import (
            BuildSyntheticBodyWithHandSourceFit,
            CreateFitSkeleton,
            EditFitJointMetadata,
            ExportFitSkeleton,
            ImportFitSkeleton,
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
            name="FitSkeletonIoSelection",
            skipSelect=True,
        )
        host = MayaFitJointHost()

        with tempfile.TemporaryDirectory(
            prefix="adv_py_fit_io_"
        ) as directory:
            directory_path = Path(directory)
            document_path = directory_path / "五指角色.fit.json"
            corrupt_path = directory_path / "损坏.fit.json"

            source_container = CreateFitSkeleton(host).apply(
                "FitSkeleton",
                display_radius=3.0,
            ).state.path
            BuildSyntheticBodyWithHandSourceFit(host).apply(source_container)
            source_orientation = host.capture_fit_orientation(source_container)
            source_root = next(
                node.path
                for node in source_orientation.hierarchy.joints
                if node.short_name == "Root"
            )
            EditFitJointMetadata(host).apply(
                [source_root],
                FitJointPatch.from_values(global_translate=True),
            )
            cmds.setAttr(f"{source_container}.visGap", 0.35)
            cmds.setAttr(f"{source_container}.visGeo", True)
            source_orientation = host.capture_fit_orientation(source_container)
            source_by_name = {
                node.short_name: (
                    node.world_position,
                    next(
                        state.world_axes
                        for state in source_orientation.joints
                        if state.joint == node.path
                    ),
                )
                for node in source_orientation.hierarchy.joints
            }

            cmds.select(marker, replace=True)
            cmds.file(modified=False)
            export_preview = ExportFitSkeleton(host).plan(
                document_path,
                source_container,
            )
            export_preview_read_only = not bool(
                cmds.file(query=True, modified=True)
            )
            exported = ExportFitSkeleton(host).apply(
                document_path,
                source_container,
            )
            export_read_only = not bool(cmds.file(query=True, modified=True))
            saved_text = document_path.read_text(encoding="utf-8")
            no_temporary_file = not any(
                path.name.endswith(".tmp")
                for path in directory_path.iterdir()
            )
            overwrite_refused = False
            try:
                ExportFitSkeleton(host).apply(
                    document_path,
                    source_container,
                )
            except ValueError:
                overwrite_refused = True

            cmds.delete(source_container)
            target_container = CreateFitSkeleton(host).apply(
                "FitSkeletonImported",
                display_radius=3.0,
            ).state.path
            target_before = host.read_fit_skeleton_settings(target_container)
            cmds.flushUndo()
            cmds.undoInfo(stateWithoutFlush=True)
            cmds.select(marker, replace=True)
            cmds.file(modified=False)

            import_preview = ImportFitSkeleton(host).plan(
                document_path,
                target_container,
            )
            import_preview_read_only = not bool(
                cmds.file(query=True, modified=True)
            )
            imported = ImportFitSkeleton(host).apply(
                document_path,
                target_container,
            )
            target_orientation = host.capture_fit_orientation(target_container)
            target_by_name = {
                node.short_name: (
                    node.world_position,
                    next(
                        state.world_axes
                        for state in target_orientation.joints
                        if state.joint == node.path
                    ),
                )
                for node in target_orientation.hierarchy.joints
            }
            max_position_error = max(
                max_vector_error(
                    source_by_name[name][0],
                    target_by_name[name][0],
                )
                for name in source_by_name
            )
            max_axis_error = max(
                max_vector_error(source_axis, target_axis)
                for name in source_by_name
                for source_axis, target_axis in zip(
                    source_by_name[name][1],
                    target_by_name[name][1],
                )
            )
            imported_root = next(
                node.path
                for node in target_orientation.hierarchy.joints
                if node.short_name == "Root"
            )
            imported_root_metadata = host.read_fit_joint_metadata(imported_root)
            settings_after = host.read_fit_skeleton_settings(target_container)
            labels_restored = all(
                host.read_joint_label(node.path) is not None
                for node in target_orientation.hierarchy.joints
            )
            selection_preserved = (cmds.ls(selection=True) or []) == [marker]

            repeat_refused = False
            try:
                ImportFitSkeleton(host).apply(
                    document_path,
                    target_container,
                )
            except ValueError:
                repeat_refused = True
            repeat_preserved_tree = len(
                host.capture_fit_hierarchy(target_container).joints
            ) == 38

            cmds.undo()
            undo_hierarchy = host.capture_fit_hierarchy(target_container)
            settings_after_undo = host.read_fit_skeleton_settings(target_container)
            undo_restored_empty_target = not undo_hierarchy.joints
            undo_restored_settings = (
                settings_after_undo == target_before
            )
            file_survived_undo = document_path.read_text(
                encoding="utf-8"
            ) == saved_text

            tampered = json.loads(saved_text)
            tampered["joints"][0]["local_position"][0] = 1.0
            corrupt_path.write_text(
                json.dumps(tampered, ensure_ascii=False),
                encoding="utf-8",
            )
            cmds.file(modified=False)
            corrupt_refused = False
            try:
                ImportFitSkeleton(host).plan(corrupt_path, target_container)
            except ValueError:
                corrupt_refused = True
            corrupt_read_only = not bool(cmds.file(query=True, modified=True))

            driver = cmds.createNode(
                "multiplyDivide",
                name="FitIoSettingDriver",
                skipSelect=True,
            )
            cmds.connectAttr(
                f"{driver}.outputX",
                f"{target_container}.visGap",
                force=True,
            )
            setting_source_before = tuple(
                cmds.listConnections(
                    f"{target_container}.visGap",
                    source=True,
                    destination=False,
                    plugs=True,
                )
                or []
            )
            cmds.file(modified=False)
            driven_preview = ImportFitSkeleton(host).plan(
                document_path,
                target_container,
            )
            driven_refused = False
            try:
                ImportFitSkeleton(host).apply(
                    document_path,
                    target_container,
                )
            except ValueError:
                driven_refused = True
            setting_source_after = tuple(
                cmds.listConnections(
                    f"{target_container}.visGap",
                    source=True,
                    destination=False,
                    plugs=True,
                )
                or []
            )
            driven_refusal_read_only = not bool(
                cmds.file(query=True, modified=True)
            )

            checks = {
                "export_preview_read_only": export_preview_read_only,
                "export_read_only_and_atomic": (
                    export_read_only
                    and no_temporary_file
                    and exported.bytes_written == len(
                        saved_text.encode("utf-8")
                    )
                    and export_preview.document == exported.plan.document
                ),
                "document_has_no_maya_paths_or_script_fields": (
                    "|FitSkeleton" not in saved_text
                    and "objects_skin" not in saved_text
                    and "pre_rebuild_script" not in saved_text
                    and "post_rebuild_script" not in saved_text
                ),
                "overwrite_refused_without_scene_change": (
                    overwrite_refused and export_read_only
                ),
                "import_preview_ready_and_read_only": (
                    import_preview.ready
                    and import_preview_read_only
                    and import_preview.joint_count == 38
                    and import_preview.changed_setting_count == 2
                ),
                "round_trip_document_matches": (
                    fit_skeleton_documents_match(
                        imported.verified_document,
                        exported.plan.document,
                    )
                ),
                "positions_and_behavior_axes_restored": (
                    set(source_by_name) == set(target_by_name)
                    and max_position_error <= 1e-5
                    and max_axis_error <= 1e-5
                ),
                "settings_metadata_and_labels_restored": (
                    settings_after.value(FitSkeletonField.VIS_GAP) == 0.35
                    and settings_after.value(
                        FitSkeletonField.VIS_GEOMETRY
                    )
                    is True
                    and FitJointField.GLOBAL_TRANSLATE
                    in imported_root_metadata.present_fields
                    and imported_root_metadata.global_translate is True
                    and labels_restored
                ),
                "selection_preserved": selection_preserved,
                "nonempty_repeat_refused_without_changes": (
                    repeat_refused and repeat_preserved_tree
                ),
                "one_undo_restored_empty_target_and_settings": (
                    undo_restored_empty_target
                    and undo_restored_settings
                    and file_survived_undo
                    and cmds.objExists(target_container)
                ),
                "tampered_file_refused_before_scene_change": (
                    corrupt_refused and corrupt_read_only
                ),
                "driven_setting_refused_without_disconnect": (
                    not driven_preview.ready
                    and driven_refused
                    and driven_refusal_read_only
                    and setting_source_after == setting_source_before
                    and not host.capture_fit_hierarchy(
                        target_container
                    ).joints
                ),
            }

            cmds.delete(target_container, driver, marker)

        checks["temporary_directory_removed"] = not directory_path.exists()
        checks["scene_cleanup"] = not (
            cmds.ls(
                "FitSkeleton",
                "FitSkeletonImported",
                "FitIoSettingDriver",
                "FitSkeletonIoSelection",
                long=True,
            )
            or []
        )
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "fit_skeleton_document_io",
            **checks,
            "joint_count": 38,
            "portable_setting_change_count": 2,
            "max_world_position_error": max_position_error,
            "max_world_axis_error": max_axis_error,
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
