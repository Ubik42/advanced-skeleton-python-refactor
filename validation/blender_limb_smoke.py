from __future__ import annotations

import json
from math import dist, radians
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main(output: Path) -> int:
    import bpy
    from mathutils import Matrix, Vector

    from adv_py.adapters import BlenderRigHost
    from adv_py.application import BuildRig
    from adv_py.core import rows
    from adv_py.examples import ik_fk_limb_plan

    started = time.perf_counter()
    plan = ik_fk_limb_plan()
    nodes = {node.key: node for node in plan.nodes}
    limb = plan.limbs[0]
    host = BlenderRigHost()
    result = BuildRig(host).execute(plan)
    armature = bpy.data.objects["PortableRig_Armature"]
    bind_armature = bpy.data.objects["PortableRig_Armature_Bind"]
    settings = bpy.data.objects[nodes[limb.settings].name]
    bind_end = bind_armature.pose.bones[nodes[limb.bind_chain[-1]].name]

    def end_position() -> tuple[float, float, float]:
        bpy.context.view_layer.update()
        point = bind_armature.matrix_world @ bind_end.head
        return tuple(point)

    def set_blend(value: float) -> None:
        settings[limb.blend_attribute] = value
        settings.update_tag()
        current_frame = bpy.context.scene.frame_current
        bpy.context.scene.frame_set(current_frame + 1)
        bpy.context.scene.frame_set(current_frame)

    initial_position = end_position()
    set_blend(0.0)
    upper_control = bpy.data.objects[nodes[limb.fk_controls[0]].name]
    upper_control.matrix_world = upper_control.matrix_world @ Matrix.Rotation(
        radians(20.0), 4, "Z"
    )
    fk_position = end_position()
    fk_pose_changed = dist(initial_position, fk_position) > 0.1

    for control_key in limb.fk_controls:
        node = nodes[control_key]
        bpy.data.objects[node.name].matrix_world = Matrix(rows(node.world_matrix))
    set_blend(1.0)
    ik_target_position = (1.25, 3.4, 1.0)
    bpy.data.objects[nodes[limb.ik_target].name].matrix_world.translation = Vector(
        ik_target_position
    )
    ik_position = end_position()
    ik_end_error = dist(ik_position, ik_target_position)
    ik_pose_reached = ik_end_error < 0.05
    ik_lower = armature.pose.bones[nodes[limb.ik_chain[-2]].name]
    ik_end = armature.pose.bones[nodes[limb.ik_chain[-1]].name]
    ik_lower_tail = tuple(armature.matrix_world @ ik_lower.tail)
    ik_end_head = tuple(armature.matrix_world @ ik_end.head)
    bind_end_influences = {
        constraint.name: constraint.influence for constraint in bind_end.constraints
    }
    driver_curves = tuple(armature.animation_data.drivers) + tuple(
        bind_armature.animation_data.drivers
    )
    drivers_valid = all(curve.driver.is_valid for curve in driver_curves)

    duplicate_blocked = False
    try:
        BuildRig(BlenderRigHost()).execute(plan)
    except RuntimeError as error:
        duplicate_blocked = "预检失败" in str(error)

    host.rollback_last()
    remaining = sorted(obj.name for obj in bpy.data.objects if obj.name.startswith("Portable"))
    passed = (
        fk_pose_changed
        and ik_pose_reached
        and drivers_valid
        and duplicate_blocked
        and not remaining
    )
    payload = {
        "host": "blender",
        "version": bpy.app.version_string,
        "pid": os.getpid(),
        "plan": result.plan,
        "created_nodes": result.created_nodes,
        "created_limbs": result.created_limbs,
        "fk_pose_changed": fk_pose_changed,
        "fk_end_delta": round(dist(initial_position, fk_position), 6),
        "ik_pose_reached": ik_pose_reached,
        "ik_end_error": round(ik_end_error, 6),
        "ik_target_position": ik_target_position,
        "ik_lower_tail": ik_lower_tail,
        "ik_end_head": ik_end_head,
        "bind_end_head": ik_position,
        "bind_end_constraint_influences": bind_end_influences,
        "drivers_valid": drivers_valid,
        "duplicate_preflight_blocked": duplicate_blocked,
        "rollback_clean": not remaining,
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


if __name__ == "__main__":
    separator = sys.argv.index("--")
    raise SystemExit(main(Path(sys.argv[separator + 1])))
