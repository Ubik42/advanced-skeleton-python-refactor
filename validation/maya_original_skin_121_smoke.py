"""Rebuild the public sam rig and copy its 121-influence Skin in one scene."""
from __future__ import annotations

from pathlib import Path
from array import array
from dataclasses import replace
import json
import sys
import tempfile
from hashlib import sha256

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _skin_api(cmds, skin):
    from maya.api import OpenMaya as om
    from maya.api import OpenMayaAnim as oma
    shapes = cmds.skinCluster(skin, query=True, geometry=True) or []
    if len(shapes) != 1:
        raise ValueError("原版 Skin 需要唯一网格")
    shape = (cmds.ls(shapes[0], long=True, type="mesh") or [])[0]
    selection = om.MSelectionList()
    selection.add(skin)
    skin_fn = oma.MFnSkinCluster(selection.getDependNode(0))
    selection = om.MSelectionList()
    selection.add(shape)
    dag = selection.getDagPath(0)
    count = int(cmds.polyEvaluate(shape, vertex=True))
    component_fn = om.MFnSingleIndexedComponent()
    component = component_fn.create(om.MFn.kMeshVertComponent)
    component_fn.addElements(range(count))
    names = [path.fullPathName().rsplit("|", 1)[-1]
             for path in skin_fn.influenceObjects()]
    if len(names) != len(set(names)):
        raise ValueError("Skin 影响关节名称不唯一")
    return skin_fn, dag, component, tuple(names), count


def _points(mesh):
    from maya.api import OpenMaya as om
    selection = om.MSelectionList()
    selection.add(mesh)
    dag = selection.getDagPath(0)
    if dag.apiType() == om.MFn.kTransform:
        dag.extendToShape()
    return tuple(tuple(float(v) for v in point)
                 for point in om.MFnMesh(dag).getPoints(om.MSpace.kWorld))


def main(scene: Path, volume_file: Path, angle_file: Path,
         axial_file: Path, report: Path) -> int:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters.maya_body import MayaBodyBuildHost
        from adv_py.adapters.maya_axial_part import MayaAxialPartHost
        from adv_py.adapters.maya_finger_mid import MayaFingerMidHost
        from adv_py.adapters.maya_limb_part import MayaLimbPartHost
        from adv_py.adapters.maya_root_volume import MayaRootVolumeHost
        from adv_py.adapters.maya_sdk_volume import MayaSdkVolumeHost
        from adv_py.adapters.maya_volume_half_parent import MayaVolumeHalfParentHost
        from adv_py.adapters.maya_angle_sampler import MayaAngleSamplerHost
        from adv_py.adapters.maya_dense_skin import MayaDenseSkinHost
        from adv_py.application.registered_body_build import BuildRegisteredBodyCharacter
        from adv_py.application.axial_part_deform import BuildAxialPartDeform
        from adv_py.application.finger_mid_deform import BuildFingerMidDeform
        from adv_py.application.limb_part_deform import BuildLimbPartDeform
        from adv_py.application.root_volume_deform import BuildRootVolumeDeform
        from adv_py.application.chest_volume_deform import BuildChestVolumeDeform
        from adv_py.application.knee_volume_deform import BuildKneeVolumeDeform
        from adv_py.application.volume_half_parent import BuildVolumeHalfParents
        from adv_py.application.bend_volume_deform import BuildBendVolumeDeform
        from adv_py.application.angle_sampler_deform import BuildAngleSamplers
        from adv_py.application.angle_volume_deform import BuildAngleVolumeDeform
        from adv_py.application.skin_bind import BindSkin
        from adv_py.application.dense_skin_transfer import TransferDenseSkinWeights

        volume = json.loads(volume_file.read_text(encoding="utf-8"))
        angle = json.loads(angle_file.read_text(encoding="utf-8"))
        axial = json.loads(axial_file.read_text(encoding="utf-8"))
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        for side in ("R", "L"):
            cmds.setAttr(f"FKIKLeg_{side}.FKIKBlend", 0.0)
        skin = (cmds.ls(type="skinCluster") or [])[0]
        source_fn, source_dag, source_component, source_names, count = (
            _skin_api(cmds, skin))
        source_dense = MayaDenseSkinHost().capture_dense_skin(skin)
        source_influence_count = len(source_dense.influence_names)
        if source_dense.influence_names != source_names:
            raise RuntimeError("原版 Skin API 影响关节顺序漂移")
        source_mesh = (cmds.listRelatives(source_dag.fullPathName(),
            parent=True, fullPath=True) or [])[0]
        source_points = _points(source_mesh)
        controls = {
            "root_y20": ("FKRoot_M.rotateY", "AdvPy_TorsoRoot_MFK.rotateY", 20.0),
            "neck_y20": ("FKNeck_M.rotateY", "AdvPy_TorsoNeck_MFK.rotateY", 20.0),
            "elbow_r_z80": ("FKElbow_R.rotateZ", "AdvPy_ElbowFK_R.rotateZ", 80.0),
            "hip_r_y30": ("FKHip_R.rotateY", "AdvPy_HipFK_R.rotateY", 30.0),
        }
        source_pose_points = {}
        source_pose_matrices = {}
        for label, (source_plug, _, value) in controls.items():
            cmds.setAttr(source_plug, value)
            source_pose_points[label] = _points(source_mesh)
            source_pose_matrices[label] = {name: tuple(cmds.xform(
                name, query=True, worldSpace=True, matrix=True))
                for name in source_names}
            cmds.setAttr(source_plug, 0.0)
        source_uv_sets = tuple(cmds.polyUVSet(source_mesh, query=True,
                                             allUVSets=True) or [])
        source_shaders = tuple(sorted(set(cmds.listConnections(
            source_dag.fullPathName(), type="shadingEngine") or [])))
        max_influences = int(cmds.getAttr(skin + ".maxInfluences"))
        maintain = bool(cmds.getAttr(skin + ".maintainMaxInfluences"))
        cmds.undoInfo(openChunk=True,
                      chunkName="原版角色 121 关节网格和权重迁移")
        duplicate = cmds.duplicate(source_mesh, returnRootsOnly=True,
                                   renameChildren=True)[0]
        if cmds.listRelatives(duplicate, parent=True):
            duplicate = cmds.parent(duplicate, world=True)[0]
        duplicate = cmds.rename(duplicate, "AdvPy_SamSourceMesh")
        cmds.delete(duplicate, constructionHistory=True)
        copy_points = _points(duplicate)
        copy_error = max(abs(a - b) for source, target in zip(
            source_points, copy_points) for a, b in zip(source, target))
        copy_uv_sets = tuple(cmds.polyUVSet(duplicate, query=True,
                                           allUVSets=True) or [])
        copy_shape = (cmds.listRelatives(duplicate, shapes=True,
                                        noIntermediate=True, fullPath=True,
                                        type="mesh") or [])[0]
        copy_shaders = tuple(sorted(set(cmds.listConnections(
            copy_shape, type="shadingEngine") or [])))
        fits = cmds.ls("FitSkeleton", type="transform", long=True) or []
        if len(fits) != 1:
            raise ValueError("原版场景需要唯一 FitSkeleton")
        fit_parent = (cmds.listRelatives(fits[0], parent=True,
                                        fullPath=True) or [""])[0]
        cmds.delete(tuple(path for path in (cmds.listRelatives(
            fit_parent, children=True, fullPath=True) or ()) if path != fits[0]))
        BuildRegisteredBodyCharacter(MayaBodyBuildHost()).apply(
            fits[0], infer_missing_labels=True)
        BuildAxialPartDeform(MayaAxialPartHost()).apply(guide=axial)
        BuildFingerMidDeform(MayaFingerMidHost()).apply()
        BuildLimbPartDeform(MayaLimbPartHost()).apply()
        BuildRootVolumeDeform(MayaRootVolumeHost()).apply(volume)
        BuildChestVolumeDeform(MayaSdkVolumeHost()).apply(volume)
        BuildKneeVolumeDeform(MayaSdkVolumeHost()).apply(volume)
        BuildVolumeHalfParents(MayaVolumeHalfParentHost()).apply(volume)
        BuildBendVolumeDeform(MayaSdkVolumeHost()).apply(volume)
        BuildAngleSamplers(MayaAngleSamplerHost()).apply(angle)
        BuildAngleVolumeDeform(MayaSdkVolumeHost()).apply(volume)
        paths = {name: (cmds.ls(name, type="joint", long=True) or [])
                 for name in source_names}
        if len(paths) != 121 or any(len(value) != 1 for value in paths.values()):
            raise AssertionError("原版 121 影响关节未全部重建")
        target_skin = "AdvPy_SamSkin"
        try:
            BindSkin(MayaBodyBuildHost()).apply(
                (cmds.ls(duplicate, type="transform", long=True) or [])[0],
                tuple(paths[name][0] for name in source_names),
                skin_name=target_skin, maximum_influences=max_influences,
                maintain_maximum_influences=False)
            transfer = TransferDenseSkinWeights(MayaDenseSkinHost()).apply(
                source_dense, target_skin)
            target_fn, target_dag, target_component, target_names, target_count = (
                _skin_api(cmds, target_skin))
            dense = memoryview(transfer.target_after.values).cast("d")
            cmds.setAttr(target_skin + ".maintainMaxInfluences", maintain)
        finally:
            cmds.undoInfo(closeChunk=True)
        result_weights, result_count = target_fn.getWeights(
            target_dag, target_component)
        weight_error = max(abs(float(a) - float(b)) for a, b in zip(
            dense, result_weights))
        result_points = _points(duplicate)
        point_error = max(abs(a - b) for source, target in zip(
            source_points, result_points) for a, b in zip(source, target))
        cmds.undo()
        undo_removed_skin = not cmds.objExists(target_skin)
        undo_removed_copy = not cmds.objExists("AdvPy_SamSourceMesh")
        undo_restored_source = (
            cmds.objExists(skin)
            and MayaDenseSkinHost().capture_dense_skin(skin) == source_dense)
        cmds.redo()
        redo_fn, redo_dag, redo_component, _, _ = _skin_api(cmds, target_skin)
        redo_weights, _ = redo_fn.getWeights(redo_dag, redo_component)
        redo_weight_error = max(abs(float(a) - float(b)) for a, b in zip(
            dense, redo_weights))
        after_redo = MayaDenseSkinHost().capture_dense_skin(target_skin)
        wrong_names = replace(source_dense, influence_names=(
            "MissingInfluence", *source_dense.influence_names[1:]))
        try:
            TransferDenseSkinWeights(MayaDenseSkinHost()).apply(
                wrong_names, target_skin)
        except ValueError:
            mismatch_rejected = (MayaDenseSkinHost().capture_dense_skin(
                target_skin) == after_redo)
        else:
            mismatch_rejected = False
        mutated = array("d")
        mutated.frombytes(after_redo.values)
        active = max(range(len(target_names)), key=lambda index: mutated[index])
        other = (active + 1) % len(target_names)
        mutated[active], mutated[other] = 0.5, 0.5
        fault_source = replace(after_redo, skin_name="FaultSource",
                               values=mutated.tobytes())
        class FaultyDenseHost(MayaDenseSkinHost):
            def apply_dense_skin(self, data):
                super().apply_dense_skin(data)
                raise RuntimeError("injected bulk write fault")
        try:
            TransferDenseSkinWeights(FaultyDenseHost()).apply(
                fault_source, target_skin)
        except RuntimeError as exc:
            fault_rolled_back = (str(exc) == "injected bulk write fault"
                and MayaDenseSkinHost().capture_dense_skin(target_skin)
                    == after_redo)
        else:
            fault_rolled_back = False
        pose_errors = {}
        pose_joint_worst = {}
        pose_joint_frames = {}
        diagnostic_names = ("Root_M", "Spine1_M", "Chest_M", "Neck_M",
            "Head_M", "Hip_R", "Hip_L", "Knee_R", "Knee_L",
            "Ankle_R", "Ankle_L", "Toes_R", "Toes_L")
        for label, (_, target_plug, value) in controls.items():
            cmds.setAttr(target_plug, value)
            posed = _points(duplicate)
            pose_errors[label] = max(abs(a - b) for source, target in zip(
                source_pose_points[label], posed)
                for a, b in zip(source, target))
            matrix_errors = {name: max(abs(a - b) for a, b in zip(
                source_pose_matrices[label][name], cmds.xform(
                    paths[name][0], query=True, worldSpace=True, matrix=True)))
                for name in source_names}
            pose_joint_worst[label] = sorted(matrix_errors.items(),
                key=lambda row: row[1], reverse=True)[:15]
            if label in ("root_y20", "neck_y20"):
                pose_joint_frames[label] = {name: {
                    "source": source_pose_matrices[label][name],
                    "target": tuple(cmds.xform(paths[name][0], query=True,
                        worldSpace=True, matrix=True)),
                } for name in diagnostic_names}
            cmds.setAttr(target_plug, 0.0)
        saved = report.with_suffix(".mb").resolve()
        report.parent.mkdir(parents=True, exist_ok=True)
        cmds.file(rename=str(saved))
        cmds.file(save=True, type="mayaBinary", force=True)
        cmds.file(str(saved), open=True, force=True,
                  executeScriptNodes=False)
        reopen_fn, reopen_dag, reopen_component, _, _ = _skin_api(
            cmds, target_skin)
        reopen_weights, _ = reopen_fn.getWeights(
            reopen_dag, reopen_component)
        reopen_weight_error = max(abs(float(a) - float(b))
            for a, b in zip(dense, reopen_weights))
        data = {"source": scene.name, "vertex_count": count,
                "source_influence_count": source_influence_count,
                "target_influence_count": result_count,
                "target_vertex_count": target_count,
                "source_max_influences": max_influences,
                "source_maintain_max_influences": maintain,
                "copy_world_point_error": copy_error,
                "rest_world_point_error": point_error,
                "maximum_weight_error": weight_error,
                "pose_world_point_errors": pose_errors,
                "pose_joint_worst": pose_joint_worst,
                "pose_joint_frames": pose_joint_frames,
                "undo_removed_skin": undo_removed_skin,
                "undo_removed_copy": undo_removed_copy,
                "undo_restored_source_skin": undo_restored_source,
                "redo_weight_error": redo_weight_error,
                "mismatch_rejected": mismatch_rejected,
                "fault_rolled_back": fault_rolled_back,
                "reopen_weight_error": reopen_weight_error,
                "source_uv_sets": source_uv_sets,
                "target_uv_sets": copy_uv_sets,
                "source_shading_engines": source_shaders,
                "target_shading_engines": copy_shaders,
                "saved_scene": saved.name,
                "target_weight_sha256": sha256(
                    transfer.target_after.values).hexdigest()}
        report.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        if (count != 18151 or source_influence_count != 121
                or result_count != 121 or target_count != count
                or copy_error > 1e-5 or point_error > 1e-5
                or weight_error > 1e-6 or copy_uv_sets != source_uv_sets
                or copy_shaders != source_shaders
                or not all((undo_removed_skin, undo_removed_copy,
                            undo_restored_source, mismatch_rejected,
                            fault_rolled_back)) or redo_weight_error > 1e-6
                or reopen_weight_error > 1e-6):
            raise AssertionError(data)
        return 0
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2]),
                          Path(sys.argv[3]), Path(sys.argv[4]),
                          Path(sys.argv[5])))
