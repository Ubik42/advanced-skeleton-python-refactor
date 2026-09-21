from adv_py.core.body_torso import BodySpaceAttachmentState, BodyTorsoSnapshot
from adv_py.core.fit_settings import FitSkeletonValidationError


class MayaBodyTorsoMixin:
    """Torso operations share the owning MayaBodyBuildHost transaction."""

    def _preflight_torso_channels(self, node, attributes):
        matches = self._cmds.ls(node, long=True) or []
        if (matches != [node] or self._cmds.referenceQuery(node, isNodeReferenced=True)
                or any(self._cmds.lockNode(node, query=True, lock=True) or [])):
            raise FitSkeletonValidationError(f"Torso 对象不可编辑：{node}")
        for attr in attributes:
            plug = f"{node}.{attr}"
            if (not self._cmds.getAttr(plug, settable=True)
                    or self._cmds.listConnections(plug, source=True, destination=False)):
                raise FitSkeletonValidationError(f"Torso 通道已有输入或锁定：{plug}")

    def preflight_body_torso(self, plan):
        planned_joints = {j.path for j in plan.spine.joints} if plan.spine else set()
        if plan.spline:
            planned_joints.update(j.path for j in plan.spline.joints)
            for target in plan.spline.body_joints[1:]:
                self._preflight_torso_channels(target,tuple(kind+axis for kind in ('translate','rotate','scale') for axis in 'XYZ'))
        if plan.spine:
            for target in plan.spine.body_joints[1:]:
                self._preflight_torso_channels(target, tuple(kind + axis for kind in ("translate", "rotate") for axis in "XYZ"))
        for spec in plan.controls.controls:
            if spec.driven_joint in planned_joints:
                continue
            attributes = tuple(f"rotate{axis}" for axis in "XYZ")
            if spec.driven_joint == plan.pelvis_translation.target:
                attributes += tuple(f"{kind}{axis}" for kind in ("translate", "scale") for axis in "XYZ")
            self._preflight_torso_channels(spec.driven_joint, attributes)

    def create_body_torso(self, plan):
        self._require_transaction()
        self.preflight_body_torso(plan)
        if any(self.find_name_collisions(name) for name in plan.node_names):
            raise FitSkeletonValidationError("Torso 名称在执行前发生冲突")
        selection = self._cmds.ls(selection=True, long=True) or []
        try:
            self.create_body_control_root(plan.controls.root_name)
            if plan.spine:
                self.prepare_body_spine(plan.spine)
            if plan.spline:
                from .maya_spline import prepare
                prepare(self,plan.spline)
            for spec in plan.controls.controls:
                self._create_body_limb_fk_control(spec, "Torso")
                locked = [f"scale{axis}" for axis in "XYZ"]
                if spec.driven_joint != plan.pelvis_translation.target:
                    locked += [f"translate{axis}" for axis in "XYZ"]
                for attr in locked:
                    self._cmds.setAttr(f"{spec.control_path}.{attr}", lock=True, keyable=False)
            if plan.spine:
                self.create_body_spine(plan.spine)
            if plan.spline:
                from .maya_spline import create
                create(self,plan.spline)
            if plan.head_aim:
                from .maya_head_aim import create
                create(self,plan.head_aim)
            for spec in (plan.pelvis_translation,) + plan.attachments:
                self._preflight_torso_channels(spec.target, spec.attributes)
                command = self._cmds.parentConstraint if spec.kind == "parentConstraint" else self._cmds.pointConstraint
                self._transaction_changed = True
                options = {"skipRotate": ("x", "y", "z")} if spec.translation_only else {}
                nodes = command(spec.source, spec.target, maintainOffset=True, name=spec.name, **options)
                if len(nodes) != 1 or nodes[0].rsplit("|", 1)[-1] != spec.name:
                    raise RuntimeError(f"Torso 约束名称漂移：{spec.name}")
        finally:
            self._cmds.select(selection, replace=True) if selection else self._cmds.select(clear=True)

    def capture_body_torso(self, plan):
        if plan.spline:
            from .maya_spline import audit
            audit(self,plan.spline)
        if plan.head_aim:
            from .maya_head_aim import audit
            audit(self,plan.head_aim.head_control,plan.head_aim.target)
        states = []
        for spec in (plan.pelvis_translation,) + plan.attachments:
            nodes = self._cmds.ls(spec.name, long=True) or []
            if len(nodes) != 1:
                raise RuntimeError(f"Torso 约束缺失或不唯一：{spec.name}")
            kind = self._cmds.nodeType(nodes[0])
            if kind != spec.kind:
                raise RuntimeError(f"Torso 约束类型错误：{spec.name}")
            command = self._cmds.parentConstraint if kind == "parentConstraint" else self._cmds.pointConstraint
            sources = tuple(self._resolve_connected_node(node) for node in (command(nodes[0], query=True, targetList=True) or []))
            inputs = []
            for attr in spec.attributes:
                plug = f"{spec.target}.{attr}"
                connected = self._cmds.listConnections(plug, source=True, destination=False) or []
                owner = None
                if len(connected) == 1:
                    resolved = self._resolve_connected_node(connected[0])
                    owner = spec.name if resolved == nodes[0] else resolved
                inputs.append((plug, owner))
            states.append(BodySpaceAttachmentState(spec.name, kind, sources, tuple(inputs)))
        return BodyTorsoSnapshot(
            self._capture_body_limb_fk_controls(plan.controls, "Torso"), tuple(states),
        )
