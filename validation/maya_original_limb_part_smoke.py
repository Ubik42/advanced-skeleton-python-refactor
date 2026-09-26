"""Compare rebuilt limb Part joints with the public sam scene."""
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
        from adv_py.adapters.maya_limb_part import MayaLimbPartHost
        from adv_py.application.registered_body_build import BuildRegisteredBodyCharacter
        from adv_py.application.limb_part_deform import BuildLimbPartDeform
        from adv_py.application.character_registry import ResolveBodyCharacter

        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        cmds.evaluationManager(mode="off")
        fits = cmds.ls("FitSkeleton", type="transform", long=True) or []
        if len(fits) != 1:
            raise ValueError("原版场景需要唯一 FitSkeleton")
        for side in ("R", "L"):
            cmds.setAttr(f"FKIKLeg_{side}.FKIKBlend", 0.0)
        segments = [(stem, side) for side in ("R", "L")
                    for stem in ("Shoulder", "Elbow", "Hip")]
        names = [f"{stem}Part{index}_{side}" for stem, side in segments
                 for index in (1, 2)]
        original_rest = {name: _matrix(cmds, name) for name in names}
        original_rotate_orders = {f"{stem}_{side}": (
            cmds.getAttr(f"FK{stem}_{side}.rotateOrder"),
            cmds.getAttr(f"FKX{stem}_{side}.rotateOrder"))
            for stem, side in segments}
        original_mode = {}
        original_leg_mode_source = cmds.listConnections(
            "FKIKBlendLeg_RUnitConversion.input", source=True,
            destination=False, plugs=True)
        for stem, side in segments:
            constraint = f"{stem}_{side}_orientConstraint1"
            aliases = cmds.orientConstraint(constraint, query=True,
                weightAliasList=True) or []
            original_mode[f"{stem}_{side}"] = {
                "control_visible": cmds.getAttr(f"FK{stem}_{side}.visibility"),
                "weights": [(alias, cmds.getAttr(constraint + "." + alias),
                             cmds.listConnections(constraint + "." + alias,
                                 source=True, destination=False, plugs=True))
                            for alias in aliases]}
        original_posed = {}
        pose_values = {"Y12": (0.0, 12.0, 0.0),
                       "Z12": (0.0, 0.0, 12.0),
                       "mixed": (12.0, 7.0, -5.0)}
        original_pose_cases = {}
        original_ik_rest = {}
        original_ik_fatness = {}
        original_ik_volume = {}
        original_ik_point_weights = {}
        original_ik_motion = {}
        original_ik_local = {}
        original_ik_twist = {}
        original_ik_body = {}
        original_ik_body_rest = {}
        original_ik_control_delta = {}
        original_ik_handle_delta = {}
        original_ik_driver_delta = {}
        original_custom_twist = {}
        original_fk_scale = {}
        original_fk_scale_local = {}
        original_fk_scale_end = {}
        original_fk_scale_start = {}
        original_fk_scale_end_local = {}
        original_fk_scale_up_twist = {}
        original_mixed_local = {}
        original_mixed_endpoints = {}
        original_mixed_fk_driver = {}
        original_pose_local = {}
        original_endpoints = {}
        original_endpoint_local = {}
        for stem, side in segments:
            control = f"FK{stem}_{side}"
            cmds.setAttr(control + ".rotateX", 12.0)
            for index in (1, 2):
                name = f"{stem}Part{index}_{side}"
                original_posed[name] = _matrix(cmds, name)
                original_pose_local[name] = {
                    "translate": cmds.getAttr(name + ".translate")[0],
                    "rotate": cmds.getAttr(name + ".rotate")[0],
                    "scale": cmds.getAttr(name + ".scale")[0]}
            end = {"Shoulder": "Elbow", "Elbow": "Wrist", "Hip": "Knee"}[stem]
            original_endpoints[f"{stem}_{side}"] = (
                _matrix(cmds, f"{stem}_{side}"),
                _matrix(cmds, f"{end}_{side}"))
            original_endpoint_local[f"{stem}_{side}"] = (
                cmds.getAttr(f"{stem}_{side}.rotate")[0],
                cmds.getAttr(f"{end}_{side}.rotate")[0])
            cmds.setAttr(control + ".rotateX", 0.0)
            for label, rotation in pose_values.items():
                cmds.setAttr(control + ".rotate", *rotation)
                for index in (1, 2):
                    name = f"{stem}Part{index}_{side}"
                    original_pose_cases[f"{name}:{label}"] = _matrix(cmds, name)
                    if label == "mixed":
                        original_mixed_local[name] = cmds.getAttr(name + ".rotate")[0]
                if label == "mixed":
                    original_mixed_endpoints[f"{stem}_{side}"] = (
                        _matrix(cmds, f"{stem}_{side}"),
                        _matrix(cmds, f"{end}_{side}"))
                    original_mixed_fk_driver[f"{stem}_{side}"] = _matrix(
                        cmds, f"FKX{stem}_{side}")
                cmds.setAttr(control + ".rotate", 0.0, 0.0, 0.0)
        for side in ("R", "L"):
            cmds.setAttr(f"FKIKArm_{side}.FKIKBlend", 10.0)
            cmds.setAttr(f"FKIKLeg_{side}.FKIKBlend", 10.0)
        for name in names:
            original_ik_rest[name] = _matrix(cmds, name)
        for side in ("R", "L"):
            for stem in ("Wrist", "Ankle"):
                node = f"{stem}_{side}_pointConstraint1"
                original_ik_point_weights[f"{stem}_{side}"] = [
                    (alias, cmds.getAttr(node + "." + alias)) for alias in
                    (cmds.pointConstraint(node, query=True,
                        weightAliasList=True) or [])]
        for stem, side in segments:
            end = {"Shoulder": "Elbow", "Elbow": "Wrist",
                   "Hip": "Knee"}[stem]
            original_ik_body_rest[f"{stem}_{side}"] = (
                _matrix(cmds, f"{stem}_{side}"),
                _matrix(cmds, f"{end}_{side}"))
        for side in ("R", "L"):
            for limb, stems in (("Arm", ("Shoulder", "Elbow")),
                                ("Leg", ("Hip",))):
                control = f"IK{limb}_{side}"
                position = cmds.xform(control, query=True, worldSpace=True,
                                      translation=True)
                handle = f"IKArmHandle_{side}" if limb == "Arm" else f"IKAnkleHandle_{side}"
                handle_before = cmds.xform(handle, query=True, worldSpace=True,
                                           translation=True)
                driver = f"IKXWrist_{side}" if limb == "Arm" else f"IKXAnkle_{side}"
                driver_before = cmds.xform(driver, query=True, worldSpace=True,
                                           translation=True)
                cmds.xform(control, worldSpace=True,
                           translation=(position[0], position[1] + 0.3,
                                        position[2]))
                moved = cmds.xform(control, query=True, worldSpace=True,
                                   translation=True)
                original_ik_control_delta[f"{limb}_{side}"] = tuple(
                    a-b for a,b in zip(moved, position))
                handle_after = cmds.xform(handle, query=True, worldSpace=True,
                                          translation=True)
                original_ik_handle_delta[f"{limb}_{side}"] = tuple(
                    a-b for a,b in zip(handle_after, handle_before))
                driver_after = cmds.xform(driver, query=True, worldSpace=True,
                                          translation=True)
                original_ik_driver_delta[f"{limb}_{side}"] = tuple(
                    a-b for a,b in zip(driver_after, driver_before))
                for stem in stems:
                    end = {"Shoulder": "Elbow", "Elbow": "Wrist",
                           "Hip": "Knee"}[stem]
                    original_ik_body[f"{stem}_{side}"] = (
                        _matrix(cmds, f"{stem}_{side}"),
                        _matrix(cmds, f"{end}_{side}"))
                    for index in (1, 2):
                        name = f"{stem}Part{index}_{side}"
                        original_ik_motion[name] = _matrix(cmds, name)
                        original_ik_local[name] = {
                            "rotate": cmds.getAttr(name + ".rotate")[0],
                            "translate": cmds.getAttr(name + ".translate")[0],
                            "addition": cmds.getAttr(name + ".twistAddition"),
                            "sum": cmds.getAttr("twistAddition" + name +
                                                ".output1D")}
                    original_ik_twist[f"{stem}_{side}"] = (
                        cmds.getAttr(f"{stem}QTETwist_{side}.outputRotateX"),
                        cmds.getAttr(f"twistAmountDivide{stem}Part1_{side}.input1"),
                        cmds.getAttr(f"twistAmountDivide{stem}Part1_{side}.output"))
                cmds.xform(control, worldSpace=True, translation=position)
        for stem, side in segments:
            limb = "Arm" if stem in ("Shoulder", "Elbow") else "Leg"
            attr = "Fatness2" if stem == "Elbow" else "Fatness1"
            plug = f"IK{limb}_{side}.{attr}"
            cmds.setAttr(plug, 0.35)
            for index in (1, 2):
                name = f"{stem}Part{index}_{side}"
                original_ik_fatness[name] = _matrix(cmds, name)
            cmds.setAttr(plug, 0.0)
        for side in ("R", "L"):
            for limb, start, stems in (
                    ("Arm", "Shoulder", ("Shoulder", "Elbow")),
                    ("Leg", "Hip", ("Hip",))):
                control = f"IK{limb}_{side}"
                anchor = cmds.xform(f"{start}_{side}", query=True,
                                    worldSpace=True, translation=True)
                initial = cmds.xform(control, query=True, worldSpace=True,
                                     translation=True)
                target = tuple(a + 1.2 * (b-a) for a,b in zip(anchor, initial))
                cmds.setAttr(control + ".stretchy", 10.0)
                cmds.xform(control, worldSpace=True, translation=target)
                for volume in (10.0, 5.0, 0.0):
                    cmds.setAttr(control + ".volume", volume)
                    for stem in stems:
                        for index in (1, 2):
                            name = f"{stem}Part{index}_{side}"
                            original_ik_volume[f"{name}:{int(volume)}"] = (
                                cmds.getAttr(name + ".scale")[0])
                cmds.setAttr(control + ".volume", 5.0)
                cmds.setAttr(control + ".Fatness1", 0.35)
                for index in (1, 2):
                    name = f"{start}Part{index}_{side}"
                    original_ik_volume[f"{name}:combo"] = cmds.getAttr(
                        name + ".scale")[0]
                cmds.setAttr(control + ".Fatness1", 0.0)
                cmds.xform(control, worldSpace=True, translation=initial)
                cmds.setAttr(control + ".volume", 10.0)
                cmds.setAttr(control + ".stretchy", 0.0)
        for side in ("R", "L"):
            cmds.setAttr(f"FKIKArm_{side}.FKIKBlend", 0.0)
            cmds.setAttr(f"FKIKLeg_{side}.FKIKBlend", 0.0)
        for stem, side in segments:
            control = f"FK{stem}_{side}"
            first, second = (f"{stem}Part{index}_{side}" for index in (1, 2))
            for name, amount, addition in ((first, 0.2, 5.0),
                                           (second, 0.8, -3.0)):
                cmds.setAttr(name + ".twistAmount", amount)
                cmds.setAttr(name + ".twistAddition", addition)
            cmds.setAttr(control + ".rotateX", 12.0)
            original_custom_twist[first] = _matrix(cmds, first)
            original_custom_twist[second] = _matrix(cmds, second)
            cmds.setAttr(control + ".rotateX", 0.0)
            for name, amount in ((first, 1.0 / 3.0),
                                 (second, 2.0 / 3.0)):
                cmds.setAttr(name + ".twistAmount", amount)
                cmds.setAttr(name + ".twistAddition", 0.0)
            cmds.setAttr(control + ".scale", 1.2, 0.8, 1.1)
            original_fk_scale[first] = _matrix(cmds, first)
            original_fk_scale[second] = _matrix(cmds, second)
            original_fk_scale_local[first] = cmds.getAttr(first + ".scale")[0]
            original_fk_scale_local[second] = cmds.getAttr(second + ".scale")[0]
            end = {"Shoulder": "Elbow", "Elbow": "Wrist", "Hip": "Knee"}[stem]
            original_fk_scale_end[f"{stem}_{side}"] = _matrix(cmds, f"{end}_{side}")
            original_fk_scale_start[f"{stem}_{side}"] = _matrix(cmds, f"{stem}_{side}")
            original_fk_scale_end_local[f"{stem}_{side}"] = cmds.getAttr(
                f"{end}_{side}.translate")[0]
            if stem in ("Elbow", "Hip"):
                original_fk_scale_up_twist[f"{stem}_{side}"] = cmds.getAttr(
                    f"{end}QTETwist_{side}.outputRotateX")
            cmds.setAttr(control + ".scale", 1.0, 1.0, 1.0)
        rig_root = (cmds.listRelatives(fits[0], parent=True, fullPath=True)
                    or [""])[0]
        cmds.delete(tuple(path for path in (cmds.listRelatives(
            rig_root, children=True, fullPath=True) or ()) if path != fits[0]))
        built = BuildRegisteredBodyCharacter(MayaBodyBuildHost()).apply(
            fits[0], infer_missing_labels=True)
        class FaultyHost(MayaLimbPartHost):
            def __init__(self):
                super().__init__()
                self.created = 0

            def create_limb_part_segment(self, spec):
                super().create_limb_part_segment(spec)
                self.created += 1
                if self.created == 3:
                    raise RuntimeError("injected limb Part failure")

        fault_raised = False
        try:
            BuildLimbPartDeform(FaultyHost()).apply()
        except RuntimeError as exc:
            fault_raised = str(exc) == "injected limb Part failure"
        fault_rolled_back = (fault_raised
            and not cmds.objExists("ShoulderPart1_R")
            and not cmds.objExists("ElbowPart1_R")
            and not cmds.objExists("AdvPy_ArmIK_R.Fatness1")
            and not cmds.objExists("AdvPy_ArmIK_R.Fatness2"))
        specs = BuildLimbPartDeform(MayaLimbPartHost()).apply()
        rest_errors = {name: max(abs(a-b) for a, b in zip(original_rest[name],
            _matrix(cmds, path))) for spec in specs for name, path in
            ((spec.part1_name, spec.part1), (spec.part2_name, spec.part2))}
        data = {"source": scene.name, "body_count": len(built.registration.body),
                "part_count": len(rest_errors), "rest_errors": rest_errors,
                "maximum_rest_error": max(rest_errors.values()),
                "original_mode": original_mode,
                "original_leg_mode_source": original_leg_mode_source,
                "fault_rolled_back": fault_rolled_back}
        data["original_ik_point_weights"] = original_ik_point_weights
        cmds.undo()
        data["undo_removed_parts"] = all(not cmds.objExists(spec.part1)
                                          for spec in specs)
        data["undo_removed_fatness"] = all(not cmds.objExists(
            spec.fatness_control + "." + spec.fatness_attribute)
            for spec in specs)
        cmds.redo()
        data["redo_restored_parts"] = all(cmds.objExists(spec.part2)
                                          for spec in specs)
        data["redo_restored_fatness"] = all(cmds.objExists(
            spec.fatness_control + "." + spec.fatness_attribute)
            for spec in specs)
        controls = tuple(built.rig.arm.fk_controls.controls) + tuple(
            built.rig.leg.fk_controls.controls)
        data["rotate_orders"] = {f"{spec.stem}_{spec.side}": {
            "original": original_rotate_orders[f"{spec.stem}_{spec.side}"],
            "new": (cmds.getAttr(next(item.control_path for item in controls
                if item.control_path.rsplit("|", 1)[-1] ==
                   f"AdvPy_{spec.stem}FK_{spec.side}") + ".rotateOrder"),
                cmds.getAttr(next(item.driven_joint for item in controls
                if item.control_path.rsplit("|", 1)[-1] ==
                   f"AdvPy_{spec.stem}FK_{spec.side}") + ".rotateOrder"))}
            for spec in specs}
        data["fk_control_driven"] = {item.control_path.rsplit("|", 1)[-1]:
            item.driven_joint.rsplit("|", 1)[-1] for item in controls}
        pose_errors = {}
        pose_case_errors = {}
        mixed_local = {}
        mixed_endpoint_errors = {}
        mixed_fk_driver_errors = {}
        endpoint_errors = {}
        endpoint_local = {}
        pose_local = {}
        for spec in specs:
            control = next(item.control_path for item in controls
                if item.control_path.rsplit("|", 1)[-1] ==
                   f"AdvPy_{spec.stem}FK_{spec.side}")
            cmds.setAttr(control + ".rotateX", 12.0)
            orig_start, orig_end = original_endpoints[f"{spec.stem}_{spec.side}"]
            endpoint_errors[f"{spec.stem}_{spec.side}"] = (
                max(abs(a-b) for a, b in zip(orig_start, _matrix(cmds, spec.start))),
                max(abs(a-b) for a, b in zip(orig_end, _matrix(cmds, spec.end))))
            endpoint_local[f"{spec.stem}_{spec.side}"] = (
                cmds.getAttr(spec.start + ".rotate")[0],
                cmds.getAttr(spec.end + ".rotate")[0])
            for name, path in ((spec.part1_name, spec.part1),
                               (spec.part2_name, spec.part2)):
                pose_errors[name] = max(abs(a-b) for a, b in zip(
                    original_posed[name], _matrix(cmds, path)))
                pose_local[name] = {"translate": cmds.getAttr(path + ".translate")[0],
                                    "rotate": cmds.getAttr(path + ".rotate")[0],
                                    "scale": cmds.getAttr(path + ".scale")[0]}
            cmds.setAttr(control + ".rotateX", 0.0)
            for label, rotation in pose_values.items():
                cmds.setAttr(control + ".rotate", *rotation)
                for name, path in ((spec.part1_name, spec.part1),
                                   (spec.part2_name, spec.part2)):
                    key = f"{name}:{label}"
                    pose_case_errors[key] = max(abs(a-b) for a, b in zip(
                        original_pose_cases[key], _matrix(cmds, path)))
                    if label == "mixed":
                        mixed_local[name] = cmds.getAttr(path + ".rotate")[0]
                if label == "mixed":
                    original_start, original_end = original_mixed_endpoints[
                        f"{spec.stem}_{spec.side}"]
                    mixed_endpoint_errors[f"{spec.stem}_{spec.side}"] = (
                        max(abs(a-b) for a,b in zip(original_start,
                            _matrix(cmds, spec.start))),
                        max(abs(a-b) for a,b in zip(original_end,
                            _matrix(cmds, spec.end))))
                    mixed_fk_driver_errors[f"{spec.stem}_{spec.side}"] = max(
                        abs(a-b) for a,b in zip(
                            original_mixed_fk_driver[f"{spec.stem}_{spec.side}"],
                            _matrix(cmds, next(item.driven_joint
                                for item in controls if item.control_path == control))))
                cmds.setAttr(control + ".rotate", 0.0, 0.0, 0.0)
        data["pose_errors"] = pose_errors
        data["pose_case_errors"] = pose_case_errors
        data["maximum_pose_case_error"] = max(pose_case_errors.values())
        data["mixed_local"] = mixed_local
        data["original_mixed_local"] = original_mixed_local
        data["mixed_endpoint_errors"] = mixed_endpoint_errors
        data["mixed_fk_driver_errors"] = mixed_fk_driver_errors
        data["endpoint_errors"] = endpoint_errors
        data["endpoint_local"] = endpoint_local
        data["original_endpoint_local"] = original_endpoint_local
        data["pose_local"] = pose_local
        data["original_pose_local"] = original_pose_local
        data["maximum_pose_error"] = max(pose_errors.values())
        for side in ("R", "L"):
            cmds.setAttr(f"AdvPy_ArmSettings.armIkFk_{side}", 1.0)
            cmds.setAttr(f"AdvPy_LegSettings.legIkFk_{side}", 1.0)
        ik_rest_errors = {name: max(abs(a-b) for a,b in zip(
            original_ik_rest[name], _matrix(cmds, path)))
            for spec in specs for name,path in
            ((spec.part1_name,spec.part1),(spec.part2_name,spec.part2))}
        new_ik_body_rest = {f"{spec.stem}_{spec.side}": (
            _matrix(cmds, spec.start), _matrix(cmds, spec.end))
            for spec in specs}
        data["ik_rest_errors"] = ik_rest_errors
        data["maximum_ik_rest_error"] = max(ik_rest_errors.values())
        ik_motion_errors = {}
        ik_local = {}
        ik_twist_candidates = {}
        ik_body_errors = {}
        ik_body_position_errors = {}
        ik_body_motion = {}
        new_ik_control_delta = {}
        for side in ("R", "L"):
            for limb, stems in (("Arm", ("Shoulder", "Elbow")),
                                ("Leg", ("Hip",))):
                control = (cmds.ls(f"AdvPy_{limb}IK_{side}", long=True) or [])[0]
                position = cmds.xform(control, query=True, worldSpace=True,
                                      translation=True)
                cmds.xform(control, worldSpace=True,
                           translation=(position[0], position[1] + 0.3,
                                        position[2]))
                moved = cmds.xform(control, query=True, worldSpace=True,
                                   translation=True)
                new_ik_control_delta[f"{limb}_{side}"] = tuple(
                    a-b for a,b in zip(moved, position))
                for spec in specs:
                    if spec.side == side and spec.stem in stems:
                        label = {"Shoulder":"UpperArm", "Elbow":"LowerArm",
                                 "Hip":"UpperLeg"}[spec.stem]
                        ik_twist_candidates[f"{spec.stem}_{side}"] = {
                            "original": original_ik_twist[f"{spec.stem}_{side}"],
                            "start": cmds.getAttr(spec.twist_project_name +
                                                   ".outputRotateX"),
                            "end": cmds.getAttr(
                                f"AdvPy_{label}TwistProject_{side}.outputRotateX")}
                        orig_start, orig_end = original_ik_body[
                            f"{spec.stem}_{side}"]
                        ik_body_errors[f"{spec.stem}_{side}"] = (
                            max(abs(a-b) for a,b in zip(orig_start,
                                _matrix(cmds, spec.start))),
                            max(abs(a-b) for a,b in zip(orig_end,
                                _matrix(cmds, spec.end))))
                        ik_body_position_errors[f"{spec.stem}_{side}"] = (
                            max(abs(a-b) for a,b in zip(orig_start[12:15],
                                _matrix(cmds, spec.start)[12:15])),
                            max(abs(a-b) for a,b in zip(orig_end[12:15],
                                _matrix(cmds, spec.end)[12:15])))
                        key = f"{spec.stem}_{side}"
                        ik_body_motion[key] = {
                            "original_end_delta": tuple(a-b for a,b in zip(
                                orig_end[12:15],
                                original_ik_body_rest[key][1][12:15])),
                            "new_end_delta": tuple(a-b for a,b in zip(
                                _matrix(cmds, spec.end)[12:15],
                                new_ik_body_rest[key][1][12:15]))}
                        for name, path in ((spec.part1_name, spec.part1),
                                           (spec.part2_name, spec.part2)):
                            ik_motion_errors[name] = max(abs(a-b) for a,b in zip(
                                original_ik_motion[name], _matrix(cmds, path)))
                            ik_local[name] = {
                                "rotate": cmds.getAttr(path + ".rotate")[0],
                                "translate": cmds.getAttr(path + ".translate")[0]}
                cmds.xform(control, worldSpace=True, translation=position)
        data["ik_motion_errors"] = ik_motion_errors
        data["maximum_ik_motion_error"] = max(ik_motion_errors.values())
        ik_fatness_errors = {}
        for spec in specs:
            plug = spec.fatness_control + "." + spec.fatness_attribute
            cmds.setAttr(plug, 0.35)
            for name, path in ((spec.part1_name, spec.part1),
                               (spec.part2_name, spec.part2)):
                ik_fatness_errors[name] = max(abs(a-b) for a,b in zip(
                    original_ik_fatness[name], _matrix(cmds, path)))
            cmds.setAttr(plug, 0.0)
        data["ik_fatness_errors"] = ik_fatness_errors
        data["maximum_ik_fatness_error"] = max(ik_fatness_errors.values())
        ik_volume_errors = {}
        ik_volume_values = {}
        for side in ("R", "L"):
            for limb, start, stems in (
                    ("Arm", "Shoulder", ("Shoulder", "Elbow")),
                    ("Leg", "Hip", ("Hip",))):
                control = (cmds.ls(f"AdvPy_{limb}IK_{side}", long=True) or [])[0]
                anchor = cmds.xform(next(spec.start for spec in specs
                    if spec.stem == start and spec.side == side), query=True,
                    worldSpace=True, translation=True)
                initial = cmds.xform(control, query=True, worldSpace=True,
                                     translation=True)
                target = tuple(a + 1.2 * (b-a) for a,b in zip(anchor, initial))
                cmds.xform(control, worldSpace=True, translation=target)
                volume_plug = f"AdvPy_{limb}Settings.{limb.lower()}Volume_{side}"
                for volume in (10.0, 5.0, 0.0):
                    cmds.setAttr(volume_plug, volume / 10.0)
                    for spec in specs:
                        if spec.side == side and spec.stem in stems:
                            for name,path in ((spec.part1_name,spec.part1),
                                              (spec.part2_name,spec.part2)):
                                key = f"{name}:{int(volume)}"
                                value = cmds.getAttr(path + ".scale")[0]
                                ik_volume_values[key] = value
                                ik_volume_errors[key] = max(abs(a-b) for a,b in
                                    zip(original_ik_volume[key], value))
                cmds.setAttr(volume_plug, 0.5)
                first = next(spec for spec in specs if spec.stem == start
                             and spec.side == side)
                cmds.setAttr(first.fatness_control + ".Fatness1", 0.35)
                for name,path in ((first.part1_name,first.part1),
                                  (first.part2_name,first.part2)):
                    key = f"{name}:combo"
                    value = cmds.getAttr(path + ".scale")[0]
                    ik_volume_values[key] = value
                    ik_volume_errors[key] = max(abs(a-b) for a,b in zip(
                        original_ik_volume[key], value))
                cmds.setAttr(first.fatness_control + ".Fatness1", 0.0)
                cmds.xform(control, worldSpace=True, translation=initial)
                cmds.setAttr(volume_plug, 1.0)
        data["ik_volume_errors"] = ik_volume_errors
        data["maximum_ik_volume_error"] = max(ik_volume_errors.values())
        data["ik_volume_values"] = ik_volume_values
        data["original_ik_local"] = original_ik_local
        data["ik_local"] = ik_local
        data["ik_twist_candidates"] = ik_twist_candidates
        data["ik_body_errors"] = ik_body_errors
        data["ik_body_position_errors"] = ik_body_position_errors
        data["ik_body_motion"] = ik_body_motion
        data["ik_control_delta"] = {"original": original_ik_control_delta,
                                    "new": new_ik_control_delta}
        data["original_ik_handle_delta"] = original_ik_handle_delta
        data["original_ik_driver_delta"] = original_ik_driver_delta
        for side in ("R", "L"):
            cmds.setAttr(f"AdvPy_ArmSettings.armIkFk_{side}", 0.0)
            cmds.setAttr(f"AdvPy_LegSettings.legIkFk_{side}", 0.0)
        custom_twist_errors = {}
        for spec in specs:
            control = next(item.control_path for item in controls
                if item.control_path.rsplit("|", 1)[-1] ==
                   f"AdvPy_{spec.stem}FK_{spec.side}")
            for name, path, amount, addition in (
                    (spec.part1_name, spec.part1, 0.2, 5.0),
                    (spec.part2_name, spec.part2, 0.8, -3.0)):
                cmds.setAttr(path + ".twistAmount", amount)
                cmds.setAttr(path + ".twistAddition", addition)
            cmds.setAttr(control + ".rotateX", 12.0)
            for name, path in ((spec.part1_name, spec.part1),
                               (spec.part2_name, spec.part2)):
                custom_twist_errors[name] = max(abs(a-b) for a,b in zip(
                    original_custom_twist[name], _matrix(cmds, path)))
            cmds.setAttr(control + ".rotateX", 0.0)
            for path, amount in ((spec.part1, 1.0 / 3.0),
                                 (spec.part2, 2.0 / 3.0)):
                cmds.setAttr(path + ".twistAmount", amount)
                cmds.setAttr(path + ".twistAddition", 0.0)
        data["custom_twist_errors"] = custom_twist_errors
        data["maximum_custom_twist_error"] = max(custom_twist_errors.values())
        fk_scale_errors = {}
        fk_scale_local = {}
        fk_scale_matrix = {}
        fk_scale_end = {}
        fk_scale_start = {}
        fk_scale_end_local = {}
        fk_scale_up_twist = {}
        for spec in specs:
            control = next(item.control_path for item in controls
                if item.control_path.rsplit("|", 1)[-1] ==
                   f"AdvPy_{spec.stem}FK_{spec.side}")
            cmds.setAttr(control + ".scale", 1.2, 0.8, 1.1)
            fk_scale_end[f"{spec.stem}_{spec.side}"] = _matrix(cmds, spec.end)
            fk_scale_start[f"{spec.stem}_{spec.side}"] = _matrix(cmds, spec.start)
            fk_scale_end_local[f"{spec.stem}_{spec.side}"] = cmds.getAttr(
                spec.end + ".translate")[0]
            if spec.up_twist_source:
                fk_scale_up_twist[f"{spec.stem}_{spec.side}"] = cmds.getAttr(
                    spec.up_twist_source)
            for name, path in ((spec.part1_name, spec.part1),
                               (spec.part2_name, spec.part2)):
                fk_scale_errors[name] = max(abs(a-b) for a,b in zip(
                    original_fk_scale[name], _matrix(cmds, path)))
                fk_scale_local[name] = cmds.getAttr(path + ".scale")[0]
                fk_scale_matrix[name] = _matrix(cmds, path)
            cmds.setAttr(control + ".scale", 1.0, 1.0, 1.0)
        data["fk_scale_errors"] = fk_scale_errors
        data["maximum_fk_scale_error"] = max(fk_scale_errors.values())
        data["original_fk_scale_local"] = original_fk_scale_local
        data["fk_scale_local"] = fk_scale_local
        data["fk_scale_matrix"] = fk_scale_matrix
        data["original_fk_scale_matrix"] = original_fk_scale
        data["fk_scale_end_errors"] = {key: max(abs(a-b) for a,b in zip(
            original_fk_scale_end[key], fk_scale_end[key]))
            for key in fk_scale_end}
        data["fk_scale_start_errors"] = {key: max(abs(a-b) for a,b in zip(
            original_fk_scale_start[key], fk_scale_start[key]))
            for key in fk_scale_start}
        data["original_fk_scale_start_matrix"] = original_fk_scale_start
        data["fk_scale_start_matrix"] = fk_scale_start
        data["fk_scale_end_local"] = fk_scale_end_local
        data["original_fk_scale_end_local"] = original_fk_scale_end_local
        data["fk_scale_up_twist"] = fk_scale_up_twist
        data["original_fk_scale_up_twist"] = original_fk_scale_up_twist
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "limb-part.mb"
            cmds.file(rename=str(output))
            cmds.file(save=True, type="mayaBinary")
            cmds.file(str(output), open=True, force=True,
                      executeScriptNodes=False)
            data["reopen_part_count"] = sum(bool(cmds.objExists(spec.part2))
                                            for spec in specs) * 2
            resolver = ResolveBodyCharacter(MayaBodyBuildHost())
            registrations = resolver.discover()
            data["registration_body_count"] = len(
                resolver.execute(registrations[0]).body)
        data["status"] = "passed" if (
            data["body_count"] == 74 and data["part_count"] == 12
            and data["maximum_rest_error"] < 0.02
            and data["maximum_pose_error"] < 0.02
            and data["maximum_pose_case_error"] < 0.02
            and data["maximum_ik_rest_error"] < 0.02
            and data["maximum_ik_motion_error"] < 0.02
            and data["maximum_ik_fatness_error"] < 0.02
            and data["maximum_ik_volume_error"] < 0.02
            and data["maximum_custom_twist_error"] < 0.02
            and data["maximum_fk_scale_error"] < 0.02
            and data["undo_removed_parts"] and data["redo_restored_parts"]
            and data["undo_removed_fatness"] and data["redo_restored_fatness"]
            and data["fault_rolled_back"]
            and data["reopen_part_count"] == 12
            and data["registration_body_count"] == 74) else "failed"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        return 0 if data["status"] == "passed" else 1
    except Exception:
        import traceback
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(traceback.format_exc(), encoding="utf-8")
        print(traceback.format_exc().encode("ascii", "backslashreplace").decode(),
              flush=True)
        raise
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]), Path(sys.argv[2])))
