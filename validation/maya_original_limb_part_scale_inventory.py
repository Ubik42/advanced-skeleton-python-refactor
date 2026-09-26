"""Read the original sam IK Fatness and volume response without saving it."""
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
        for side in ("R", "L"):
            cmds.setAttr(f"FKIKArm_{side}.FKIKBlend", 10.0)
            cmds.setAttr(f"FKIKLeg_{side}.FKIKBlend", 10.0)

        def sample():
            return {f"{stem}Part{index}_{side}": {
                "scale": cmds.getAttr(f"{stem}Part{index}_{side}.scale")[0],
                "matrix": cmds.xform(f"{stem}Part{index}_{side}", query=True,
                                     worldSpace=True, matrix=True),
            } for side in ("R", "L")
              for stem in ("Shoulder", "Elbow", "Hip")
              for index in (1, 2)}

        scenarios = {"neutral": sample()}
        driver_graph = {name: {
            "type": cmds.nodeType(name),
            "inputs": cmds.listConnections(name, source=True,
                destination=False, connections=True, plugs=True) or []}
            for name in ("fatnessIKXShoulder_R", "fatnessIKXElbow_R",
                         "fatnessIKXHip_R", "volumeBlendArmBlendTwo_R",
                         "volumeBlendLegBlendTwo_R", "volumepowArm_R",
                         "volumepowLeg_R", "multWithStretchyArm_R",
                         "multWithStretchyLeg_R")}
        volume_parameters = {name: {
            "operation": cmds.getAttr(name + ".operation"),
            "input1X": cmds.getAttr(name + ".input1X"),
            "input2X": cmds.getAttr(name + ".input2X")}
            for name in ("volumepowArm_R", "volumepowLeg_R",
                         "multWithStretchyArm_R", "multWithStretchyLeg_R")}
        attributes = {}
        for limb in ("Arm", "Leg"):
            control = f"IK{limb}_R"
            attributes[control] = {}
            for attr in ("Fatness1", "Fatness2", "volume", "Lenght1", "Lenght2",
                         "stretchy"):
                has_min = cmds.attributeQuery(attr, node=control,
                                               minExists=True)
                has_max = cmds.attributeQuery(attr, node=control,
                                               maxExists=True)
                attributes[control][attr] = {
                    "default": cmds.getAttr(control + "." + attr),
                    "minimum": cmds.attributeQuery(attr, node=control,
                        minimum=True) if has_min else None,
                    "maximum": cmds.attributeQuery(attr, node=control,
                        maximum=True) if has_max else None}
            for attr, value in (("Fatness1", 5.0), ("Fatness2", 5.0),
                                ("volume", 5.0), ("Lenght1", 1.2),
                                ("stretchy", 10.0)):
                plug = control + "." + attr
                previous = cmds.getAttr(plug)
                cmds.setAttr(plug, value)
                scenarios[f"{limb}_{attr}"] = sample()
                cmds.setAttr(plug, previous)
            start = f"Shoulder_R" if limb == "Arm" else "Hip_R"
            start_position = cmds.xform(start, query=True, worldSpace=True,
                                        translation=True)
            initial = cmds.xform(control, query=True, worldSpace=True,
                                 translation=True)
            delta = tuple(b-a for a,b in zip(start_position, initial))
            target = tuple(a + value * 1.2 for a,value in zip(start_position,
                                                                delta))
            cmds.setAttr(control + ".stretchy", 10.0)
            cmds.xform(control, worldSpace=True, translation=target)
            for volume in (10.0, 5.0, 0.0):
                cmds.setAttr(control + ".volume", volume)
                scenarios[f"{limb}_far_volume{int(volume)}"] = sample()
            cmds.xform(control, worldSpace=True, translation=initial)
            cmds.setAttr(control + ".volume", 10.0)
            cmds.setAttr(control + ".stretchy", 0.0)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({"source": scene.name,
            "attributes": attributes, "scenarios": scenarios,
            "driver_graph": driver_graph,
            "volume_parameters": volume_parameters},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
