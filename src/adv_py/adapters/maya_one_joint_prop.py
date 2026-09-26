"""Maya scene adapter for the Preparation One Joint Prop workflow."""
from __future__ import annotations

from .maya_body import MayaBodyBuildHost


class MayaOneJointPropHost(MayaBodyBuildHost):
    def create_one_joint_prop_rig(self, first_skin_mesh: str):
        self._require_transaction()
        c = self._cmds
        bounds = c.exactWorldBoundingBox(first_skin_mesh)
        center = tuple((bounds[axis] + bounds[axis + 3]) / 2.0
                       for axis in range(3))
        radius = max(bounds[3] - bounds[0], bounds[4] - bounds[1],
                     bounds[5] - bounds[2]) * .6
        self._transaction_changed = True
        selection = c.ls(selection=True, long=True) or []
        try:
            fit = c.createNode("transform", name="FitSkeleton")
            c.select(clear=True)
            fit_root = c.joint(name="Root", position=center)
            c.setAttr(fit_root + ".jointOrient", 90, 0, 90,
                      type="double3")
            c.parent(fit_root, fit, absolute=True)
            from adv_py.core.preparation_objects import PreparationObjectRole
            from .maya_preparation_objects import (
                MayaPreparationObjectsHost, _ATTRIBUTES)
            records = MayaPreparationObjectsHost()
            for role in PreparationObjectRole:
                attribute = _ATTRIBUTES[role]
                c.addAttr(fit, longName=attribute, dataType="string")
                c.setAttr(fit + "." + attribute,
                          " ".join(records._stored_names(role)), type="string")
            group = c.createNode("transform", name="Group")
            rig = c.createNode("transform", name="Rig", parent=group)
            c.select(clear=True)
            joint = c.joint(name="Root_M", position=center)
            c.parent(joint, rig, absolute=True)
            control = c.circle(name="Main", normal=(0, 1, 0),
                               radius=max(radius, .1),
                               constructionHistory=False)[0]
            c.parent(control, group, absolute=True)
            c.xform(control, worldSpace=True, translation=center)
            c.parentConstraint(control, joint, maintainOffset=True)
            if not c.objExists("Hi"):
                c.createDisplayLayer(name="Hi", number=1, empty=True)
            c.setAttr("Hi.displayType", 1)
            fit_path = (c.ls(fit_root, long=True, type="joint") or [])[0]
            joint_path = (c.ls(joint, long=True, type="joint") or [])[0]
            control_path = (c.ls(control, long=True, type="transform") or [])[0]
            return fit_path, joint_path, control_path
        finally:
            c.select(selection, replace=True) if selection else c.select(clear=True)
