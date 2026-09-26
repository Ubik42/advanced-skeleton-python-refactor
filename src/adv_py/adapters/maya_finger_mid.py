"""Maya nodes for final finger-segment deformation influences."""
from __future__ import annotations

from adv_py.core.finger_mid_deform import FingerMidSpec
from .maya_body import MayaBodyBuildHost


class MayaFingerMidHost(MayaBodyBuildHost):
    def create_finger_mid(self, spec: FingerMidSpec) -> None:
        self._require_transaction()
        c = self._cmds
        self._transaction_changed = True
        zero = c.createNode("transform", name=spec.zero_name, parent=spec.parent,
                            skipSelect=True)
        joint = c.createNode("joint", name=spec.name, parent=spec.parent,
                             skipSelect=True)
        if ((c.ls(zero, long=True) or [None])[0] != spec.zero_path
                or (c.ls(joint, long=True) or [None])[0] != spec.path):
            raise RuntimeError("手指辅助节点路径漂移")
        c.addAttr(joint, longName="advPyAuxiliaryInfluenceKind", dataType="string")
        c.setAttr(joint + ".advPyAuxiliaryInfluenceKind",
                  "finger-mid-v1", type="string", lock=True)
        c.xform(joint, worldSpace=True, translation=spec.position)
        c.pointConstraint(spec.tip, joint, maintainOffset=False,
                          name=spec.name + "_pointConstraint")
        orient = c.orientConstraint(zero, spec.tip, joint, maintainOffset=False,
                                    name=spec.name + "_orientConstraint")[0]
        aliases = c.orientConstraint(orient, query=True, weightAliasList=True) or []
        if len(aliases) != 2:
            raise RuntimeError("手指分段双目标约束无效")
        for alias in aliases:
            c.setAttr(orient + "." + alias, 1.0)

    def capture_finger_mid(self, spec: FingerMidSpec
                           ) -> tuple[str, str, tuple[float, float, float]]:
        c = self._cmds
        paths = c.ls(spec.path, long=True, type="joint") or []
        if len(paths) != 1 or not c.objExists(spec.zero_path):
            raise RuntimeError("手指分段节点缺失")
        parent = (c.listRelatives(paths[0], parent=True, fullPath=True) or [""])[0]
        position = tuple(float(value) for value in c.xform(paths[0], query=True,
                          worldSpace=True, translation=True))
        return paths[0], parent, position
