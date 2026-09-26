"""Maya _00/_50 helper hierarchy for weighted volume joint families."""
from __future__ import annotations

from adv_py.core.volume_half_parent import VolumeHalfParentSpec
from .maya_body import MayaBodyBuildHost


class MayaVolumeHalfParentHost(MayaBodyBuildHost):
    def preflight_volume_half_parent(self, spec: VolumeHalfParentSpec) -> None:
        c = self._cmds
        paths = c.ls(spec.parent, long=True, type="joint") or []
        if len(paths) != 1 or paths[0] != spec.parent:
            raise ValueError("体积中间关节父链缺失：" + spec.parent)
        current = c.xform(spec.parent, query=True, worldSpace=True, matrix=True)
        if max(abs(a - b) for a, b in zip(
                current, spec.parent_world_matrix)) > 1e-3:
            raise ValueError("体积中间关节父链静止姿态不匹配：" + spec.name)
        if not c.objExists(spec.target):
            raise ValueError("体积中间关节目标缺失：" + spec.target)

    def create_volume_half_parent(self, spec: VolumeHalfParentSpec) -> None:
        self._require_transaction()
        c = self._cmds
        self._transaction_changed = True
        zero = c.createNode("transform", name=spec.zero_name,
                            parent=spec.parent, skipSelect=True)
        joint = c.createNode("joint", name=spec.name,
                             parent=spec.parent, skipSelect=True)
        if ((c.ls(zero, long=True) or [None])[0] != spec.zero_path
                or (c.ls(joint, long=True) or [None])[0] != spec.path):
            raise RuntimeError("体积中间关节路径漂移：" + spec.name)
        c.setAttr(joint + ".rotateOrder", spec.rotate_order)
        c.setAttr(joint + ".jointOrient", *spec.joint_orient)
        c.xform(joint, worldSpace=True, matrix=spec.world_matrix)
        point = c.pointConstraint(spec.target, joint, maintainOffset=False,
                                  name=spec.name + "_pointConstraint")[0]
        c.setAttr(point + ".offset", *spec.point_offset)
        orient = c.orientConstraint(zero, spec.target, joint,
                                    maintainOffset=False,
                                    name=spec.name + "_orientConstraint")[0]
        aliases = c.orientConstraint(orient, query=True, weightAliasList=True) or []
        if len(aliases) != 2:
            raise RuntimeError("体积中间关节双目标约束无效：" + spec.name)
        for alias in aliases:
            c.setAttr(orient + "." + alias, 1.0)
        c.setAttr(orient + ".offset", *spec.orient_offset)
        c.setAttr(orient + ".interpType", spec.orient_interp_type)
        c.addAttr(joint, longName="advPyAuxiliaryInfluenceKind",
                  dataType="string")
        c.setAttr(joint + ".advPyAuxiliaryInfluenceKind",
                  "volume-half-parent-v1", type="string", lock=True)

    def capture_volume_half_parent(self, spec: VolumeHalfParentSpec
                                   ) -> tuple[str, str, tuple[float, ...]]:
        c = self._cmds
        paths = c.ls(spec.path, long=True, type="joint") or []
        if len(paths) != 1 or not c.objExists(spec.zero_path):
            raise RuntimeError("体积中间关节缺失：" + spec.name)
        parent = (c.listRelatives(paths[0], parent=True, fullPath=True) or [""])[0]
        world = tuple(float(v) for v in c.xform(paths[0], query=True,
                                                 worldSpace=True, matrix=True))
        return paths[0], parent, world
