"""Source-ordered DS to BS conversion, including Mixed and game rigs."""
from adv_py.application.face_pre import FacePreRole
from adv_py.core.face_blendshape_conversion import FaceBlendShapeConversionOptions
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_face_bs_sampling import MayaFaceBSSamplingMixin
from .maya_face_bs_layers import MayaFaceBSLayersMixin
from .maya_face_bs_cleanup import MayaFaceBSCleanupMixin
from .maya_face_bs_mixed import MayaFaceBSMixedMixin
from .maya_face_bs_attachers import MayaFaceBSAttachersMixin
from .maya_face_bs_edit import MayaFaceBSEditMixin
from .maya_face_bs_targets import MayaFaceBSTargetsMixin


class MayaFaceBSConversionMixin(MayaFaceBSEditMixin, MayaFaceBSTargetsMixin, MayaFaceBSSamplingMixin, MayaFaceBSLayersMixin,
                                MayaFaceBSCleanupMixin, MayaFaceBSMixedMixin, MayaFaceBSAttachersMixin):
    @staticmethod
    def _original_restore_leaf(node):
        return node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]

    @staticmethod
    def _original_bs_physical_address(node):
        # Raw Maya names of root-namespace model objects need an explicit
        # root marker before passing through the character command mapper.
        return "|".join(":" + part if part and ":" not in part else part for part in node.split("|"))

    def capture_original_face_bs_conversion(self, options):
        c = self._cmds
        raw = getattr(c, "raw", c)
        fit = self._fit(required=True)
        for node in ("FaceControlSet", "FaceAllSet", "ctrlBox", "OnFacecontrols", "FaceJoint_M"):
            if not c.objExists(node):
                raise FitSkeletonValidationError("Face 转换缺少前置节点：" + node)
        if c.objExists("asFaceBS"):
            raise FitSkeletonValidationError("Face 已经转换为 BlendShape")
        faces = self.read_face_objects(FacePreRole.FACE)
        if len(faces) != 1:
            raise FitSkeletonValidationError("Face 转换需要唯一主网格")
        geometry = self._original_bs_physical_address(raw.ls(self.scene_address(faces[0]), long=True)[0])
        all_head = tuple(self._original_bs_physical_address(raw.ls(self.scene_address(mesh), long=True)[0]) for mesh in self.read_face_objects(FacePreRole.ALL_HEAD))
        head = c.getAttr(fit + ".HeadJoint")
        use_layers = options.keep_joints and not (c.objExists(fit + ".GameEngine") and c.getAttr(fit + ".GameEngine"))
        if use_layers and (not c.objExists("FaceGroup.version") or float(c.getAttr("FaceGroup.version")) < 5.791):
            raise FitSkeletonValidationError("Mixed 转换要求原版 Face 版本不低于 5.791")
        controls = []
        for parent in c.listRelatives("ctrlBox", children=True, type="transform") or []:
            children = c.listRelatives(parent, children=True, type="transform") or []
            if children:
                controls.append(children[0])
        if options.keep_joints:
            controls.extend(("SmilePull_R", "SmilePull_L"))
        meshes = [geometry]
        for part in ("Eyebrow", "EyeLash", "Extras", "UpperTeeth", "LowerTeeth", "Tongue"):
            meshes.extend(self.read_original_face_parts(part))
        targets, seen = [], set()
        for item in meshes:
            for obj in raw.ls(item, objectsOnly=True, long=True) or []:
                if raw.nodeType(obj) == "mesh":
                    obj = raw.listRelatives(obj, parent=True, fullPath=True)[0]
                uid = (raw.ls(obj, uuid=True) or [obj])[0]
                if uid not in seen:
                    seen.add(uid)
                    targets.append(self._original_bs_physical_address(obj))
        anchor = "JawPivot" if c.objExists("JawPivot") else "outerLid_R"
        return {"geometry": geometry, "all_head": tuple(all_head), "head": head,
                "skin": self.original_face_production_skin(geometry, head),
                "use_skin_layers": bool(use_layers), "controls": tuple(controls),
                "target_geometry": tuple(targets), "ctrl_scale": float(c.getAttr("OnFacecontrols.sx")),
                "cheek_position": tuple(c.xform(anchor, query=True, worldSpace=True, translation=True))}

    def convert_original_face_to_blendshapes(self, options=None):
        self._require_transaction()
        options = options or FaceBlendShapeConversionOptions()
        source = self.capture_original_face_bs_conversion(options)
        c = self._cmds
        raw = getattr(c, "raw", c)
        fit = self._fit(required=True)
        before = self.capture_face_build_node_ids()
        existing = [node for node in c.ls(objectsOnly=True) or [] if c.nodeType(node) not in ("objectSet", "partition")]
        self._transaction_changed = True
        c.sets(existing, name="allBeforeConvertToBS")
        auto = bool(raw.autoKeyframe(query=True, state=True))
        limits = bool(c.getAttr("ctrlBox.limits"))
        envelopes = []
        raw.autoKeyframe(state=False)
        try:
            if not c.objExists(fit + ".RigType"):
                c.addAttr(fit, longName="RigType", attributeType="enum", enumName="Joints:BlendShape:Mixed")
            try:
                c.setAttr(fit + ".RigType", 1 + int(options.keep_joints))
            except RuntimeError:
                pass
            if source["use_skin_layers"]:
                self.prepare_original_face_bs_layers(source)
            else:
                self._original_face_bs_front(source["geometry"], "asFaceBS")
            if limits:
                c.setAttr("ctrlBox.limits", 0)
            self.apply_face_build_pose(self.read_face_build_pose())
            for node in raw.listHistory(self.scene_address(source["geometry"])) or []:
                if raw.nodeType(node) in ("deltaMush", "blendShape"):
                    envelopes.append((node, raw.getAttr(node + ".envelope")))
                    raw.setAttr(node + ".envelope", 0)
            if c.objExists("asBlendShapes"):
                children = c.listRelatives("asBlendShapes", children=True) or []
                if children:
                    c.move(0, source["cheek_position"][0] * -2.5, 0, children, relative=True)
            else:
                c.createNode("transform", name="asBlendShapes")
            if not source["use_skin_layers"]:
                for side in ("_R", "_L"):
                    for shell, child, parent in (("EyeBaseFollowTS", "EyeAim", "EyeOffset"),
                                                  ("EyeBaseFollowR", "SDKEye", "EyeAim"),
                                                  ("EyeBaseOffset", "EyeRegionOffset", "SideReverse")):
                        if c.objExists(shell + side):
                            c.parent(child + side, parent + side)
                            c.delete(shell + side)
            targets = self.sample_original_face_bs_targets(source, options)
            if limits:
                c.setAttr("ctrlBox.limits", 1)
            self.remove_original_face_bs_driving_graph(source, options)
            if source["use_skin_layers"]:
                self.make_original_face_bs_mixed_local(source)
            self.finish_original_face_bs_conversion(source, options, before, envelopes)
            return {"targets": targets, "keep_joints": options.keep_joints,
                    "keep_targets": options.keep_targets, "use_skin_layers": source["use_skin_layers"]}
        finally:
            raw.autoKeyframe(state=auto)
