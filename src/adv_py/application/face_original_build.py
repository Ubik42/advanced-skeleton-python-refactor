"""Continuous original Face build, with one operation-level undo boundary."""
from adv_py.core.face_original_build import ORIGINAL_FACE_BUILD_STEPS, OriginalFaceKeepOptions


class BuildOriginalFace:
    def __init__(self, host):
        self.host = host

    def apply(self, *, keep=None, manually_restore=False, cage_smooth=None, jaw_smooth=50, lip_falloff=None):
        keep = keep or OriginalFaceKeepOptions()
        source = self.host.preflight_original_face_build()
        c = self.host._cmds
        raw = getattr(c, "raw", c)
        if raw.currentUnit(query=True, fullName=True) != "centimeter":
            raise ValueError("AdvancedSkeleton 需要厘米单位，请先切换 Maya 场景单位")
        self.host.prepare_original_face_build_dependencies()
        if not manually_restore:
            self.host.prepare_original_face_restore_dependencies(keep)
        results = {}
        with self.host.transaction("按原版完整构建 Advanced Face"):
            for step, stage in enumerate(ORIGINAL_FACE_BUILD_STEPS, 1):
                if stage == "RebuildRestore" and manually_restore:
                    break
                results[stage] = self.host.execute_original_face_build_stage(
                    stage, prep=source if stage == "Prep" else None, keep=keep,
                    cage_smooth=cage_smooth, jaw_smooth=jaw_smooth, lip_falloff=lip_falloff)
                self.host.complete_original_face_build_step(step)
        return {"stages": results, "restore_pending": bool(manually_restore and source["rebuild"])}


class BuildOriginalFaceStep:
    def __init__(self, host):
        self.host = host

    def apply(self, step, *, keep=None, cage_smooth=None, jaw_smooth=50, lip_falloff=None):
        if type(step) is not int or not 1 <= step <= len(ORIGINAL_FACE_BUILD_STEPS):
            raise ValueError("Face 步骤必须为 1 至 30")
        source = self.host.preflight_original_face_build() if step == 1 else None
        if ORIGINAL_FACE_BUILD_STEPS[step - 1] == "Finish":
            self.host.prepare_original_face_build_dependencies()
        if ORIGINAL_FACE_BUILD_STEPS[step - 1] == "RebuildRestore":
            self.host.prepare_original_face_restore_dependencies(keep)
        with self.host.transaction("原版 Face 步骤：" + ORIGINAL_FACE_BUILD_STEPS[step - 1]):
            self.host.prepare_original_face_build_step(step)
            result = self.host.execute_original_face_build_stage(
                ORIGINAL_FACE_BUILD_STEPS[step - 1], prep=source, keep=keep,
                cage_smooth=cage_smooth, jaw_smooth=jaw_smooth, lip_falloff=lip_falloff)
            self.host.complete_original_face_build_step(step)
        return result


class UpgradeOriginalFaceFit:
    def __init__(self, host):
        self.host = host

    def apply(self):
        source = self.host.capture_original_face_fit_upgrade()
        if source is None:
            return {"upgraded": False, "requires_pre_fit": False}
        with self.host.transaction("升级旧版原版 Face Fit"):
            return self.host.upgrade_original_face_fit(source)
