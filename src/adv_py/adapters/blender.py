from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import importlib.util
from typing import Iterable, Iterator

from adv_py.core.matrix import almost_equal, matrix44, rows
from adv_py.core.model import ConstraintSpec, LimbSpec, NodeSpec, RigPlan


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
        self._bind_armature_name = f"{armature_name}_Bind"
        self._armature_object = None
        self._bind_armature_object = None
        self._bind_joint_keys: set[str] = set()
        self._joint_armatures: dict[str, object] = {}
        self._nodes: dict[str, NodeSpec] = {}
        self._objects: dict[str, object] = {}
        self._constraints: list[object] = []
        self._limb_artifacts: dict[str, dict[str, object]] = {}
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
        self._bind_joint_keys = {
            key for limb in plan.limbs for key in limb.bind_chain
        }
        if self._bpy.data.objects.get(self._armature_name) is not None:
            errors.append(f"场景中已存在 Armature {self._armature_name!r}")
        if self._bind_joint_keys and self._bpy.data.objects.get(
            self._bind_armature_name
        ) is not None:
            errors.append(f"场景中已存在 Armature {self._bind_armature_name!r}")
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
            armature = (
                self._ensure_bind_armature()
                if node.key in self._bind_joint_keys
                else self._ensure_armature()
            )
            self._joint_armatures[node.key] = armature
            self._activate_armature(armature, "EDIT")
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
            armature = self._joint_armatures[child_key]
            if armature is not self._joint_armatures[parent_key]:
                raise RuntimeError("Blender 不支持跨 Armature 的骨骼父级")
            self._activate_armature(armature, "EDIT")
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
            owner_armature = self._joint_armatures[constraint.target]
            self._activate_armature(owner_armature, "POSE")
            owner = owner_armature.pose.bones[target_node.name]
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
            created.target = self._joint_armatures[source_key]
            created.subtarget = source_node.name
        else:
            created.target = self._objects[source_key]
        if hasattr(created, "owner_space"):
            created.owner_space = "WORLD"
        if hasattr(created, "target_space"):
            created.target_space = "WORLD"
        self._constraints.append(created)

    def create_limb(self, limb: LimbSpec) -> None:
        self._ensure_object_mode()
        settings = self._objects[limb.settings]
        settings[limb.blend_attribute] = 0.0
        settings.id_properties_ui(limb.blend_attribute).update(
            min=0.0, max=1.0, soft_min=0.0, soft_max=1.0
        )

        self._activate_armature(self._armature_object, "POSE")
        armature = self._armature_object
        bind_armature = self._bind_armature_object
        fk_constraints: list[object] = []
        for control_key, joint_key in zip(limb.fk_controls, limb.fk_chain):
            owner = armature.pose.bones[self._nodes[joint_key].name]
            created = owner.constraints.new("COPY_TRANSFORMS")
            created.name = f"PortableRig_{limb.key}_FK"
            created.target = self._objects[control_key]
            created.owner_space = "WORLD"
            created.target_space = "WORLD"
            fk_constraints.append(created)
            self._constraints.append(created)

        # A three-joint Maya chain describes two solved segments. Blender bones
        # are segments, so the second bone's tail is the equivalent end pivot.
        ik_owner = armature.pose.bones[self._nodes[limb.ik_chain[-2]].name]
        ik_constraint = ik_owner.constraints.new("IK")
        ik_constraint.name = f"PortableRig_{limb.key}_IK"
        ik_constraint.target = self._objects[limb.ik_target]
        ik_constraint.pole_target = self._objects[limb.pole_vector]
        ik_constraint.chain_count = 2
        ik_constraint.influence = 0.0
        self._constraints.append(ik_constraint)

        blend_constraints: list[tuple[object, object]] = []
        for bind_key, fk_key, ik_key in zip(
            limb.bind_chain, limb.fk_chain, limb.ik_chain
        ):
            owner = bind_armature.pose.bones[self._nodes[bind_key].name]
            fk_constraint = owner.constraints.new("COPY_TRANSFORMS")
            fk_constraint.name = f"PortableRig_{limb.key}_BindFK"
            fk_constraint.target = armature
            fk_constraint.subtarget = self._nodes[fk_key].name
            fk_constraint.owner_space = "POSE"
            fk_constraint.target_space = "POSE"
            fk_constraint.influence = 1.0

            ik_constraint_for_bind = owner.constraints.new("COPY_TRANSFORMS")
            ik_constraint_for_bind.name = f"PortableRig_{limb.key}_BindIK"
            ik_constraint_for_bind.target = armature
            ik_constraint_for_bind.subtarget = self._nodes[ik_key].name
            ik_constraint_for_bind.owner_space = "POSE"
            ik_constraint_for_bind.target_space = "POSE"
            ik_constraint_for_bind.influence = 0.0
            blend_constraints.append((fk_constraint, ik_constraint_for_bind))
            self._constraints.extend((fk_constraint, ik_constraint_for_bind))

        # Register drivers only after the complete constraint graph exists.
        # Evaluating a half-built pose graph can permanently invalidate drivers
        # for the remainder of the Blender session.
        self._ensure_object_mode()
        self._add_blend_driver(
            ik_constraint, settings, limb.blend_attribute, "blend"
        )
        for fk_constraint, ik_constraint_for_bind in blend_constraints:
            self._add_blend_driver(
                fk_constraint, settings, limb.blend_attribute, "1.0 - blend"
            )
            self._add_blend_driver(
                ik_constraint_for_bind, settings, limb.blend_attribute, "blend"
            )
        settings.update_tag()
        armature.update_tag()
        bind_armature.update_tag()
        self._bpy.context.view_layer.update()

        self._limb_artifacts[limb.key] = {
            "settings": settings,
            "ik_constraint": ik_constraint,
            "fk_constraints": tuple(fk_constraints),
            "blend_constraints": tuple(blend_constraints),
        }

    def verify(self, plan: RigPlan) -> tuple[str, ...]:
        self._ensure_object_mode()
        errors: list[str] = []
        for node in plan.nodes:
            if node.kind == "joint":
                armature = self._joint_armatures.get(node.key)
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
        for limb in plan.limbs:
            artifacts = self._limb_artifacts.get(limb.key)
            if artifacts is None:
                errors.append(f"缺少 Limb {limb.key!r}")
                continue
            settings = artifacts["settings"]
            if limb.blend_attribute not in settings:
                errors.append(f"Limb {limb.key!r} 缺少 blend 属性")
            if len(artifacts["fk_constraints"]) != 3:
                errors.append(f"Limb {limb.key!r} 的 FK 约束数量不一致")
            if len(artifacts["blend_constraints"]) != 3:
                errors.append(f"Limb {limb.key!r} 的 blend 约束数量不一致")
        expected_constraints = len(plan.constraints) + len(plan.limbs) * 10
        if len(self._constraints) != expected_constraints:
            errors.append(
                f"约束数量不一致：期望 {expected_constraints}，实际 {len(self._constraints)}"
            )
        driver_curves = []
        for armature in (self._armature_object, self._bind_armature_object):
            if armature is not None and armature.animation_data is not None:
                driver_curves.extend(armature.animation_data.drivers)
        expected_drivers = len(plan.limbs) * 7
        if len(driver_curves) != expected_drivers:
            errors.append(
                f"驱动数量不一致：期望 {expected_drivers}，实际 {len(driver_curves)}"
            )
        if any(not curve.driver.is_valid for curve in driver_curves):
            errors.append("存在求值失败的 Blender 驱动")
        return tuple(errors)

    def rollback_last(self) -> None:
        if not self._last_created:
            raise RuntimeError("没有可回滚的 Blender 构建事务")
        self._ensure_object_mode()
        self._remove_objects(reversed(self._last_created))
        self._nodes.clear()
        self._objects.clear()
        self._constraints.clear()
        self._limb_artifacts.clear()
        self._joint_armatures.clear()
        self._bind_joint_keys.clear()
        self._armature_object = None
        self._bind_armature_object = None
        self._last_created = ()

    def _ensure_armature(self):
        if self._armature_object is None:
            data = self._bpy.data.armatures.new(f"{self._armature_name}_Data")
            obj = self._bpy.data.objects.new(self._armature_name, data)
            self._bpy.context.scene.collection.objects.link(obj)
            self._armature_object = obj
            self._remember(obj.name)
        return self._armature_object

    def _ensure_bind_armature(self):
        if self._bind_armature_object is None:
            data = self._bpy.data.armatures.new(f"{self._bind_armature_name}_Data")
            obj = self._bpy.data.objects.new(self._bind_armature_name, data)
            self._bpy.context.scene.collection.objects.link(obj)
            self._bind_armature_object = obj
            self._remember(obj.name)
        return self._bind_armature_object

    def _activate_armature(self, armature, mode: str) -> None:
        self._ensure_object_mode()
        for selected in tuple(self._bpy.context.selected_objects):
            selected.select_set(False)
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

    @staticmethod
    def _add_blend_driver(constraint, settings, attribute: str, expression: str) -> None:
        curve = constraint.driver_add("influence")
        driver = curve.driver
        driver.type = "SCRIPTED"
        variable = driver.variables.new()
        variable.name = "blend"
        variable.type = "SINGLE_PROP"
        target = variable.targets[0]
        target.id = settings
        target.data_path = f'["{attribute}"]'
        driver.expression = expression

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
