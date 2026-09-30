"""Original first-build branch of asFacePrep; rebuild prefix branch separate."""
from adv_py.application.face_pre import FacePreRole
from adv_py.core.face_build_requirements import FaceInclude, required_face_fit_nodes
from adv_py.core.fit_settings import FitSkeletonValidationError
from .maya_face_forehead_fit import MayaFaceForeHeadFitMixin


class MayaFacePrepFirstMixin(MayaFaceForeHeadFitMixin):
    def _marker_context(self, section):
        from .maya_face_fit_markers import MayaFaceFitMarkersHost
        return MayaFaceFitMarkersHost._marker_context(self, section)

    def _marker_containers(self, fit, section, suffix, holder):
        from .maya_face_fit_markers import MayaFaceFitMarkersHost
        return MayaFaceFitMarkersHost._marker_containers(self, fit, section, suffix, holder)

    def capture_original_face_first_prep(self):
        c = self._cmds
        raw = getattr(c, "raw", c)
        fit = self._fit(required=True)
        if c.objExists("prefix_FaceGroup"):
            raise FitSkeletonValidationError("prefix_FaceGroup 表示前次重建未完成，请先恢复该次重建")
        if c.objExists("FaceMotionSystem"):
            raise FitSkeletonValidationError("当前已有 Face 系统；此入口用于首次准备，完整重建恢复仍待接入")
        if not c.objExists(fit + ".faceScale"):
            raise FitSkeletonValidationError("请先选择 Mask")
        geometry = self.read_face_objects(FacePreRole.FACE)
        all_head = self.read_face_objects(FacePreRole.ALL_HEAD)
        if len(geometry) != 1 or not all_head:
            raise FitSkeletonValidationError("请记录 Face 和 All Head")
        for part in ("RightEye", "LeftEye"):
            if not self.read_original_face_parts(part):
                raise FitSkeletonValidationError("请记录 " + part)
        head = c.getAttr(fit + ".HeadJoint") if c.objExists(fit + ".HeadJoint") else ""
        if not head or not c.objExists(head):
            raise FitSkeletonValidationError("请记录 Head 关节")
        if not raw.listConnections(self.scene_address(head) + ".worldMatrix"):
            raise FitSkeletonValidationError("Head 关节未连接 Skin")
        non_sym = bool(c.objExists(fit + ".NonSym") and c.getAttr(fit + ".NonSym"))
        include = FaceInclude(c.getAttr(fit + ".Include", asString=True)) if c.objExists(fit + ".Include") else FaceInclude.ALL
        for name in required_face_fit_nodes(include, non_sym):
            legacy = name.replace("NoseBridge", "NoseCenter")
            if not c.objExists(name) and not (legacy != name and c.objExists(legacy)):
                raise FitSkeletonValidationError("Face Fit 尚未完成：" + name)
        if non_sym and c.objExists("upperLipOuterCurve") and not c.objExists("upperLipOuterCurveLeft"):
            raise FitSkeletonValidationError("Lip Fit 创建于启用 NonSym 之前，需要重新定位 Lip")
        if self.read_original_face_parts("Tongue") and not c.objExists("Tongue0"):
            raise FitSkeletonValidationError("已记录 Tongue 网格，但缺少 Tongue 定位点")
        if "decomposeMatrix" not in raw.allNodeTypes():
            raise FitSkeletonValidationError("FaceSetup 需要启用 matrixNodes 插件")
        for mesh in all_head:
            if not raw.objExists(self.scene_address(mesh)) or not self._original_pupil_skin(self.scene_address(mesh), exclude_prefix=False):
                raise FitSkeletonValidationError("All Head 缺少网格或 Skin：" + mesh)
        for name in ("Nose_M", "Eye_R", "Eye1_R", "Eye_L", "Eye1_L"):
            if c.objExists(name):
                raise FitSkeletonValidationError("Face 构建名称已占用：" + name)
        return {"geometry": geometry[0], "all_head": all_head, "head": head,
                "skin": self.original_face_production_skin(geometry[0], head),
                "scale": float(c.getAttr(fit + ".faceScale")), "non_sym": non_sym,
                "game": bool(c.objExists(fit + ".GameEngine") and c.getAttr(fit + ".GameEngine"))}

    def prepare_original_face_first_build(self, source):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, "raw", c)
        fit = self._fit(required=True)
        self._transaction_changed = True
        if c.objExists("FaceFitNoseCenter"):
            for node in c.ls("*NoseCenter*", type="transform") or []:
                c.rename(node, node.rsplit("|", 1)[-1].replace("NoseCenter", "NoseBridge"))
        if c.objExists(fit + ".RigType") and c.getAttr(fit + ".RigType") == 1 and c.objExists("FaceFitUpMidLo"):
            raw.warning("当前 RigType 不支持 UpMidLo，按原版移除该 Fit")
            c.delete("FaceFitUpMidLo")
        from adv_py.application.model_check import ReviewModelCheck
        from .maya_model_checker import MayaModelCheckHost
        raw.select(self.scene_address(source["geometry"]), replace=True)
        ReviewModelCheck(MayaModelCheckHost()).execute(game_engine=source["game"], skip_symmetry=True)
        raw.select(clear=True)
        for name in ("FaceFitSmileLine", "FaceFitSmileLineLeft", "FaceFitCheekRaiser", "FaceFitCheekRaiserLeft"):
            if c.objExists(name):
                c.delete(name)
        if c.objExists(fit + ".preRebuildScript"):
            script = c.getAttr(fit + ".preRebuildScript")
            if script:
                from maya import mel
                mel.eval(script)  # User-provided hook, never the ADV procedure.
        self._original_face_prep_forehead_direction(source)
        if c.objExists(fit + ".run"):
            c.setAttr(fit + ".run", "", type="string")
        for name in ("upperTempSoftModHandle", "lowerTempSoftModHandle"):
            if c.objExists(name):
                c.delete(name)
        raw.softSelect(edit=True, softSelectEnabled=False)
        if raw.symmetricModelling(query=True, symmetry=True):
            raw.symmetricModelling(edit=True, symmetry=False)
        raw.displaySmoothness(tuple(self.scene_address(mesh) for mesh in source["all_head"]),
                              divisionsU=0, divisionsV=0, pointsWire=4, pointsShaded=1, polygonObject=1)
        if not c.objExists(fit + ".buildCompleted"):
            c.addAttr(fit, longName="buildCompleted", attributeType="bool", defaultValue=False)
        completed = bool(c.getAttr(fit + ".buildCompleted"))
        if c.objExists("FaceAllSet") and not c.objExists("FaceMotionSystem"):
            completed = False
        if not completed:
            self._original_face_first_cleanup(source)
        skin = self.scene_address(source["skin"])
        if raw.getAttr(skin + ".maintainMaxInfluences"):
            raw.setAttr(skin + ".maintainMaxInfluences", False)
        if raw.getAttr(skin + ".normalizeWeights") != 1:
            raw.setAttr(skin + ".normalizeWeights", 1)
        if c.objExists("Main.jointVis"):
            c.setAttr("Main.jointVis", False)
        self.prepare_original_face_fit_sides()
        before = self.capture_face_build_node_ids()
        self.prepare_original_face_skin(source)
        self.finish_original_face_preparation(source)
        self.register_face_module_nodes(before, "FacePrepSet", production_skins=(source["skin"],))
        return {"skin": source["skin"], "original_stage": "asFacePrep first build"}

    def _original_face_prep_forehead_direction(self, source):
        """Refresh legacy ForeHead curve direction before Fit duplication."""
        c = self._cmds
        raw = getattr(c, "raw", c)
        if not c.objExists("FaceFitForeHead") or c.objExists("FaceFitForeHead.directionChecked"):
            return
        fit = self._fit(required=True)
        suffixes = ("", "Left") if source["non_sym"] else ("",)
        selections = {}
        for suffix in suffixes:
            holder = "FaceFitForeHead" + suffix
            if not c.objExists(holder + ".selection"):
                raise FitSkeletonValidationError("旧 ForeHead Fit 缺少原始选择记录：" + holder)
            selections[suffix] = tuple(raw.ls(c.getAttr(holder + ".selection").split(),
                                               long=True, flatten=True) or [])
            if not selections[suffix]:
                raise FitSkeletonValidationError("旧 ForeHead Fit 的原始组件已不存在：" + holder)
        if source["non_sym"] and not c.objExists(fit + ".NonSymSide"):
            c.addAttr(fit, longName="NonSymSide", dataType="string")
        for suffix in suffixes:
            if source["non_sym"]:
                c.setAttr(fit + ".NonSymSide", "Left" if suffix else "Right", type="string")
            raw.select(selections[suffix], replace=True)
            c.delete("FaceFitForeHead" + suffix)
            self.create_original_face_forehead_fit()
        if source["non_sym"]:
            c.setAttr(fit + ".NonSymSide", "Right", type="string")

    def _original_face_first_cleanup(self, source):
        c = self._cmds
        raw = getattr(c, "raw", c)
        names = ("FaceAllSet", "FaceControlSet", "FaceAreas", "FaceBuildingSets", "eyeLidArea", "eyeLidAreaLeft",
                 "eyeBrowArea", "eyeBrowLineArea", "eyeLidMainArea", "eyeLidOuterArea", "eyeLidOuterAreaLeft",
                 "lipMainArea", "lipArea", "lipFalloffArea", "lipFalloffAreaMax", "lowerTeethSet", "upperTeethSet",
                 "FaceMusclesLayer", "lowerOS2WSTG_L", "lowerOS2WSTG_R", "allBeforeFaceBuild",
                 "MainAndHeadScaleMultiplyDivide", "asCage", "FaceMotionSystem", "FaceDeformationSystem",
                 "FaceBuildInProgress", "FaceJoint_M")
        found = False
        for name in names:
            if c.objExists(name):
                c.delete(name)
                found = True
        if found:
            for mesh in source["all_head"]:
                skin = self._original_pupil_skin(self.scene_address(mesh), exclude_prefix=False)
                if skin:
                    raw.select(self.scene_address(mesh), replace=True)
                    raw.skinPercent(skin, normalize=True)
                    raw.dgdirty(allPlugs=True)
