"""Compare evaluated Python face poses with the original ADV character."""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys


def read_obj(path: Path) -> tuple[list[tuple[float, float, float]],
                                  list[tuple[int, ...]]]:
    points = []
    faces = []
    with path.open(encoding="ascii") as stream:
        for line in stream:
            if line.startswith("v "):
                points.append(tuple(float(value) for value in
                                    line.split()[1:4]))
            elif line.startswith("f "):
                faces.append(tuple(int(item.split("/", 1)[0])
                                   for item in line.split()[1:]))
    if not points or not faces:
        raise ValueError("OBJ 缺少顶点或面：" + str(path))
    return points, faces


def metrics(values: list[float]) -> dict:
    ordered = sorted(values)
    return {"count": len(values),
            "rms_cm": round(math.sqrt(sum(value * value for value in values)
                                      / len(values)), 6),
            "mean_cm": round(sum(values) / len(values), 6),
            "p95_cm": round(ordered[min(len(values) - 1,
                                        math.ceil(len(values) * .95) - 1)], 6),
            "maximum_cm": round(ordered[-1], 6)}


def main() -> None:
    original = Path(sys.argv[1]).resolve()
    rebuilt = Path(sys.argv[2]).resolve()
    output = Path(sys.argv[3]).resolve()
    rows = {}
    for label in ("head", "right-eye", "left-eye"):
        reference = {pose: read_obj(original / (pose + "-" + label + ".obj"))
                     for pose in ("open", "blink")}
        candidate = {pose: read_obj(rebuilt / (pose + "-" + label + ".obj"))
                     for pose in ("open", "blink")}
        face_order = reference["open"][1]
        if any(faces != face_order for points, faces in
               (*reference.values(), *candidate.values())):
            raise ValueError(label + " 四件 OBJ 的面及顶点顺序不一致")
        if any(len(points) != len(reference["open"][0]) for points, _ in
               (*reference.values(), *candidate.values())):
            raise ValueError(label + " 四件 OBJ 的顶点数不一致")
        base_errors = [math.dist(first, second) for first, second in zip(
            reference["open"][0], candidate["open"][0])]
        if max(base_errors) > 1e-4:
            raise ValueError(label + " 张眼静态网格不对应，不能逐顶点比较")
        ref_motion = [tuple(end[axis] - start[axis] for axis in range(3))
                      for start, end in zip(reference["open"][0],
                                            reference["blink"][0])]
        new_motion = [tuple(end[axis] - start[axis] for axis in range(3))
                      for start, end in zip(candidate["open"][0],
                                            candidate["blink"][0])]
        errors = [math.dist(first, second) for first, second in zip(
            reference["blink"][0], candidate["blink"][0])]
        moving = [index for index, (first, second) in enumerate(zip(
            ref_motion, new_motion)) if max(math.sqrt(sum(v*v for v in first)),
                                            math.sqrt(sum(v*v for v in second)))
                  > 1e-4]
        rows[label] = {"vertex_count": len(errors),
                       "open_alignment": metrics(base_errors),
                       "closed_all": metrics(errors),
                       "closed_moving": metrics([errors[index]
                                                 for index in moving])
                       if moving else None,
                       "reference_moved_vertices": sum(
                           math.sqrt(sum(v*v for v in delta)) > 1e-4
                           for delta in ref_motion),
                       "candidate_moved_vertices": sum(
                           math.sqrt(sum(v*v for v in delta)) > 1e-4
                           for delta in new_motion)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"meshes": rows}, ensure_ascii=False,
                                 indent=2) + "\n", encoding="utf-8")
    print("Original face pose comparison:",
          {key: {"moving_rms_cm": row["closed_moving"]["rms_cm"]
                if row["closed_moving"] else None,
                 "maximum_cm": row["closed_all"]["maximum_cm"]}
           for key, row in rows.items()}, flush=True)


if __name__ == "__main__":
    main()
