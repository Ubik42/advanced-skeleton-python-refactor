from __future__ import annotations

from math import sqrt

from adv_py.core.body_spine import spine_roll_degrees, spine_ik_goal_position
from adv_py.core.body_limb_ik import solve_limb_pole_position
from adv_py.core.fit_settings import FitSkeletonValidationError


class MayaBodySpineMixin:
    def ensure_precise_body_spine_solver(self,plan):
        """Upgrade this owned spine only; never edit Maya's shared solver settings."""
        self._require_transaction()
        self.validate_body_spine(plan)
        c=self._cmds
        solver="AdvPy_SpineRPSolver"
        current=c.ikHandle("AdvPy_SpineIKHandle",query=True,solver=True)
        if current==solver:
            return
        if current!="ikRPsolver" or c.objExists(solver):
            raise FitSkeletonValidationError("脊柱求解器有外部替换或名称冲突")
        self._transaction_changed=True
        c.createNode("ikRPsolver",name=solver,skipSelect=True)
        c.addAttr(solver,longName="advPySpineSolverOwner",dataType="string")
        c.setAttr(solver+".advPySpineSolverOwner","adv_py.spine_solver.v1",type="string",lock=True)
        c.addAttr(solver,longName="characterRoot",attributeType="message")
        c.connectAttr(plan.root_path+".message",solver+".characterRoot")
        c.setAttr(solver+".characterRoot",lock=True)
        c.setAttr(solver+".tolerance",1e-10,lock=True)
        c.ikHandle("AdvPy_SpineIKHandle",edit=True,solver=solver)
        self.validate_body_spine(plan)

    def _spine_frame(self, name, parent, position, axes):
        node = self._cmds.createNode("transform", name=name, parent=parent, skipSelect=True)
        node = self._resolve_connected_node(node)
        self._cmds.xform(node, worldSpace=True, matrix=(
            *axes[0], 0, *axes[1], 0, *axes[2], 0, *position, 1,
        ))
        return node

    def prepare_body_spine(self, plan):
        self._require_transaction()
        self._transaction_changed = True
        root = self._cmds.createNode("transform", name=plan.root_path.rsplit("|", 1)[-1],
                                     parent=plan.root_path.rsplit("|", 1)[0], skipSelect=True)
        self._cmds.addAttr(root, longName="advPySpineOwner", dataType="string")
        self._cmds.setAttr(root + ".advPySpineOwner", "adv_py.spine.v1", type="string", lock=True)
        for spec in plan.joints:
            self.create_body_arm_mechanism_joint(spec)
        chest = plan.joints[2]
        self._spine_frame(plan.chest_space.rsplit("|", 1)[-1], plan.chest_space.rsplit("|", 1)[0],
                          chest.world_position, chest.world_axes)

    def create_body_spine(self, plan):
        self._require_transaction()
        self._transaction_changed = True
        c = self._cmds
        for offset, control, pos in (
            (plan.ik_offset, plan.ik_control, plan.joints[2].world_position),
            (plan.pole_offset, plan.pole_control, plan.pole_position),
        ):
            self._spine_frame(offset.rsplit("|", 1)[-1], offset.rsplit("|", 1)[0], pos, plan.joints[2].world_axes)
            ctrl = c.circle(name=control.rsplit("|", 1)[-1], normal=(1, 0, 0), radius=1.5, constructionHistory=False)[0]
            c.parent(ctrl, offset, relative=True)
            for axis in "XYZ":
                c.setAttr(control + ".scale" + axis, lock=True, keyable=False)
        c.addAttr(plan.ik_control, longName="spineIkFk", attributeType="double", minValue=0, maxValue=1, defaultValue=0, keyable=True)
        c.addAttr(plan.ik_control, longName="waistRoll", attributeType="doubleAngle", defaultValue=0, keyable=True)
        c.createNode("transform", name=plan.waist_output.rsplit("|", 1)[-1], parent=plan.joints[4].path, skipSelect=True)
        c.connectAttr(plan.roll_plug, plan.waist_output + ".rotateX")
        c.pointConstraint(plan.pelvis_control, plan.joints[0].path, maintainOffset=False, name="AdvPy_SpineFKRootPoint")
        c.pointConstraint(plan.pelvis_control, plan.joints[3].path, maintainOffset=False, name="AdvPy_SpineIKRootPoint")
        # Preferred bend disambiguates the fully straight synthetic bind chain.
        c.setAttr(plan.joints[4].path + ".preferredAngleZ", -0.1)
        handle, effector = c.ikHandle(name="AdvPy_SpineIKHandle", startJoint=plan.joints[3].path,
                                      endEffector=plan.joints[5].path, solver="ikRPsolver")
        c.rename(effector, "AdvPy_SpineIKEffector")
        c.parent(handle, plan.ik_control)
        c.setAttr("AdvPy_SpineIKHandle.visibility", False)
        c.poleVectorConstraint(plan.pole_control, "AdvPy_SpineIKHandle", name="AdvPy_SpinePoleConstraint")
        c.orientConstraint(plan.ik_control, plan.joints[5].path, maintainOffset=False, name="AdvPy_SpineIKChestOrient")
        c.createNode("reverse", name="AdvPy_SpineReverse")
        c.connectAttr(plan.blend_plug, "AdvPy_SpineReverse.inputX")
        for label, body, fk, ik in (
            ("Waist", plan.body_joints[1], plan.joints[1].path, plan.waist_output),
            ("Chest", plan.body_joints[2], plan.joints[2].path, plan.joints[5].path),
        ):
            for suffix, command in (("Point", c.pointConstraint), ("Orient", c.orientConstraint)):
                node = command(fk, ik, body, maintainOffset=False, name=f"AdvPy_Spine{label}{suffix}")[0]
                weights = command(node, query=True, weightAliasList=True)
                c.connectAttr("AdvPy_SpineReverse.outputX", node + "." + weights[0])
                c.connectAttr(plan.blend_plug, node + "." + weights[1])
                if suffix == "Orient":
                    c.setAttr(node + ".interpType", 2)
        c.parentConstraint(plan.body_joints[2], plan.chest_space, maintainOffset=False, name="AdvPy_SpineChestSpaceParent")
        c.setAttr(plan.root_path + ".visibility", False)
        self.validate_body_spine(plan)

    def validate_body_spine(self, plan):
        c = self._cmds
        if (not c.objExists(plan.root_path + ".advPySpineOwner")
                or c.getAttr(plan.root_path + ".advPySpineOwner") != "adv_py.spine.v1"):
            raise FitSkeletonValidationError("Spine 机制归属标记缺失")
        if any(len(c.ls(name, long=True) or []) != 1 for name in plan.node_names):
            raise FitSkeletonValidationError("Spine 节点集合缺失或名称不唯一")
        solver=c.ikHandle("AdvPy_SpineIKHandle",query=True,solver=True)
        if solver!="ikRPsolver":
            if (solver!="AdvPy_SpineRPSolver" or c.nodeType(solver)!="ikRPsolver"
                    or c.referenceQuery(solver,isNodeReferenced=True)
                    or not c.objExists(solver+".advPySpineSolverOwner")
                    or c.getAttr(solver+".advPySpineSolverOwner")!="adv_py.spine_solver.v1"
                    or not c.isConnected(plan.root_path+".message",solver+".characterRoot")
                    or c.getAttr(solver+".tolerance")!=1e-10
                    or c.listConnections(solver+".tolerance",s=True,d=False)
                    or (c.listConnections(solver,s=False,d=True,plugs=True) or []) != ["AdvPy_SpineIKHandle.ikSolver"]):
                raise FitSkeletonValidationError("独立脊柱求解器归属、精度或输出被修改")
        for joint in plan.joints:
            parents = c.listRelatives(joint.path, parent=True, fullPath=True) or []
            if c.nodeType(joint.path) != "joint" or parents != [joint.parent_path]:
                raise FitSkeletonValidationError("Spine 驱动关节类型或父链改变")
            if not c.isConnected(joint.source_joint + ".message", joint.path + ".advPySourceJoint"):
                raise FitSkeletonValidationError("Spine 驱动关节来源改变")
        def targets(name, command, expected):
            actual = tuple(self._resolve_connected_node(n) for n in (command(name, query=True, targetList=True) or []))
            if actual != expected:
                raise FitSkeletonValidationError(f"Spine 约束来源已变化：{name}")
        for label, body, fk, ik in (
            ("Waist", plan.body_joints[1], plan.joints[1].path, plan.waist_output),
            ("Chest", plan.body_joints[2], plan.joints[2].path, plan.joints[5].path),
        ):
            for suffix, kind, command in (("Point", "translate", c.pointConstraint), ("Orient", "rotate", c.orientConstraint)):
                name = f"AdvPy_Spine{label}{suffix}"
                targets(name, command, (fk, ik))
                weights = command(name, query=True, weightAliasList=True)
                expected = ("AdvPy_SpineReverse.outputX", plan.blend_plug)
                for weight, source in zip(weights, expected):
                    if not c.isConnected(source, name + "." + weight):
                        raise FitSkeletonValidationError("Spine blend 权重接线变化")
                for axis in "XYZ":
                    if not c.isConnected(f"{name}.constraint{kind.title()}{axis}", f"{body}.{kind}{axis}"):
                        raise FitSkeletonValidationError("Spine Body 输出接线变化")
        targets("AdvPy_SpineChestSpaceParent", c.parentConstraint, (plan.body_joints[2],))
        targets("AdvPy_SpinePoleConstraint", c.poleVectorConstraint, (plan.pole_control,))
        targets("AdvPy_SpineIKChestOrient", c.orientConstraint, (plan.ik_control,))
        for role, index in (("FK", 0), ("IK", 3)):
            name = f"AdvPy_Spine{role}RootPoint"
            targets(name, c.pointConstraint, (plan.pelvis_control,))
            for axis in "XYZ":
                if not c.isConnected(name + ".constraintTranslate" + axis, plan.joints[index].path + ".translate" + axis):
                    raise FitSkeletonValidationError("Spine 起点约束输出改变")
        for name, control, joint in zip(
            ("AdvPy_SpineBaseFKOrient", "AdvPy_TorsoSpine1_MOrient", "AdvPy_TorsoChest_MOrient"),
            plan.fk_controls, plan.joints[:3],
        ):
            targets(name, c.orientConstraint, (control,))
            if any(not c.isConnected(name + ".constraintRotate" + axis, joint.path + ".rotate" + axis) for axis in "XYZ"):
                raise FitSkeletonValidationError("Spine FK 驱动输出改变")
        handle = "AdvPy_SpineIKHandle"
        chain = tuple(self._resolve_connected_node(node) for node in c.ikHandle(handle, query=True, jointList=True))
        if (chain != tuple(j.path for j in plan.joints[3:5])
                or (c.listRelatives(handle, parent=True, fullPath=True) or []) != [plan.ik_control]
                or not c.isConnected(plan.blend_plug, "AdvPy_SpineReverse.inputX")):
            raise FitSkeletonValidationError("Spine IK handle 或混合输入结构改变")
        for attr in ("translateX", "translateY", "translateZ", "rotateY", "rotateZ"):
            if abs(c.getAttr(plan.waist_output + "." + attr)) > 1e-6 or c.listConnections(plan.waist_output + "." + attr, source=True, destination=False):
                raise FitSkeletonValidationError("Spine waist 输出层被修改")
        if not c.isConnected(plan.roll_plug, plan.waist_output + ".rotateX"):
            raise FitSkeletonValidationError("Spine waist roll 接线变化")

    def _spine_world_frame(self, node):
        matrix = tuple(float(v) for v in self._cmds.xform(node, query=True, worldSpace=True, matrix=True))
        axes = tuple(self._normalized_vector(matrix[i:i+3]) for i in (0, 4, 8))
        return matrix, axes

    def capture_body_spine_pose(self, plan):
        body = self.capture_body_skeleton(plan.body_joints[0])
        return tuple((j.path, self._spine_world_frame(j.path)[0]) for j in body.joints)

    def preflight_body_spine_match(self, plan, mode):
        self.validate_body_spine(plan)
        c = self._cmds
        if mode not in ("fk", "ik"):
            raise FitSkeletonValidationError("Spine 匹配模式必须是 fk 或 ik")
        if c.ls(type="animLayer"):
            raise FitSkeletonValidationError("Spine 当前姿态匹配暂不支持动画层")
        if c.currentUnit(query=True, angle=True) != "deg":
            raise FitSkeletonValidationError("Spine 当前匹配要求 Maya 角度单位为 degree")
        value = c.getAttr(plan.blend_plug)
        if value not in (0.0, 1.0):
            raise FitSkeletonValidationError("Spine 匹配要求当前 blend 位于 FK 或 IK 端点")
        targets = ([(plan.ik_control, "translate"), (plan.ik_control, "rotate"), (plan.pole_control, "translate")]
                   if mode == "ik" else [(path, "rotate") for path in plan.fk_controls])
        for path, kind in targets:
            self._preflight_torso_channels(path, tuple(kind + axis for axis in "XYZ"))
        self._preflight_torso_channels(plan.ik_control, ("spineIkFk", "waistRoll"))
        matrix, axes = self._spine_world_frame(plan.root_path)
        scales = tuple(sqrt(sum(v*v for v in matrix[i:i+3])) for i in (0, 4, 8))
        x, y, z = axes
        determinant = x[0]*(y[1]*z[2]-y[2]*z[1])-x[1]*(y[0]*z[2]-y[2]*z[0])+x[2]*(y[0]*z[1]-y[1]*z[0])
        if min(scales) < 1e-5 or max(scales)-min(scales) > 1e-4 or abs(determinant-1) > 1e-4:
            raise FitSkeletonValidationError("Spine 匹配只支持正等比缩放")
        if mode == "ik":
            positions = tuple(self._spine_world_frame(j.path)[0][12:15] for j in plan.joints[:3])
            for a, b, rest in zip(positions, positions[1:], plan.lengths):
                length = sqrt(sum((x-y)**2 for x, y in zip(a, b)))
                if abs(length-rest*scales[0]) > 1e-4:
                    raise FitSkeletonValidationError("Spine FK 骨段长度改变，不能直接匹配到固定长度 IK")
        return value

    def _spine_set_world_rotation(self, node, matrix):
        from maya.api import OpenMaya as om
        from math import degrees
        rotation = om.MTransformationMatrix(om.MMatrix(matrix)).rotation()
        self._cmds.xform(node, worldSpace=True, rotation=tuple(degrees(v) for v in rotation))

    def match_body_spine(self, plan, mode):
        self._require_transaction()
        c = self._cmds
        if mode == "ik":
            frames = tuple(self._spine_world_frame(j.path) for j in plan.joints[:3])
            positions = tuple(frame[0][12:15] for frame in frames)
            pole = solve_limb_pole_position(*positions, frames[0][1][1], limb_label="Spine", distance_scale=0.75)
            self._transaction_changed = True
            c.xform(plan.ik_control, worldSpace=True, translation=spine_ik_goal_position(*positions))
            self._spine_set_world_rotation(plan.ik_control, frames[2][0])
            c.xform(plan.pole_control, worldSpace=True, translation=pole)
            c.setAttr(plan.roll_plug, spine_roll_degrees(frames[1][1], self._spine_world_frame(plan.joints[4].path)[1]))
            c.setAttr(plan.blend_plug, 1.0)
        else:
            frames = tuple(self._spine_world_frame(path)[0] for path in (plan.joints[3].path, plan.waist_output, plan.joints[5].path))
            self._transaction_changed = True
            for control, matrix in zip(plan.fk_controls, frames):
                self._spine_set_world_rotation(control, matrix)
            c.setAttr(plan.blend_plug, 0.0)
