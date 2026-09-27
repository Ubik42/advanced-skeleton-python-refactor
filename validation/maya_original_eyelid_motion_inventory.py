"""Read original ADV eyelid joint and head motion at full blink."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds
from maya.api import OpenMaya as om


_JOINT = re.compile(r"^(upper|lower)Lid(Main|Outer)(\d+)_(R|L)$")


def main() -> None:
    scene = Path(sys.argv[1]).resolve()
    head_name = sys.argv[2]
    output = Path(sys.argv[3]).resolve()
    cmds.file(str(scene), open=True, force=True,
              executeScriptNodes=False)
    selection = om.MSelectionList()
    selection.add(head_name)
    head = om.MFnMesh(selection.getDagPath(0))
    groups = {}
    for joint in cmds.ls(type="joint", long=True) or []:
        match = _JOINT.fullmatch(joint.rsplit("|", 1)[-1])
        if match:
            groups.setdefault(match.group(1) + match.group(2) +
                              match.group(4), []).append(
                                  (int(match.group(3)), joint))
    for group in groups.values():
        group.sort()
    poses = {}
    cmds.currentTime(1, edit=True)
    for label, blink in (("open", 0), ("closed", 10)):
        for control in ("ctrlEye_R", "ctrlEye_L"):
            cmds.setAttr(control + ".blink", blink)
        poses[label] = {
            "head_points": [tuple(float(p[axis]) for axis in range(3))
                            for p in head.getPoints(om.MSpace.kWorld)],
            "matrices": {name: [tuple(float(value) for value in
                         cmds.xform(joint, query=True, worldSpace=True,
                                    matrix=True))
                         for _, joint in group]
                        for name, group in groups.items()},
            "groups": {name: [tuple(float(value) for value in
                        cmds.xform(joint, query=True, worldSpace=True,
                                   translation=True))
                        for _, joint in group]
                       for name, group in groups.items()}}
    rows = {}
    for name, group in groups.items():
        points_open = poses["open"]["groups"][name]
        points_closed = poses["closed"]["groups"][name]
        deltas = [tuple(after[axis] - before[axis] for axis in range(3))
                  for before, after in zip(points_open, points_closed)]
        rows[name] = {"count": len(group),
                      "indices": [index for index, _ in group],
                      "open": points_open,
                      "closed": points_closed,
                      "open_matrices": poses["open"]["matrices"][name],
                      "closed_matrices": poses["closed"]["matrices"][name],
                      "deltas": deltas,
                      "middle_delta": deltas[len(deltas) // 2]}
    before = poses["open"]["head_points"]
    after = poses["closed"]["head_points"]
    moved = [index for index, (first, second) in enumerate(zip(before, after))
             if sum((a - b) ** 2 for a, b in zip(first, second)) > 1e-10]
    result = {"scene": scene.name, "head": head_name,
              "joint_groups": rows,
              "head_vertex_count": len(before),
              "moved_head_vertices": len(moved),
              "maximum_head_delta_cm": max((sum((a-b)**2 for a,b in
                    zip(before[index],after[index]))**.5 for index in moved),
                    default=0.),
              "head_open_points": before,
              "head_closed_points": after}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print("Original ADV eyelid motion:", scene.name,
          "groups", {key: (row["count"],
                   tuple(round(value, 5) for value in row["middle_delta"]))
                   for key, row in rows.items()},
          "moved vertices", len(moved), flush=True)


if __name__ == "__main__":
    main()
