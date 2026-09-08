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
            CreateFitSkeleton,
            ExportFitSkeleton,
            MergeFitSkeleton,
        )
        from adv_py.core import (
            BODY_HAND_DIGITS,
            fit_skeleton_documents_match,
        )

        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.upAxis(axis="z", rotateView=False)
        marker = cmds.createNode(
            "transform",
            name="FitSkeletonMergeSelection",
            skipSelect=True,
        )
        host = MayaFitJointHost()

        with tempfile.TemporaryDirectory(
            prefix="adv_py_fit_merge_"
        ) as directory:
            directory_path = Path(directory)
            document_path = directory_path / "完整五指角色.fit.json"

            container = CreateFitSkeleton(host).apply(
                "FitSkeleton",
                display_radius=3.0,
            ).state.path
            BuildSyntheticBodyWithHandSourceFit(host).apply(container)
            exported = ExportFitSkeleton(host).apply(
                document_path,
                container,
            )
            full_snapshot = host.capture_fit_orientation(container)
            full_paths = {
                node.short_name: node.path
                for node in full_snapshot.hierarchy.joints
            }
            finger_roots = tuple(
                full_paths[f"{digit.value}1"] for digit in BODY_HAND_DIGITS
            )
            cmds.delete(*finger_roots)

            base_snapshot = host.capture_fit_orientation(container)
            base_paths = {
                node.short_name: node.path
                for node in base_snapshot.hierarchy.joints
            }
            base_uuids = {
                name: (cmds.ls(path, uuid=True) or [None])[0]
                for name, path in base_paths.items()
            }
            cmds.flushUndo()
            cmds.undoInfo(stateWithoutFlush=True)
            cmds.select(marker, replace=True)
            cmds.file(modified=False)

            preview = MergeFitSkeleton(host).plan(
                document_path,
                container,
            )
            preview_read_only = not bool(cmds.file(query=True, modified=True))
            merged = MergeFitSkeleton(host).apply(
                document_path,
                container,
            )
            merged_snapshot = host.capture_fit_orientation(container)
            merged_paths = {
                node.short_name: node.path
                for node in merged_snapshot.hierarchy.joints
            }
            existing_uuids_preserved = all(
                merged_paths.get(name) == path
                and (cmds.ls(path, uuid=True) or [None])[0]
                == base_uuids[name]
                for name, path in base_paths.items()
            )
            selection_preserved = (cmds.ls(selection=True) or []) == [marker]
            undo_name_before_repeat = cmds.undoInfo(
                query=True,
                undoName=True,
            )
            repeated = MergeFitSkeleton(host).apply(
                document_path,
                container,
            )
            undo_name_after_repeat = cmds.undoInfo(
                query=True,
                undoName=True,
            )

            cmds.undo()
            undo_snapshot = host.capture_fit_orientation(container)
            undo_paths = {
                node.short_name: node.path
                for node in undo_snapshot.hierarchy.joints
            }
            undo_kept_existing = all(
                undo_paths.get(name) == path
                and (cmds.ls(path, uuid=True) or [None])[0]
                == base_uuids[name]
                for name, path in base_paths.items()
            )
            undo_removed_additions = len(undo_paths) == len(base_paths) == 18

            conflict_path = base_paths["Spine1"]
            original_position = tuple(
                float(value)
                for value in cmds.getAttr(f"{conflict_path}.translate")[0]
            )
            changed_position = (
                original_position[0],
                original_position[1],
                original_position[2] + 0.25,
            )
            cmds.setAttr(f"{conflict_path}.translate", *changed_position)
            cmds.file(modified=False)
            conflict_preview = MergeFitSkeleton(host).plan(
                document_path,
                container,
            )
            conflict_refused = False
            try:
                MergeFitSkeleton(host).apply(document_path, container)
            except ValueError:
                conflict_refused = True
            conflict_position_after = tuple(
                float(value)
                for value in cmds.getAttr(f"{conflict_path}.translate")[0]
            )
            conflict_read_only = not bool(cmds.file(query=True, modified=True))

            checks = {
                "preview_ready_and_read_only": (
                    preview.ready
                    and preview_read_only
                    and preview.added_joint_count == 20
                    and len(preview.current_document.joints) == 18
                ),
                "additive_union_matches_incoming_document": (
                    len(merged_snapshot.hierarchy.joints) == 38
                    and len(merged.joint_paths) == 20
                    and fit_skeleton_documents_match(
                        merged.verified_document,
                        exported.plan.document,
                    )
                ),
                "existing_joint_identity_preserved": existing_uuids_preserved,
                "selection_preserved": selection_preserved,
                "repeat_is_noop_without_new_undo": (
                    repeated.plan.added_joint_count == 0
                    and not repeated.joint_paths
                    and undo_name_after_repeat == undo_name_before_repeat
                ),
                "one_undo_removed_only_additions": (
                    undo_kept_existing and undo_removed_additions
                ),
                "shared_joint_conflict_refused_read_only": (
                    not conflict_preview.ready
                    and any(
                        issue.code == "joint_conflict"
                        for issue in conflict_preview.document_merge.issues
                    )
                    and conflict_refused
                    and conflict_position_after == changed_position
                    and conflict_read_only
                    and len(host.capture_fit_hierarchy(container).joints) == 18
                ),
                "source_file_survived_scene_undo": document_path.is_file(),
            }

            cmds.delete(container, marker)

        checks["temporary_directory_removed"] = not directory_path.exists()
        checks["scene_cleanup"] = not (
            cmds.ls(
                "FitSkeleton",
                "FitSkeletonMergeSelection",
                long=True,
            )
            or []
        )
        passed = all(checks.values())
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "slice": "fit_skeleton_additive_merge",
            **checks,
            "existing_joint_count": 18,
            "added_joint_count": 20,
            "merged_joint_count": 38,
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
