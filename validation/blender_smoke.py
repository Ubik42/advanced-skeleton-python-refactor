from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main(output: Path) -> int:
    import bpy

    from adv_py.adapters import BlenderRigHost
    from adv_py.application import BuildRig
    from adv_py.examples import two_joint_plan

    started = time.perf_counter()
    plan = two_joint_plan()
    host = BlenderRigHost()
    result = BuildRig(host).execute(plan)
    armature = bpy.data.objects["PortableRig_Armature"]
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bone_roll = {
        node.name: armature.data.edit_bones[node.name].roll
        for node in plan.nodes
        if node.kind == "joint"
    }
    bpy.ops.object.mode_set(mode="OBJECT")
    orientation_encoded = all(abs(value) > 1e-4 for value in bone_roll.values())
    duplicate_blocked = False
    try:
        BuildRig(BlenderRigHost()).execute(plan)
    except RuntimeError as error:
        duplicate_blocked = "预检失败" in str(error)
    host.rollback_last()
    remaining = [
        node.name
        for node in plan.nodes
        if node.kind != "joint" and bpy.data.objects.get(node.name) is not None
    ]
    if bpy.data.objects.get("PortableRig_Armature") is not None:
        remaining.append("PortableRig_Armature")
    payload = {
        "host": "blender",
        "version": bpy.app.version_string,
        "pid": os.getpid(),
        "plan": result.plan,
        "created_nodes": result.created_nodes,
        "created_constraints": result.created_constraints,
        "bone_roll_radians": bone_roll,
        "orientation_encoded_in_rest_state": orientation_encoded,
        "duplicate_preflight_blocked": duplicate_blocked,
        "rollback_clean": not remaining,
        "remaining_nodes": remaining,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "status": "passed" if duplicate_blocked and not remaining and orientation_encoded else "failed",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    separator = sys.argv.index("--")
    raise SystemExit(main(Path(sys.argv[separator + 1])))
