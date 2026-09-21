from math import sqrt

from adv_py.core.fit_settings import FitSkeletonValidationError


class MayaBodyControlSpacesMixin:
    def _space_command(self, spec):
        return self._cmds.orientConstraint if spec.rotation_only else self._cmds.parentConstraint

    def _space_editable(self, path):
        c = self._cmds
        if ((c.ls(path, long=True) or []) != [path] or c.referenceQuery(path, isNodeReferenced=True)
                or any(c.lockNode(path, query=True, lock=True) or [])):
            raise FitSkeletonValidationError(f"控制空间节点不可编辑：{path}")

    def _space_scale(self, path):
        matrix, axes = self._spine_world_frame(path)
        scales = tuple(sqrt(sum(v*v for v in matrix[i:i+3])) for i in (0, 4, 8))
        x, y, z = axes
        determinant = x[0]*(y[1]*z[2]-y[2]*z[1])-x[1]*(y[0]*z[2]-y[2]*z[0])+x[2]*(y[0]*z[1]-y[1]*z[0])
        if min(scales) < 1e-5 or max(scales)-min(scales) > 1e-4 or abs(determinant-1) > 1e-4:
            raise FitSkeletonValidationError("控制空间只支持正等比缩放")

    def _create_control_space_constraint(self, spec, target, name, mode):
        c = self._cmds
        created = self._space_command(spec)(spec.source(mode), target, maintainOffset=True, name=name)
        if len(created) != 1 or created[0].rsplit("|", 1)[-1] != name:
            raise RuntimeError("控制空间约束名称漂移")
        c.addAttr(created[0], longName="advPySpaceOwner", dataType="string")
        c.setAttr(created[0] + ".advPySpaceOwner", "adv_py.control_space.v1", type="string", lock=True)

    def create_body_control_spaces(self, plan):
        self._require_transaction()
        c = self._cmds
        for spec in plan.spaces:
            for path in (spec.body_source, spec.global_source, *spec.targets):
                self._space_editable(path)
                self._space_scale(path)
            for target in spec.targets:
                self._preflight_torso_channels(target, spec.attributes)
            if any(self.find_name_collisions(name) for name in spec.constraint_names):
                raise FitSkeletonValidationError("控制空间名称已占用")
        before = self.capture_control_space_pose(plan)
        selection = c.ls(selection=True, long=True) or []
        try:
            self._transaction_changed = True
            for spec in plan.spaces:
                for target, name in zip(spec.targets, spec.constraint_names):
                    self._create_control_space_constraint(spec, target, name, spec.initial_mode)
                self.capture_control_space_mode(spec)
            from adv_py.core.body_control_spaces import control_space_pose_error, SPACE_TOLERANCE
            if control_space_pose_error(before, self.capture_control_space_pose(plan)) > SPACE_TOLERANCE:
                raise RuntimeError("安装控制空间改变了角色姿态")
        finally:
            c.select(selection, replace=True) if selection else c.select(clear=True)

    def capture_control_space_mode(self, spec):
        c = self._cmds
        modes = []
        command = self._space_command(spec)
        expected_type = "orientConstraint" if spec.rotation_only else "parentConstraint"
        for target, name in zip(spec.targets, spec.constraint_names):
            nodes = c.ls(name, long=True) or []
            if (len(nodes) != 1 or c.nodeType(nodes[0]) != expected_type
                    or not c.objExists(name + ".advPySpaceOwner")
                    or c.getAttr(name + ".advPySpaceOwner") != "adv_py.control_space.v1"):
                raise FitSkeletonValidationError("控制空间约束类型或归属无效")
            node = nodes[0]
            self._space_editable(node)
            if c.listRelatives(node, children=True):
                raise FitSkeletonValidationError("控制空间约束包含外部子节点")
            sources = tuple(self._resolve_connected_node(n) for n in (command(node, query=True, targetList=True) or []))
            if sources == (spec.body_source,):
                modes.append("body")
            elif sources == (spec.global_source,):
                modes.append("global")
            else:
                raise FitSkeletonValidationError("控制空间约束来源已变化")
            incoming = {self._resolve_connected_node(n) for n in (c.listConnections(node, source=True, destination=False) or [])}
            if incoming - {node, target, sources[0]}:
                raise FitSkeletonValidationError("控制空间约束存在动画或外部输入")
            weights = command(node, query=True, weightAliasList=True) or []
            if len(weights) != 1 or abs(c.getAttr(node + "." + weights[0]) - 1.0) > 1e-6:
                raise FitSkeletonValidationError("控制空间约束权重必须为 1")
            for attr in spec.attributes:
                output = "constraint" + attr[0].upper() + attr[1:]
                if not c.isConnected(name + "." + output, target + "." + attr):
                    raise FitSkeletonValidationError("控制空间约束输出已变化")
            destinations = set()
            for plug in c.listConnections(node, source=False, destination=True, plugs=True) or []:
                path, attr = plug.split(".", 1)
                path = self._resolve_connected_node(path)
                if path != node:
                    destinations.add((path, attr))
            if destinations != {(target, attr) for attr in spec.attributes}:
                raise FitSkeletonValidationError("控制空间约束存在外部消费")
        if len(set(modes)) != 1:
            raise FitSkeletonValidationError("同组目标与 Pole 的空间状态不一致")
        return modes[0]

    def preflight_control_space_switch(self, spec):
        c = self._cmds
        mode = self.capture_control_space_mode(spec)
        if c.ls(type="animLayer") or c.currentUnit(query=True, angle=True) != "deg":
            raise FitSkeletonValidationError("当前空间切换要求 degree 单位且无动画层")
        for path in (spec.body_source, spec.global_source, *spec.targets):
            self._space_editable(path)
            self._space_scale(path)
        for target in spec.targets:
            if any(c.getAttr(target + "." + attr, lock=True) for attr in spec.attributes):
                raise FitSkeletonValidationError("控制空间 offset 通道锁定")
        return mode

    def capture_control_space_pose(self, plan):
        body = self.capture_body_skeleton(plan.body_root)
        paths = tuple(j.path for j in body.joints) + tuple(target for spec in plan.spaces for target in spec.targets)
        return tuple((path, self._spine_world_frame(path)[0]) for path in paths)

    def switch_control_space(self, spec, mode):
        self._require_transaction()
        c = self._cmds
        frames = tuple(self._spine_world_frame(path)[0] for path in spec.targets)
        selection = c.ls(selection=True, long=True) or []
        try:
            self._transaction_changed = True
            c.delete(spec.constraint_names)
            for target, name, matrix in zip(spec.targets, spec.constraint_names, frames):
                if not spec.rotation_only:
                    c.xform(target, worldSpace=True, translation=matrix[12:15])
                self._spine_set_world_rotation(target, matrix)
                self._create_control_space_constraint(spec, target, name, mode)
        finally:
            c.select(selection, replace=True) if selection else c.select(clear=True)
