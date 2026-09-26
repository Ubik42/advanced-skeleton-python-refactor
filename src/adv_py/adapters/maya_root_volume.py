"""Maya adapter for original-name weighted RootA Skin influences."""
from __future__ import annotations

from adv_py.core.root_volume_deform import RootVolumeSpec
from .maya_body import MayaBodyBuildHost


class MayaRootVolumeHost(MayaBodyBuildHost):
    def create_root_volume_joint(self, spec: RootVolumeSpec) -> None:
        self._require_transaction()
        c = self._cmds
        self._transaction_changed = True
        joint = c.createNode("joint", name=spec.name, parent=spec.parent,
                             skipSelect=True)
        joint = (c.ls(joint, long=True) or [joint])[0]
        if joint != spec.path:
            raise RuntimeError("Root 体积关节路径漂移：" + spec.name)
        c.setAttr(joint + ".rotateOrder", spec.rotate_order)
        c.setAttr(joint + ".jointOrient", *spec.joint_orient)
        c.setAttr(joint + ".translate", *spec.translate)
        c.setAttr(joint + ".rotate", *spec.rotate)
        c.setAttr(joint + ".scale", *spec.scale)
        c.addAttr(joint, longName="advPyAuxiliaryInfluenceKind", dataType="string")
        c.setAttr(joint + ".advPyAuxiliaryInfluenceKind",
                  "root-volume-v1", type="string", lock=True)

    def capture_root_volume_joint(self, spec: RootVolumeSpec
                                  ) -> tuple[str, str, tuple[float, float, float]]:
        c = self._cmds
        paths = c.ls(spec.path, long=True, type="joint") or []
        if len(paths) != 1:
            raise RuntimeError("Root 体积关节缺失：" + spec.name)
        parent = (c.listRelatives(paths[0], parent=True, fullPath=True) or [""])[0]
        translate = tuple(float(v) for v in c.getAttr(paths[0] + ".translate")[0])
        return paths[0], parent, translate
