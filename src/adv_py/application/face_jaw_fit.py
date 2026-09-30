"""Build the original persistent Jaw Fit weight-reference curves."""
from adv_py.core.face_jaw_fit import JAW_FIT_CURVES
from adv_py.core.fit_settings import FitSkeletonValidationError

class BuildFaceJawFitCurves:
    def __init__(self, host): self.host = host

    def apply(self):
        source = self.host.capture_jaw_fit_input()
        collisions = tuple(name for name in ("FaceFitJawCurves",*JAW_FIT_CURVES)
                           if self.host.find_name_collisions(name))
        if collisions:
            raise FitSkeletonValidationError("Jaw Fit 节点名称已被占用："+"、".join(collisions))
        with self.host.transaction("创建 Jaw Fit 权重曲线"):
            if self.host.capture_jaw_fit_input() != source:
                raise RuntimeError("Jaw Fit 输入在构建前变化")
            result = self.host.create_jaw_fit_curves(source)
            self.host.validate_jaw_fit_curves()
        return result
