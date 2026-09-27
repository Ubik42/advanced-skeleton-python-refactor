"""Plan the 6.925 Model Clean OBJ round trip without Maya operations."""
from __future__ import annotations

from dataclasses import dataclass
import re


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ModelCleanNode:
    path: str
    kind: str  # group or mesh
    shape_name: str | None = None
    vertex_count: int = 0
    face_count: int = 0
    uv_sets: tuple[str, ...] = ()
    material_slots: tuple[str, ...] = ()
    user_attributes: tuple[str, ...] = ()
    referenced: bool = False
    instanced: bool = False


@dataclass(frozen=True, slots=True)
class ModelCleanScene:
    scene_name: str
    geo_root: str
    nodes: tuple[ModelCleanNode, ...]
    other_scene_nodes: tuple[str, ...] = ()
    reference_files: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ModelCleanItem:
    source_path: str
    target_path: str
    kind: str
    obj_key: str | None
    expected_shape_name: str | None
    vertex_count: int
    face_count: int
    uv_sets: tuple[str, ...]
    material_slots: tuple[str, ...]
    user_attributes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ModelCleanPlan:
    scene_name: str
    geo_root: str
    items: tuple[ModelCleanItem, ...]
    discarded_scene_nodes: tuple[str, ...]
    discarded_reference_files: tuple[str, ...]

    @property
    def meshes(self) -> tuple[ModelCleanItem, ...]:
        return tuple(item for item in self.items if item.kind == "mesh")


@dataclass(frozen=True, slots=True)
class ModelCleanArchiveItem:
    obj_key: str
    obj_sha256: str
    vertex_count: int
    face_count: int
    uv_sets: tuple[str, ...]
    material_slots: tuple[str, ...]
    user_attributes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ModelCleanArchive:
    location: str
    scene_payload_sha256: str
    material_payload_sha256: str
    uv_payload_sha256: str
    attribute_payload_sha256: str
    items: tuple[ModelCleanArchiveItem, ...]


def plan_model_clean(scene: ModelCleanScene) -> ModelCleanPlan:
    """Resolve scene names and preserve the information OBJ cannot carry."""
    if scene.geo_root != "|geo" or not scene.nodes:
        raise ValueError("Model Clean 需要唯一的顶层 |geo 组")
    by_path = {node.path: node for node in scene.nodes}
    if len(by_path) != len(scene.nodes):
        raise ValueError("Model Clean 层级包含重复 DAG 路径")
    root = by_path.get("|geo")
    if root is None or root.kind != "group":
        raise ValueError("Model Clean 顶层 |geo 必须是空 Transform 组")
    if any("polySurface1" == path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
           for path in (*by_path, *scene.other_scene_nodes)):
        raise ValueError("Model Clean 保留名 polySurface1 已被占用")
    names = set()
    items = []
    target_paths = {}
    for node in scene.nodes:
        if (not node.path.startswith("|geo")
                or (node.path != "|geo" and
                    not node.path.startswith("|geo|"))):
            raise ValueError("Model Clean 几何对象必须位于 |geo 下")
        if node.kind not in ("group", "mesh"):
            raise ValueError("Model Clean 仅支持组和多边形网格")
        if node.referenced or node.instanced:
            raise ValueError("Model Clean 几何对象不能属于引用或实例")
        parent = node.path.rsplit("|", 1)[0]
        if node.path != "|geo" and parent not in target_paths:
            raise ValueError("Model Clean 层级必须按父级先于子级排列")
        if node.kind == "mesh":
            if (not node.shape_name or type(node.vertex_count) is not int
                    or node.vertex_count < 1 or type(node.face_count) is not int
                    or node.face_count < 1):
                raise ValueError("Model Clean 网格 Shape 或拓扑无效")
        elif (node.shape_name is not None or node.vertex_count
              or node.face_count or node.uv_sets or node.material_slots):
            raise ValueError("Model Clean 组不能携带网格 Shape 与拓扑")
        if (len(set(node.uv_sets)) != len(node.uv_sets)
                or len(set(node.user_attributes)) != len(node.user_attributes)
                or any(not value for value in (
                    *node.uv_sets, *node.material_slots,
                    *node.user_attributes))):
            raise ValueError("Model Clean UV、材质或用户属性记录无效")
        leaf = node.path.rsplit("|", 1)[-1].rsplit(":", 1)[-1]
        if not leaf or (node.path == "|geo" and leaf != "geo"):
            raise ValueError("Model Clean 对象名称无效")
        target_name = leaf
        suffix = 0
        while target_name in names:
            target_name = f"{leaf}{suffix}"
            suffix += 1
        names.add(target_name)
        target_path = ("|geo" if node.path == "|geo" else
                       target_paths[parent] + "|" + target_name)
        target_paths[node.path] = target_path
        obj_key = (f"mesh-{len(items):04d}" if node.kind == "mesh" else None)
        items.append(ModelCleanItem(
            node.path, target_path, node.kind, obj_key,
            node.shape_name.rsplit(":", 1)[-1] if node.shape_name else None,
            node.vertex_count, node.face_count, node.uv_sets,
            node.material_slots, node.user_attributes))
    if not any(item.kind == "mesh" for item in items):
        raise ValueError("Model Clean 的 |geo 下没有多边形网格")
    return ModelCleanPlan(scene.scene_name, scene.geo_root, tuple(items),
                          scene.other_scene_nodes, scene.reference_files)


def validate_model_clean_archive(
    plan: ModelCleanPlan, archive: ModelCleanArchive,
) -> None:
    if not archive.location:
        raise ValueError("Model Clean 临时归档位置缺失")
    digests = (archive.scene_payload_sha256,
               archive.material_payload_sha256,
               archive.uv_payload_sha256,
               archive.attribute_payload_sha256)
    if any(_SHA256.fullmatch(digest) is None for digest in digests):
        raise ValueError("Model Clean 临时场景、材质、UV 或属性归档缺少摘要")
    expected = {item.obj_key: item for item in plan.meshes}
    actual = {item.obj_key: item for item in archive.items}
    if (len(actual) != len(archive.items) or set(actual) != set(expected)):
        raise ValueError("Model Clean OBJ 归档与计划网格不一致")
    for key, original in expected.items():
        item = actual[key]
        if (_SHA256.fullmatch(item.obj_sha256) is None
                or item.vertex_count != original.vertex_count
                or item.face_count != original.face_count
                or item.uv_sets != original.uv_sets
                or item.material_slots != original.material_slots
                or item.user_attributes != original.user_attributes):
            raise ValueError("Model Clean 归档未保留网格结构、UV、材质或属性："
                             + original.source_path)


def validate_model_clean_result(
    plan: ModelCleanPlan, scene: ModelCleanScene,
) -> None:
    expected = {item.target_path: item for item in plan.items}
    actual = {node.path: node for node in scene.nodes}
    if (scene.geo_root != "|geo" or len(actual) != len(scene.nodes)
            or set(actual) != set(expected)):
        raise ValueError("Model Clean 重建后的 geo 层级与计划不一致")
    for path, item in expected.items():
        node = actual[path]
        if (node.kind != item.kind
                or node.shape_name != item.expected_shape_name
                or node.vertex_count != item.vertex_count
                or node.face_count != item.face_count
                or node.uv_sets != item.uv_sets
                or node.material_slots != item.material_slots
                or node.user_attributes != item.user_attributes):
            raise ValueError("Model Clean 重建后网格或属性不完整：" + path)
