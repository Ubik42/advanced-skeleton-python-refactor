from __future__ import annotations

import json
from math import dist
import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import maya.standalone


def main(output: Path) -> int:
    started = time.perf_counter()
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds

        from adv_py.adapters import MayaRigHost
        from adv_py.application import BuildRig
        from adv_py.core import transpose_flat
        from adv_py.examples import ik_fk_limb_plan

        cmds.file(new=True, force=True)
        plan = ik_fk_limb_plan()
        nodes = {node.key: node for node in plan.nodes}
        limb = plan.limbs[0]
        host = MayaRigHost()
        result = BuildRig(host).execute(plan)

        settings_attr = f"{nodes[limb.settings].name}.{limb.blend_attribute}"
        bind_end = nodes[limb.bind_chain[-1]].name
        initial_position = cmds.xform(
            bind_end, query=True, worldSpace=True, translation=True
        )
        cmds.setAttr(settings_attr, 0.0)
        cmds.rotate(
            0.0,
            0.0,
            20.0,
            nodes[limb.fk_controls[0]].name,
            relative=True,
            objectSpace=True,
        )
        fk_position = cmds.xform(
            bind_end, query=True, worldSpace=True, translation=True
        )
        fk_pose_changed = dist(initial_position, fk_position) > 0.1

        for control_key in limb.fk_controls:
            node = nodes[control_key]
            cmds.xform(
                node.name,
                worldSpace=True,
                matrix=list(transpose_flat(node.world_matrix)),
            )
        cmds.setAttr(settings_attr, 1.0)
        ik_target_position = (1.25, 3.4, 1.0)
        cmds.xform(
            nodes[limb.ik_target].name,
            worldSpace=True,
            translation=ik_target_position,
        )
        ik_position = cmds.xform(
            bind_end, query=True, worldSpace=True, translation=True
        )
        ik_end_error = dist(ik_position, ik_target_position)
        ik_pose_reached = ik_end_error < 0.05

        duplicate_blocked = False
        try:
            BuildRig(MayaRigHost()).execute(plan)
        except RuntimeError as error:
            duplicate_blocked = "预检失败" in str(error)

        host.rollback_last()
        remaining = sorted(
            set(
                (cmds.ls("Portable*") or [])
                + (cmds.ls("portable_limb*") or [])
            )
        )
        passed = fk_pose_changed and ik_pose_reached and duplicate_blocked and not remaining
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "plan": result.plan,
            "created_nodes": result.created_nodes,
            "created_limbs": result.created_limbs,
            "fk_pose_changed": fk_pose_changed,
            "fk_end_delta": round(dist(initial_position, fk_position), 6),
            "ik_pose_reached": ik_pose_reached,
            "ik_end_error": round(ik_end_error, 6),
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
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
