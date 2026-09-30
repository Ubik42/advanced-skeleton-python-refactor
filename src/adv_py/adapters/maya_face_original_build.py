"""Original 30-step Advanced Face build and rebuild orchestration.

Each stage executes its native Python port; no ADV MEL procedure evaluation.
Full builds do not reset controls between stages (asBuildAdvancedFace). The
manual step entry alone runs asStepBuildPrep's neutralization and order check.
"""
from .maya_face_expressions import MayaFaceExpressionHost
from .maya_face_softmod_edit import MayaFaceSoftModEditMixin
from .maya_face_regions import MayaFaceRegionsHost
from .maya_face_head_squash import MayaFaceHeadSquashHost
from .maya_face_tweak_controls import MayaFaceTweakControlsHost
from .maya_face_restore import MayaFaceRestoreMixin
from .maya_face_fit_upgrade import MayaFaceFitUpgradeMixin
from .maya_face_wrinkle_curves import MayaFaceWrinkleCurvesMixin
from .maya_face_wrinkle_uv import MayaFaceWrinkleUVMixin
from .maya_face_wrinkle_graph import MayaFaceWrinkleGraphMixin
from adv_py.core.face_original_build import ORIGINAL_FACE_BUILD_STEPS, OriginalFaceKeepOptions
from adv_py.core.face_cage import FaceCageOptions
from adv_py.core.face_lip_falloff import LipFalloffOptions
from adv_py.core.fit_settings import FitSkeletonValidationError

class MayaOriginalFaceBuildHost(MayaFaceWrinkleGraphMixin, MayaFaceWrinkleCurvesMixin, MayaFaceWrinkleUVMixin, MayaFaceFitUpgradeMixin, MayaFaceSoftModEditMixin, MayaFaceRestoreMixin, MayaFaceExpressionHost,
                                MayaFaceRegionsHost, MayaFaceHeadSquashHost,
                                MayaFaceTweakControlsHost):
    def face_skin_cluster(self, mesh):
        # Face stages share the source's primary Skin, even with additional
        # EyeLid/Lip/Cage layers. The legacy single-Skin helper is insufficient.
        fit = self._fit(required=True)
        return self.original_face_production_skin(mesh, self._cmds.getAttr(fit + ".HeadJoint"))

    def preflight_original_face_build(self):
        c = self._cmds
        fit = self._fit(required=True)
        return self.capture_original_face_prep()

    def prepare_original_face_build_step(self, step):
        """asStepBuildPrep 30881–30918, used only by manual steps."""
        self._require_transaction()
        c = self._cmds
        fit = self._fit(required=True)
        if c.objExists(fit + ".buildStep") and int(c.getAttr(fit + ".buildStep")) != step - 1:
            raise FitSkeletonValidationError("检测到跳过构建步骤，请按原版顺序继续")
        raw = getattr(c, "raw", c)
        auto = bool(raw.autoKeyframe(query=True, state=True))
        if auto:
            raw.autoKeyframe(state=False)
        try:
            curves = []
            for root in ("OnFacecontrols", "ctrlBox"):
                if c.objExists(root):
                    curves.extend(c.listRelatives(root, allDescendents=True, type="nurbsCurve") or [])
            for shape in curves:
                control = c.listRelatives(shape, parent=True)[0]
                if self._original_restore_leaf(control).startswith("ctrlBox"):
                    continue
                c.xform(control, objectSpace=True, translation=(0, 0, 0), rotation=(0, 0, 0), scale=(1, 1, 1))
        finally:
            if auto:
                raw.autoKeyframe(state=True)

    def complete_original_face_build_step(self, step):
        c = self._cmds
        if c.ls("convertedSoftMod_*", type="softMod"):
            self.complete_original_face_softmod_edits()
        fit = self._fit(required=True)
        if not c.objExists(fit + ".buildStep"):
            c.addAttr(fit, longName="buildStep", attributeType="long", defaultValue=0)
        c.setAttr(fit + ".buildStep", step)

    def execute_original_face_build_stage(self, stage, *, prep=None, keep=None,
                                          cage_smooth=None, jaw_smooth=50, lip_falloff=None):
        """Execute one source stage inside the caller's encompassing undo."""
        self._require_transaction()
        before = self.capture_face_build_node_ids()
        source = None
        result = None
        module = "FaceExpressionSet"
        if stage == "Prep":
            return self.prepare_original_face_build(prep or self.capture_original_face_prep(), keep)
        if stage == "CtrlBox":
            controls = self.create_ctrl_box(self.capture_ctrl_box_input())
            result = {"controls": controls}
            module = "FaceCtrlBoxSet"
        elif stage in ("EyeBall", "EyeLid"):
            source = self.capture_original_face_eye_input() if stage == "EyeBall" else self.capture_original_face_lid_input()
            method = self.create_original_face_eye_ball if stage == "EyeBall" else self.create_original_face_eye_lid
            result = method(source)
        elif stage == "Lip":
            source = self.capture_lip_input()
            if source is not None:
                result = self.create_lip_rig(source)
                module = "LipSet"
        elif stage == "LipFalloff":
            fit = self._fit(required=True)
            c = self._cmds
            from dataclasses import replace
            supplied = lip_falloff or LipFalloffOptions()
            options = self.resolve_lip_falloff_options(replace(supplied,
                multi_skin_clusters=bool(c.objExists(fit + ".MultiSkinClusters") and c.getAttr(fit + ".MultiSkinClusters"))))
            source = self.capture_lip_falloff_context(options)
            if source is not None:
                result = self.create_lip_falloff(source, options)
                module = "LipFalloffSet"
        elif stage in ("FaceCage", "CageToSkin", "EyeBrow", "SmilePull", "Snarl", "UpMidLo"):
            source = self.capture_face_cage_input()
            if source is not None:
                if stage == "FaceCage":
                    result = self.create_original_face_cage(source, FaceCageOptions(cage_smooth))
                    self._original_face_cage_smooth = result["smooth_passes"]
                elif stage == "CageToSkin":
                    smooth = cage_smooth if cage_smooth is not None else getattr(self, "_original_face_cage_smooth", 1)
                    result = self.transfer_original_face_cage(source, smooth)
                else:
                    method = {"EyeBrow": self.create_original_face_eye_brow,
                              "SmilePull": self.fit_original_face_smile_pull,
                              "Snarl": self.fit_original_face_snarl,
                              "UpMidLo": self.create_original_face_up_mid_lo}[stage]
                    result = method(source)
                module = "FaceCageSet" if stage in ("FaceCage", "CageToSkin", "EyeBrow") else module
        elif stage in ("JawWeighing", "JawOpen"):
            source = self.capture_jaw_input(jaw_smooth) if stage == "JawWeighing" else self.capture_jaw_finish_input(jaw_smooth)
            if source is not None:
                result = self.create_original_jaw_weighing(source) if stage == "JawWeighing" else self.fit_original_jaw_open(source)
                module = "FaceJawSet"
        elif stage == "Tongue":
            if self._cmds.objExists("upperLipMainCurve"):
                self.finish_original_face_snarl()
            source = self.capture_tongue_input()
            if source is not None:
                result = self.create_tongue_rig(source)
                module = "TongueSet"
        elif stage == "Regions":
            source = self.capture_face_regions()
            if source is not None:
                result = self.create_face_regions(source)
                module = "FaceRegionsSet"
        elif stage == "Finish":
            return self.finish_original_face(self.preflight_original_face_finish())
        elif stage == "RebuildRestore":
            return self.restore_original_face(keep)
        else:
            methods = {"EyeBlink": self.fit_original_face_eye_blink, "EyeWide": self.fit_original_face_eye_wide,
                       "Squint": self.fit_original_face_squint, "FrownPull": self.fit_original_face_frown_pull,
                       "Cheek": self.fit_original_face_cheek, "CheekRaiser": self.fit_original_face_cheek_raiser,
                       "LipUp": self.fit_original_lip_up, "LipDown": self.fit_original_lip_down,
                       "LipSide": self.fit_original_lip_side, "EyeAim": self.show_original_face_eye_aim,
                       "Phonemes": self.create_original_face_phonemes, "Emotions": self.create_original_face_emotions}
            if stage not in methods:
                raise ValueError("未知原版 Face 步骤：" + stage)
            result = methods[stage]()
        if result:
            skins = list(result.get("production_skins", ())) if isinstance(result, dict) else []
            if isinstance(result, dict) and result.get("skin"):
                skins.append(result["skin"])
            if source is not None and hasattr(source, "skin"):
                skins.append(source.skin)
            if isinstance(result, dict) and result.get("controls"):
                self.extend_face_build_pose(result["controls"])
            elif stage == "Regions" and isinstance(result, tuple):
                self.extend_face_build_pose(result)
            # Narrow smile controls are created when Cheek finishes FrownPull.
            if stage == "Cheek":
                self.extend_face_build_pose(("SmilePull_R", "SmilePull_L"))
            self.register_face_module_nodes(before, module, reuse=True, production_skins=tuple(skin for skin in skins if skin))
        return result
