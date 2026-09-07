from __future__ import annotations

import json
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
        from adv_py.examples import two_joint_plan

        cmds.file(new=True, force=True)
        host = MayaRigHost()
        plan = two_joint_plan()
        result = BuildRig(host).execute(plan)
        joint_orient = {
            node.name: list(cmds.getAttr(f"{node.name}.jointOrient")[0])
            for node in plan.nodes
            if node.kind == "joint"
        }
        rotate_channels = {
            node.name: list(cmds.getAttr(f"{node.name}.rotate")[0])
            for node in plan.nodes
            if node.kind == "joint"
        }
        orientation_encoded = (
            all(any(abs(value) > 1e-4 for value in values) for values in joint_orient.values())
            and all(all(abs(value) < 1e-4 for value in values) for values in rotate_channels.values())
        )
        duplicate_blocked = False
        try:
            BuildRig(MayaRigHost()).execute(plan)
        except RuntimeError as error:
            duplicate_blocked = "预检失败" in str(error)
        host.rollback_last()
        remaining = [node.name for node in plan.nodes if cmds.objExists(node.name)]
        payload = {
            "host": "maya",
            "version": str(cmds.about(version=True)),
            "pid": os.getpid(),
            "plan": result.plan,
            "created_nodes": result.created_nodes,
            "created_constraints": result.created_constraints,
            "joint_orient_degrees": joint_orient,
            "joint_rotate_degrees": rotate_channels,
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
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
