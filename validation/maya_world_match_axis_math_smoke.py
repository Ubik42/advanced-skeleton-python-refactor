"""Compare portable World Match frames against Maya aimConstraint frames."""
from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

IDENTITY = (1., 0., 0., 0., 0., 1., 0., 0.,
            0., 0., 1., 0., 0., 0., 0., 1.)


def main(report: Path) -> int:
    import maya.standalone

    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.core import (ControlOrientationState,
                                 plan_control_orientation_world_axis_match)

        report.parent.mkdir(parents=True, exist_ok=True)
        cmds.file(new=True, force=True)
        cases = ((1., 0., 0.), (-1., 0., 0.),
                 (0., 1., 0.), (0., -1., 0.),
                 (0., 0., 1.), (0., 0., -1.))
        errors = {}
        for source in cases:
            axis = next(index for index, value in enumerate(source)
                        if value)
            up = (0., 0., 1.) if axis == 1 else (0., 1., 0.)
            expected = plan_control_orientation_world_axis_match(
                (ControlOrientationState("|Probe", IDENTITY),),
                (("|Probe", source),)).changes[0].after.world_matrix
            holder = cmds.createNode("transform", name="Probe")
            target = cmds.createNode("transform", name="AimTarget")
            cmds.setAttr(target + ".translateX", 1.)
            constraint = cmds.aimConstraint(
                target, holder, aimVector=source, upVector=up,
                worldUpType="vector", worldUpVector=up)[0]
            actual = tuple(float(value) for value in cmds.xform(
                holder, query=True, worldSpace=True, matrix=True))
            key = "".join(str(int(value)) for value in source)
            errors[key] = max(abs(a - b) for a, b in zip(
                actual, expected))
            cmds.delete(constraint, holder, target)
        payload = {"max_errors": errors,
                   "status": "passed" if all(error < 1e-5
                                               for error in errors.values())
                   else "failed"}
        report.write_text(json.dumps(payload, indent=2) + "\n",
                          encoding="utf-8")
        return 0 if payload["status"] == "passed" else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
