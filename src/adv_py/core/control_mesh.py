"""Plan the 6.925 selected-faces-to-control-mesh operation."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ControlMeshSource:
    mesh_shape: str
    control: str
    global_control: str
    faces: tuple[int, ...]
    face_count: int
    mirror_control: str | None = None
    mirror_faces: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class ControlMeshItem:
    mesh_shape: str
    control: str
    faces: tuple[int, ...]
    shape_name: str
    transform_name: str
    global_control: str


def plan_control_mesh(
    source: ControlMeshSource, existing_names: frozenset[str],
) -> tuple[ControlMeshItem, ...]:
    if (not source.mesh_shape or not source.control
            or not source.global_control
            or source.face_count < 1
            or not source.faces):
        raise ValueError("Control Mesh 需要一件网格、若干面及目标控制器")
    if (source.mirror_control is None) != (not source.mirror_faces):
        raise ValueError("Control Mesh 镜像控制器与镜像面必须同时提供")
    if source.mirror_control == source.control:
        raise ValueError("Control Mesh 镜像控制器不能是来源控制器")
    plans = []
    used = set(existing_names)
    targets = [(source.control, source.faces)]
    if source.mirror_control:
        targets.append((source.mirror_control, source.mirror_faces))
    for control, faces in targets:
        if (not faces or len(set(faces)) != len(faces)
                or any(type(face) is not int or face < 0
                       or face >= source.face_count for face in faces)):
            raise ValueError("Control Mesh 面索引无效或重复")
        leaf = control.rsplit("|", 1)[-1]
        for index in range(100):
            name = leaf + "MeshCtrl" + (str(index) if index else "")
            transform_name = (leaf + "MCTransformGeometry"
                              + (str(index) if index else ""))
            if name not in used and transform_name not in used:
                used.update((name, transform_name))
                plans.append(ControlMeshItem(
                    source.mesh_shape, control, tuple(sorted(faces)),
                    name, transform_name,
                    source.global_control))
                break
        else:
            raise ValueError("Control Mesh 当前控制器已用完可用命名序号")
    return tuple(plans)
