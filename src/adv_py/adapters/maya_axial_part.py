"""Maya construction of exact-name axial deformation influences."""
from __future__ import annotations

from adv_py.core.axial_part_deform import AxialPartSpec
from .maya_body import MayaBodyBuildHost


class MayaAxialPartHost(MayaBodyBuildHost):
    def create_axial_part(self, spec: AxialPartSpec) -> None:
        self._require_transaction()
        c = self._cmds
        self._transaction_changed = True
        joint = c.createNode("joint", name=spec.name, parent=spec.parent,
                             skipSelect=True)
        joint = (c.ls(joint, long=True) or [joint])[0]
        if joint != spec.path:
            raise RuntimeError("轴向分段关节路径漂移")
        c.addAttr(joint, longName="advPyAuxiliaryInfluenceKind",
                  dataType="string")
        c.setAttr(joint + ".advPyAuxiliaryInfluenceKind",
                  "axial-part-v1", type="string", lock=True)
        c.xform(joint, worldSpace=True, translation=spec.position)
        point = c.pointConstraint(spec.start, spec.end, joint,
                                  maintainOffset=False,
                                  name=spec.name + "_pointConstraint")[0]
        orient = c.orientConstraint(spec.start, spec.end, joint,
                                    maintainOffset=False,
                                    name=spec.name + "_orientConstraint")[0]
        for node, command in ((point, c.pointConstraint),
                              (orient, c.orientConstraint)):
            aliases = command(node, query=True, weightAliasList=True) or []
            if len(aliases) != 2:
                raise RuntimeError("轴向分段双端约束目标无效")
            c.setAttr(node + "." + aliases[0], 1.0 - spec.fraction)
            c.setAttr(node + "." + aliases[1], spec.fraction)

    def capture_axial_part(self, spec: AxialPartSpec
                           ) -> tuple[str, str, tuple[float, float, float]]:
        c = self._cmds
        matches = c.ls(spec.path, long=True, type="joint") or []
        if len(matches) != 1:
            raise RuntimeError("轴向分段关节缺失")
        parent = (c.listRelatives(matches[0], parent=True,
                                  fullPath=True) or [""])[0]
        position = tuple(float(v) for v in c.xform(matches[0], query=True,
                         worldSpace=True, translation=True))
        return matches[0], parent, position
