"""Read the original weighted limb Part joints and their driver settings."""
from __future__ import annotations

import json
from pathlib import Path
import sys


def main(scene: Path, report: Path) -> None:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        cmds.file(str(scene.resolve()), open=True, force=True,
                  executeScriptNodes=False)
        rows = []
        drivers = {}
        for side in ("R", "L"):
            for stem, end in (("Shoulder", "Elbow"),
                              ("Elbow", "Wrist"), ("Hip", "Knee")):
                blend = f"{stem}PartBM_{side}"
                drivers[f"{stem}_{side}"] = {
                    "blend_weight": cmds.getAttr(blend + ".target[0].weight"),
                    "translation": cmds.getAttr(
                        f"{stem}PartDM_{side}.outputTranslate")[0],
                    "twist_project": {
                        "node": f"{stem}QTETwist_{side}",
                        "type": cmds.nodeType(f"{stem}QTETwist_{side}"),
                        "inputs": cmds.listConnections(
                            f"{stem}QTETwist_{side}", source=True,
                            destination=False, connections=True,
                            plugs=True) or [],
                        "decompose_input": cmds.listConnections(
                            f"{stem}DMTwist_{side}.inputMatrix", source=True,
                            destination=False, plugs=True) or [],
                        "matrix_inputs": cmds.listConnections(
                            f"{stem}MMTwist_{side}", source=True,
                            destination=False, connections=True,
                            plugs=True) or [],
                    },
                    "extra_twist": {f"Part{index}": {
                        "sum_inputs": {str(i): cmds.listConnections(
                            f"twistAddition{stem}Part{index}_{side}.input1D[{i}]",
                            source=True, destination=False, plugs=True) or []
                            for i in (cmds.getAttr(
                                f"twistAddition{stem}Part{index}_{side}.input1D",
                                multiIndices=True) or [])}
                    } for index in (1, 2)},
                    "up_twist_nodes": {f"Part{index}": {
                        "exists": cmds.objExists(
                            f"upTwistAmountDivide{end}Part{index}_{side}"),
                        "inputs": cmds.listConnections(
                            f"upTwistAmountDivide{end}Part{index}_{side}",
                            source=True, destination=False,
                            connections=True, plugs=True) or [],
                        "factor": cmds.getAttr(
                            f"upTwistAmountDivide{end}Part{index}_{side}.input2")
                            if cmds.objExists(
                                f"upTwistAmountDivide{end}Part{index}_{side}") else None,
                    } for index in (1, 2)} if stem != "Shoulder" else {},
                }
                for index in (1, 2):
                    name = f"{stem}Part{index}_{side}"
                    if not cmds.objExists(name):
                        raise ValueError("原版缺少分段关节：" + name)
                    rows.append({
                        "name": name,
                        "parent": (cmds.listRelatives(name, parent=True,
                            fullPath=True) or [None])[0],
                        "end": f"{end}_{side}",
                        "local_translate": cmds.getAttr(name + ".translate")[0],
                        "joint_orient": cmds.getAttr(name + ".jointOrient")[0],
                        "rotate": cmds.getAttr(name + ".rotate")[0],
                        "scale": cmds.getAttr(name + ".scale")[0],
                        "segment_scale_compensate": cmds.getAttr(
                            name + ".segmentScaleCompensate"),
                        "world_matrix": cmds.xform(name, query=True,
                            worldSpace=True, matrix=True),
                        "twist_amount": cmds.getAttr(name + ".twistAmount")
                            if cmds.attributeQuery("twistAmount", node=name,
                                                   exists=True) else None,
                        "twist_addition": cmds.getAttr(name + ".twistAddition")
                            if cmds.attributeQuery("twistAddition", node=name,
                                                   exists=True) else None,
                    })
        report.parent.mkdir(parents=True, exist_ok=True)
        controls = {pattern: cmds.ls(pattern, type="transform") or [] for pattern
                    in ("*IK*Wrist*", "*IK*Ankle*", "IKArm_*", "IKLeg_*")}
        control_details = {name: {
            "position": cmds.xform(name, query=True, worldSpace=True,
                                   translation=True),
            "parent": cmds.listRelatives(name, parent=True, fullPath=True) or [],
            "children": cmds.listRelatives(name, children=True,
                                           fullPath=True) or [],
            "local_translate": cmds.getAttr(name + ".translate")[0],
            "local_scale": cmds.getAttr(name + ".scale")[0],
            "translate_outputs": cmds.listConnections(name + ".translate",
                source=False, destination=True, plugs=True) or [],
            "user_attributes": {attr: cmds.getAttr(name + "." + attr)
                for attr in (cmds.listAttr(name, userDefined=True) or [])
                if cmds.getAttr(name + "." + attr, type=True)
                    in ("double", "float", "bool", "long", "enum")},
        } for name in ("IKArm_R", "IKLeg_R", "IKXWrist_R", "IKXAnkle_R")}
        handle_details = {name: {
            "ik_blend": cmds.getAttr(name + ".ikBlend"),
            "solver": cmds.listConnections(name + ".ikSolver", source=True,
                                            destination=False) or [],
        } for name in ("IKArmHandle_R", "IKArmHandle_L",
                       "IKAnkleHandle_R", "IKAnkleHandle_L")}
        ik_joint_details = {name: {
            "local_translate": cmds.getAttr(name + ".translate")[0],
            "world_matrix": cmds.xform(name, query=True, worldSpace=True,
                                         matrix=True),
            "parent": cmds.listRelatives(name, parent=True, fullPath=True) or [],
        } for name in ("IKXShoulder_R", "IKXElbow_R", "IKXWrist_R",
                       "IKXHip_R", "IKXKnee_R", "IKXAnkle_R")}
        fresh_ik_probe = {}
        fresh_fk_wrist_probe = {}
        fk_rotate_orders = {f"{stem}_{side}": cmds.getAttr(
            f"FK{stem}_{side}.rotateOrder") for side in ("R", "L")
            for stem in ("Shoulder", "Elbow", "Wrist", "Hip", "Knee",
                         "Ankle", "Toes") if cmds.objExists(f"FK{stem}_{side}")}
        for side in ("R", "L"):
            for limb, stem in (("Arm", "Elbow"), ("Leg", "Hip")):
                cmds.setAttr(f"FKIK{limb}_{side}.FKIKBlend", 10.0)
                control = f"IK{limb}_{side}"
                p = cmds.xform(control, query=True, worldSpace=True,
                               translation=True)
                cmds.xform(control, worldSpace=True,
                           translation=(p[0], p[1] + 0.3, p[2]))
                part = f"{stem}Part1_{side}"
                fresh_ik_probe[f"{stem}_{side}"] = {
                    "part_rotate": cmds.getAttr(part + ".rotateX"),
                    "source": cmds.getAttr(
                        f"{stem}QTETwist_{side}.outputRotateX"),
                    "amount_input": cmds.getAttr(
                        f"twistAmountDivide{part}.input1"),
                    "amount_output": cmds.getAttr(
                        f"twistAmountDivide{part}.output"),
                    "sum_inputs": {str(i): cmds.getAttr(
                        f"twistAddition{part}.input1D[{i}]")
                        for i in (cmds.getAttr(f"twistAddition{part}.input1D",
                                               multiIndices=True) or [])},
                    "sum_output": cmds.getAttr(
                        f"twistAddition{part}.output1D"),
                    "sum_operation": cmds.getAttr(
                        f"twistAddition{part}.operation"),
                    "third_input_source": cmds.listConnections(
                        f"twistAddition{part}.input1D[2]", source=True,
                        destination=False, plugs=True) or [],
                    "third_input_settable": cmds.getAttr(
                        f"twistAddition{part}.input1D[2]", settable=True),
                }
                cmds.xform(control, worldSpace=True, translation=p)
        for side in ("R", "L"):
            cmds.setAttr(f"FKIKArm_{side}.FKIKBlend", 0.0)
            control = f"FKWrist_{side}"
            cmds.setAttr(control + ".rotateX", 12.0)
            fresh_fk_wrist_probe[side] = {
                "elbow_part_rotate": cmds.getAttr(
                    f"ElbowPart1_{side}.rotateX"),
                "wrist_twist": cmds.getAttr(
                    f"WristQTETwist_{side}.outputRotateX"),
            }
            cmds.setAttr(control + ".rotateX", 0.0)
        report.write_text(json.dumps({"joints": rows, "drivers": drivers,
                                      "control_candidates": controls,
                                      "control_details": control_details,
                                      "handle_details": handle_details,
                                      "ik_joint_details": ik_joint_details,
                                      "fk_rotate_orders": fk_rotate_orders,
                                      "fresh_ik_probe": fresh_ik_probe,
                                      "fresh_fk_wrist_probe": fresh_fk_wrist_probe},
            ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
