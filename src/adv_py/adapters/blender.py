from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import importlib.util
from typing import Iterable, Iterator

from adv_py.core.matrix import almost_equal, matrix44, rows
from adv_py.core.model import ConstraintSpec, NodeSpec, RigPlan


@dataclass(frozen=True, slots=True)
class BlenderAdapterStatus:
    available: bool
    implementation: str = "basic-rig-host"
    responsibility: str = "Armature/EditBone/PoseBone、基础约束、事务清理与场景复检"

    @classmethod
    def detect(cls) -> "BlenderAdapterStatus":
        return cls(available=importlib.util.find_spec("bpy") is not None)


class BlenderRigHost:
    """Minimal real Blender adapter using one generated Armature per RigPlan."""

    name = "blender"

    def __init__(self, *, armature_name: str = "PortableRig_Armature") -> None:
        import bpy  # type: ignore[import-not-found]
        from mathutils import Matrix, Vector  # type: ignore[import-not-found]

        self._bpy = bpy
        self._Matrix = Matrix
        self._Vector = Vector
        self._armature_name = armature_name
        self._armature_object = None
        self._nodes: dict[str, NodeSpec] = {}
        self._objects: dict[str, object] = {}
        self._constraint_owners: list[object] = []
        self._active_created: list[str] | None = None
        self._last_created: tuple[str, ...] = ()

    @contextmanager
    def transaction(self, label: str) -> Iterator[None]:
        del label
        if self._active_created is not None:
            raise RuntimeError("BlenderRigHost 不支持嵌套事务")
        self._active_created = []
        try:
            yield
        except Exception:
            self._remove_objects(reversed(self._active_created))
            raise
        else:
            self._last_created = tuple(self._active_created)
        finally:
            self._ensure_object_mode()
            self._active_created = None

    def preflight(self, plan: RigPlan) -> tuple[str, ...]:
        errors: list[str] = []
        if self._bpy.data.objects.get(self._armature_name) is not None:
            errors.append(f"场景中已存在 Armature {self._armature_name!r}")
        by_key = {node.key: node for node in plan.nodes}
        for node in plan.nodes:
            if node.kind != "joint" and self._bpy.data.objects.get(node.name) is not None:
                errors.append(f"场景中已存在对象 {node.name!r}")
            if node.parent is not None:
                parent = by_key[node.parent]
                if (node.kind == "joint") != (parent.kind == "joint"):
                    errors.append(f"Blender 首版不支持混合父级：{node.key!r} -> {parent.key!r}")
        for constraint in plan.constraints:
            if len(constraint.sources) != 1:
                errors.append("Blender 首版约束只支持一个 source")
            if constraint.maintain_offset:
                errors.append("Blender 首版约束暂不支持 maintain_offset=True")
        return tuple(errors)

    def create_node(self, node: NodeSpec) -> None:
        self._nodes[node.key] = node
        if node.kind == "joint":
            armature = self._ensure_armature()
            self._activate_armature("EDIT")
            bone = armature.data.edit_bones.new(node.name)
            transform = self._Matrix(rows(node.world_matrix))
            head = transform.translation
            direction = transform.to_3x3() @ self._Vector((0.0, 1.0, 0.0))
            roll_axis = transform.to_3x3() @ self._Vector((0.0, 0.0, 1.0))
            bone.head = head
            bone.tail = head + direction.normalized() * node.extent
            bone.align_roll(roll_axis)
        else:
            self._ensure_object_mode()
            obj = self._bpy.data.objects.new(node.name, None)
            obj.empty_display_type = "CIRCLE" if node.kind == "control" else "PLAIN_AXES"
            obj.matrix_world = self._Matrix(rows(node.world_matrix))
            obj["portable_rig_kind"] = node.kind
            self._bpy.context.scene.collection.objects.link(obj)
            self._objects[node.key] = obj
            self._remember(obj.name)

    def parent_node(self, child_key: str, parent_key: str) -> None:
        child = self._nodes[child_key]
        parent = self._nodes[parent_key]
        if child.kind == "joint" and parent.kind == "joint":
            armature = self._ensure_armature()
            self._activate_armature("EDIT")
            armature.data.edit_bones[child.name].parent = armature.data.edit_bones[parent.name]
            return
        self._ensure_object_mode()
        child_obj = self._objects[child_key]
        world_matrix = child_obj.matrix_world.copy()
        child_obj.parent = self._objects[parent_key]
        child_obj.matrix_world = world_matrix

    def create_constraint(self, constraint: ConstraintSpec) -> None:
        self._ensure_object_mode()
        target_node = self._nodes[constraint.target]
        if target_node.kind == "joint":
            self._activate_armature("POSE")
            owner = self._armature_object.pose.bones[target_node.name]
        else:
            owner = self._objects[constraint.target]

        blender_types = {
            "parent": "COPY_TRANSFORMS",
            "point": "COPY_LOCATION",
            "orient": "COPY_ROTATION",
            "scale": "COPY_SCALE",
        }
        created = owner.constraints.new(blender_types[constraint.kind])
        created.name = f"PortableRig_{constraint.kind}"
        source_key = constraint.sources[0]
        source_node = self._nodes[source_key]
        if source_node.kind == "joint":
            created.target = self._armature_object
            created.subtarget = source_node.name
        else:
            created.target = self._objects[source_key]
        if hasattr(created, "owner_space"):
            created.owner_space = "WORLD"
        if hasattr(created, "target_space"):
            created.target_space = "WORLD"
        self._constraint_owners.append(owner)

    def verify(self, plan: RigPlan) -> tuple[str, ...]:
        self._ensure_object_mode()
        errors: list[str] = []
        armature = self._armature_object
        for node in plan.nodes:
            if node.kind == "joint":
                bone = armature.data.bones.get(node.name) if armature else None
                if bone is None:
                    errors.append(f"缺少骨骼 {node.key!r}")
                    continue
                actual = matrix44(value for row in bone.matrix_local for value in row)
                if not almost_equal(actual, node.world_matrix, tolerance=1e-4):
                    errors.append(f"骨骼 {node.key!r} 的世界矩阵不一致")
                actual_parent = bone.parent.name if bone.parent else None
                expected_parent = self._nodes[node.parent].name if node.parent else None
            else:
                obj = self._objects.get(node.key)
                if obj is None or self._bpy.data.objects.get(obj.name) is None:
                    errors.append(f"缺少对象 {node.key!r}")
                    continue
                actual = matrix44(value for row in obj.matrix_world for value in row)
                if not almost_equal(actual, node.world_matrix, tolerance=1e-4):
                    errors.append(f"对象 {node.key!r} 的世界矩阵不一致")
                actual_parent = obj.parent.name if obj.parent else None
                expected_parent = self._objects[node.parent].name if node.parent else None
            if actual_parent != expected_parent:
                errors.append(f"节点 {node.key!r} 的父级不一致")
        expected_constraints = len(plan.constraints)
        actual_constraints = sum(len(owner.constraints) for owner in self._constraint_owners)
        if actual_constraints != expected_constraints:
            errors.append(f"约束数量不一致：期望 {expected_constraints}，实际 {actual_constraints}")
        return tuple(errors)

    def rollback_last(self) -> None:
        if not self._last_created:
            raise RuntimeError("没有可回滚的 Blender 构建事务")
        self._ensure_object_mode()
        self._remove_objects(reversed(self._last_created))
        self._nodes.clear()
        self._objects.clear()
        self._constraint_owners.clear()
        self._armature_object = None
        self._last_created = ()

    def _ensure_armature(self):
        if self._armature_object is None:
            data = self._bpy.data.armatures.new(f"{self._armature_name}_Data")
            obj = self._bpy.data.objects.new(self._armature_name, data)
            self._bpy.context.scene.collection.objects.link(obj)
            self._armature_object = obj
            self._remember(obj.name)
        return self._armature_object

    def _activate_armature(self, mode: str) -> None:
        self._ensure_object_mode()
        armature = self._ensure_armature()
        self._bpy.context.view_layer.objects.active = armature
        armature.select_set(True)
        self._bpy.ops.object.mode_set(mode=mode)

    def _ensure_object_mode(self) -> None:
        active = self._bpy.context.view_layer.objects.active
        if active is not None and active.mode != "OBJECT":
            self._bpy.ops.object.mode_set(mode="OBJECT")

    def _remember(self, object_name: str) -> None:
        if self._active_created is None:
            raise RuntimeError("场景修改必须发生在事务内")
        self._active_created.append(object_name)

    def _remove_objects(self, names: Iterable[str]) -> None:
        self._ensure_object_mode()
        for name in names:
            obj = self._bpy.data.objects.get(name)
            if obj is None:
                continue
            data = obj.data if obj.type == "ARMATURE" else None
            self._bpy.data.objects.remove(obj, do_unlink=True)
            if data is not None and data.users == 0:
                self._bpy.data.armatures.remove(data)

