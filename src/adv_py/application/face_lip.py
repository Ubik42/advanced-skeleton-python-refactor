"""Build the original complete Lip chain in one reversible operation."""
from adv_py.core.fit_settings import FitSkeletonValidationError

class BuildFaceLip:
    def __init__(self,host): self.host=host

    def apply(self):
        source=self.host.capture_lip_input()
        if source is None: return None
        names=("LipSet","LipSetup","LipJoints_M","lipArea","lipMainArea","LipRegion_M",
               "upperLipRibbonCurve","lowerLipRibbonCurve","upperLipRibbon","lowerLipRibbon",
               "lipSlideSurface","FaceControlSuspended","FaceControlOrientLip")
        collisions=tuple(name for name in names if self.host.find_name_collisions(name))
        if collisions: raise FitSkeletonValidationError("Lip 构建节点名称已占用："+"、".join(collisions))
        with self.host.transaction("构建完整 Lip Ribbon 与控制驱动"):
            if self.host.capture_lip_input()!=source: raise RuntimeError("Lip 输入在构建前变化")
            before=self.host.capture_face_build_node_ids()
            result=self.host.create_lip_rig(source)
            self.host.extend_face_build_pose(result["controls"])
            self.host.register_face_module_nodes(before,"LipSet",production_skins=(result["skin"],))
        return result
