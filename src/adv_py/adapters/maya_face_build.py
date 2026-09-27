"""Read the FaceSetup inputs used by the original build preflight."""
from __future__ import annotations

from adv_py.application.face_pre import FacePreRole
from adv_py.core.face_build_requirements import FaceInclude, required_face_fit_nodes
from adv_py.core.fit_settings import FitSkeletonValidationError

from .maya_face_pre import MayaFacePreHost


class MayaFaceBuildHost(MayaFacePreHost):
    def set_include(self, include: FaceInclude) -> FaceInclude:
        if not isinstance(include, FaceInclude):
            raise ValueError("Face Include 选项无效")
        c = self._cmds
        fit = self._fit(required=True)
        if c.referenceQuery(fit, isNodeReferenced=True):
            raise FitSkeletonValidationError("不能改写引用中的 FaceFitSkeleton")
        values = tuple(option.value for option in FaceInclude)
        with self.transaction("设置 Face Include"):
            self._transaction_changed = True
            if not c.attributeQuery("Include", node=fit, exists=True):
                c.addAttr(fit, longName="Include", attributeType="enum",
                          enumName=":".join(values))
            if c.getAttr(fit + ".Include", type=True) != "enum":
                raise FitSkeletonValidationError("Face Include 属性类型无效")
            labels = tuple((c.attributeQuery("Include", node=fit,
                                listEnum=True) or [""])[0].split(":"))
            if labels != values:
                raise FitSkeletonValidationError("Face Include 枚举选项与原版不一致")
            c.setAttr(fit + ".Include", values.index(include.value))
        if self.read_include() is not include:
            raise RuntimeError("Face Include 写后读回不一致")
        return include

    def read_include(self) -> FaceInclude:
        fit = self._fit(required=True)
        c = self._cmds
        if not c.attributeQuery("Include", node=fit, exists=True):
            return FaceInclude.ALL
        try:
            return FaceInclude(c.getAttr(fit + ".Include", asString=True))
        except ValueError as error:
            raise FitSkeletonValidationError("Face Include 选项无效") from error

    def inspect_build_inputs(self) -> dict:
        """Return missing original prerequisites without changing the scene."""
        c = self._cmds
        fit = self._fit(required=True)
        include = self.read_include()
        non_symmetric = bool(c.attributeQuery("NonSym", node=fit,
                               exists=True) and c.getAttr(fit + ".NonSym"))
        missing = []
        try:
            mask_mesh, _, _ = self.read_face_mask()
        except FitSkeletonValidationError:
            missing.append("Mask")
            mask_mesh = None
        try:
            face = self.read_face_objects(FacePreRole.FACE)
        except FitSkeletonValidationError:
            face = ()
        if len(face) != 1 or face[0] != mask_mesh:
            missing.append("Face")
        try:
            all_head = self.read_face_objects(FacePreRole.ALL_HEAD)
        except FitSkeletonValidationError:
            all_head = ()
        if not all_head or not face or face[0] not in all_head:
            missing.append("All Head")
        for side_name in ("RightEye", "LeftEye"):
            if not c.attributeQuery(side_name, node=fit, exists=True):
                missing.append(side_name)
                continue
            name = c.getAttr(fit + "." + side_name) or ""
            matches = c.ls(name, long=True, type="transform") if name else []
            if len(matches or []) != 1 or not c.listRelatives(
                    matches[0], shapes=True, noIntermediate=True, type="mesh"):
                missing.append(side_name)
        head_name = (c.getAttr(fit + ".HeadJoint")
                     if c.attributeQuery("HeadJoint", node=fit, exists=True)
                     else "") or ""
        heads = c.ls(head_name, long=True, type="joint") if head_name else []
        if len(heads or []) != 1:
            missing.append("HeadJoint")
        if len(face) == 1:
            shapes = c.listRelatives(face[0], shapes=True,
                                     noIntermediate=True, type="mesh") or []
            history = c.listHistory(shapes[0], pruneDagObjects=True) if shapes else []
            skins = [item for item in history or []
                     if c.nodeType(item) == "skinCluster"]
            if len(skins) != 1 or not heads or heads[0] not in [
                    (c.ls(item, long=True) or [None])[0] for item in
                    (c.skinCluster(skins[0], query=True, influence=True) or [])]:
                missing.append("Face Skin / HeadJoint")
        for name in required_face_fit_nodes(include, non_symmetric):
            paths = c.ls(name, long=True, type="transform") or []
            if len(paths) != 1 or not paths[0].startswith(fit + "|"):
                missing.append(name)
        return {"include": include.value,
                "non_symmetrical": non_symmetric,
                "required_fit_count": len(required_face_fit_nodes(
                    include, non_symmetric)),
                "missing": tuple(missing), "ready": not missing}
