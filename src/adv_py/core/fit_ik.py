"""ADV 6.925 asFitJointIKInfo and asGetIKJoints on captured Fit data."""
from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
import re
from typing import Mapping

from .fit_hierarchy import FitHierarchySnapshot
from .fit_settings import FitSkeletonValidationError
from .joint_labels import JointLabel


@dataclass(frozen=True, slots=True)
class FitJointIkInfo:
    name: str
    start: str
    middle: str
    end: str
    solver: str
    control_count: int
    joints: tuple[str, ...]


def fit_joint_chain(hierarchy: FitHierarchySnapshot, start: str,
                    end: str) -> tuple[str, ...]:
    """asGetIKJoints returns the complete start-to-end ancestor chain."""
    nodes = {node.path: node for node in hierarchy.joints}
    chain = []
    current = end
    visited = set()
    while current in nodes and current not in visited:
        visited.add(current)
        chain.append(current)
        if current == start:
            return tuple(reversed(chain))
        current = nodes[current].dag_parent
    raise FitSkeletonValidationError("Fit IK 起点和末端没有完整的关节父链")


def fit_joint_ik_info(hierarchy: FitHierarchySnapshot,
                      labels: Mapping[str, JointLabel | None],
                      joint: str) -> FitJointIkInfo | None:
    """Keep the source label matching, descendant order and middle selection.

    Names never infer labels. Unlabelled joints remain part of an IK chain but
    cannot declare its start, end or extra spline controls.
    """
    nodes = {node.path: node for node in hierarchy.joints}
    if joint not in nodes:
        raise FitSkeletonValidationError("Fit IK 查询关节不存在：" + joint)
    if set(labels) != set(nodes):
        raise FitSkeletonValidationError("Fit IK 查询需要全部关节的标签状态")

    def label(path):
        value = labels.get(path)
        return value.text if value is not None else ""

    children = {path: [] for path in nodes}
    for node in hierarchy.joints:
        if node.dag_parent in children:
            children[node.dag_parent].append(node.path)
    for paths in children.values():
        paths.sort(key=lambda path: nodes[path].sibling_index)

    def descendants(path):
        # Maya listRelatives -ad reports grandchildren before their parents.
        result = []
        visiting = set()

        def visit(parent):
            if parent in visiting:
                raise FitSkeletonValidationError("Fit IK 查询遇到循环父链")
            visiting.add(parent)
            for child in children[parent]:
                visit(child)
                result.append(child)
            visiting.remove(parent)

        visit(path)
        return result

    start = None
    current = joint
    visited = set()
    while current in nodes and current not in visited:
        visited.add(current)
        text = label(current)
        if current != joint and ("Hand" in text or "Chest" in text):
            break
        if ("Shoulder" in text or "Hip" in text or "Root" in text
                or text.startswith("0")):
            start = current
            break
        current = nodes[current].dag_parent
    if start is None:
        return None

    start_label = label(start)
    nested_spline_joints = set()
    end = None
    for path in reversed(descendants(joint) + [joint]):
        text = label(path)
        if (("Hand" in text and "Shoulder" in start_label)
                or (("Foot" in text or "Toes" in text)
                    and "Hip" in start_label)
                or ("Chest" in text and "Root" in start_label)):
            end = path
            break
        if text.startswith("0") and path != joint:
            nested_spline_joints.update(descendants(path))
        if (fnmatchcase(text, "*[1-9]*") and "0" in start_label
                and path not in nested_spline_joints):
            end = path
    if end is None:
        return None
    chain = fit_joint_chain(hierarchy, start, end)
    control_count = 2 + sum("Mid" in label(path)
                            or fnmatchcase(label(path), "[0-9]*")
                            for path in chain[1:-1])
    name = ""
    solver = "ikRPsolver"
    if "Shoulder" in start_label:
        name = "Arm" + start_label.replace("Shoulder", "", 1)
    if "Hip" in start_label:
        name = "Leg" + start_label.replace("Hip", "", 1)
    if "Root" in start_label:
        name = "Spine" + start_label.replace("Root", "", 1)
        solver = "ikSplineSolver"
    if "0" in start_label and not fnmatchcase(start_label, "*[0-9]0*"):
        # MEL substitute removes the numeric run, preserving the suffix
        # assigned to duplicate starts: 0A / 1A is SplineA.
        name = "Spline" + re.sub(r"[0-9]+", "", start_label, count=1)
        solver = "ikSplineSolver"
    middle = chain[len(chain) - 1 - len(chain) // 2]
    return FitJointIkInfo(name, start, middle, end, solver,
                          control_count, chain)
