"""Original old Face Fit container upgrade, MEL 28930–29045."""
from adv_py.core.face_fit_upgrade import (LEGACY_FACE_INPUTS, OBSOLETE_FACE_FITS,
    original_face_fit_needs_upgrade)
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_face_eye_loop_fit import MayaFaceEyeLoopFitMixin


class MayaFaceFitUpgradeMixin:
    def capture_original_face_fit_upgrade(self):
        c = self._cmds
        fit = self._fit()
        if fit is None:
            return None
        version = c.getAttr("FaceGroup.version") if c.objExists("FaceGroup.version") else None
        if not original_face_fit_needs_upgrade(version, c.getAttr(fit + ".ty")):
            return None
        if c.referenceQuery(fit, isNodeReferenced=True):
            raise FitSkeletonValidationError("不能升级引用中的 Face Fit")
        fields = {}
        for old, new in LEGACY_FACE_INPUTS:
            if not c.objExists(fit + "." + old):
                raise FitSkeletonValidationError("旧 Face Fit 缺少原版字段：" + old)
            fields[new] = c.getAttr(fit + "." + old) or ""
        pupil = c.getAttr(fit + ".Pupil_R") if c.objExists(fit + ".Pupil_R") else ""
        iris = c.getAttr(fit + ".Iris_R") if c.objExists(fit + ".Pupil_R") and c.objExists(fit + ".Iris_R") else ""
        if c.objExists("OldFaceFitSkeletonHolder"):
            raise FitSkeletonValidationError("已有旧 Fit 升级暂存，请先恢复该场景")
        deletion = self.plan_delete_face_advanced() if c.objExists("FaceMotionSystem") else None
        return {"fit": fit, "fields": fields, "scale": float(c.getAttr(fit + ".sy")) * 1.5,
                "pupil": pupil, "iris": iris, "deletion": deletion}

    def create_original_face_fit_container(self):
        c = self._cmds
        group = c.createNode("transform", name="FaceGroup")
        if c.objExists("|Group"):
            c.parent(group, "|Group")
        fit = c.createNode("transform", name="FaceFitSkeleton", parent=group)
        for node in (group, fit):
            for channel in ("t", "r", "s"):
                for axis in "xyz":
                    c.setAttr(node + "." + channel + axis, lock=True, keyable=False)
        return fit

    def upgrade_original_face_fit(self, source):
        self._require_transaction()
        if source is None:
            return {"upgraded": False, "requires_pre_fit": False}
        c = self._cmds
        raw = getattr(c, "raw", c)
        fit = source["fit"]
        self._transaction_changed = True
        for node in OBSOLETE_FACE_FITS:
            if c.objExists(node):
                c.delete(node)
        if source["deletion"] is not None:
            self.delete_face_advanced(source["deletion"])
        c.createNode("transform", name="OldFaceFitSkeletonHolder")
        for holder in c.listRelatives(fit, children=True, type="transform") or []:
            holder = c.parent(holder, "OldFaceFitSkeletonHolder")[0]
            children = c.listRelatives(holder, children=True, type="transform") or []
            for child in children:
                for channel in ("t", "r", "s"):
                    for axis in "xyz":
                        c.setAttr(child + "." + channel + axis, lock=False, keyable=True)
                c.setAttr(child + ".v", lock=False, keyable=True)
            if children:
                children = c.parent(children, world=True)
                for child in children:
                    c.setAttr(child + ".inheritsTransform", 1)
            c.xform(holder, objectSpace=True, translation=(0,0,0), rotation=(0,0,0), scale=(1,1,1))
            if children:
                c.parent(children, holder)
        c.delete("FaceGroup")
        fit = self.create_original_face_fit_container()
        for name, value in source["fields"].items():
            c.addAttr(fit, longName=name, dataType="string")
            c.setAttr(fit + "." + name, value, type="string")
        c.addAttr(fit, longName="faceScale", attributeType="double", defaultValue=source["scale"])
        for section, selection in (("Pupil", source["pupil"]), ("Iris", source["iris"])):
            if selection and not c.objExists("FaceFit" + section):
                selected = raw.ls(tuple(self.scene_address(token) for token in selection.split()), long=True, flatten=True) or []
                if selected:
                    raw.select(selected, replace=True)
                    MayaFaceEyeLoopFitMixin.create_original_eye_loop_fit(self, section)
        c.deleteAttr(fit + ".faceScale")
        children = c.listRelatives("OldFaceFitSkeletonHolder", children=True, type="transform") or []
        if children:
            c.parent(children, fit)
        c.delete("OldFaceFitSkeletonHolder")
        # Descendants must be visited child-first so parent renames cannot
        # invalidate paths of pending child operations.
        descendants = c.listRelatives(fit, allDescendents=True, fullPath=True, type="transform") or []
        for node in sorted(descendants, key=lambda path: path.count("|"), reverse=True):
            leaf = node.rsplit("|",1)[-1].rsplit(":",1)[-1]
            if "EyeBrowMiddle" in leaf:
                c.rename(node, leaf.replace("EyeBrowMiddle", "EyeBrowCenter", 1))
        c.addAttr(fit, longName="advPyFitUpgradePending", attributeType="bool", defaultValue=True)
        # Original stops after updating and requests fresh Pre/ Fit work. Return
        # that state rather than raising inside the undo chunk and undoing it.
        c.select(clear=True)
        return {"upgraded": True, "requires_pre_fit": True, "fit": fit}
