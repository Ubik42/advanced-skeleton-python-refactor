"""Original Jaw weighing, adjustment and finishing operations."""
from adv_py.core.fit_settings import FitSkeletonValidationError

class BuildFaceJaw:
    def __init__(self,host): self.host=host
    def apply(self,smooth_iterations=50):
        source=self.host.capture_jaw_input(smooth_iterations)
        if source is None: return None
        names=("JawSet","Jaw_M","JawOffset_M","SDKJaw_M","JawJoint_M","JawMix_M",
            "JawLayer","JawLayerSC","JawOpenLayer","JawOpenLayerSC","JawCurveSC",
            "LipDeform","mouthOpenSoftMod","mouthOpenSoftModHandle")
        collisions=[name for name in names if self.host.find_name_collisions(name)]
        if collisions: raise FitSkeletonValidationError("Jaw 构建节点名称已占用："+"、".join(collisions))
        with self.host.transaction("建立 Jaw 权重层与 Teeth"):
            if self.host.capture_jaw_input(smooth_iterations)!=source: raise RuntimeError("Jaw 输入在构建前变化")
            before=self.host.capture_face_build_node_ids()
            result=self.host.create_original_jaw_weighing(source)
            self.host.extend_face_build_pose(result["controls"])
            self.host.register_face_module_nodes(before,"JawSet",production_skins=result["production_skins"])
        return result

class UpdateFaceJawWeights:
    def __init__(self,host): self.host=host
    def apply(self,smooth_iterations=50):
        source=self.host.capture_jaw_input(smooth_iterations)
        if source is None: return None
        with self.host.transaction("更新 Jaw 曲线边界权重"):
            if self.host.capture_jaw_input(smooth_iterations)!=source: raise RuntimeError("Jaw 输入在更新前变化")
            before=self.host.capture_face_build_node_ids()
            count=self.host.update_original_jaw_curve_weights(source)
            self.host.register_face_module_nodes(before,"JawSet",reuse=True,production_skins=(source.skin,))
            return count

class FinishFaceJaw:
    def __init__(self,host): self.host=host
    def apply(self,smooth_iterations=50):
        source=self.host.capture_jaw_finish_input(smooth_iterations)
        if source is None: return None
        with self.host.transaction("合并 Jaw 权重并接入下颌跟随"):
            before=self.host.capture_face_build_node_ids()
            result=self.host.finish_original_jaw_weighing(source)
            if not result["already_finished"]:
                self.host.register_face_module_nodes(before,"JawSet",reuse=True,production_skins=(source.skin,result["skin"]))
            return result

class RecordFaceTeeth:
    def __init__(self,host): self.host=host
    def apply(self,part):
        with self.host.transaction("记录 "+part+" 输入"):
            return self.host.record_original_face_parts(part)


class FitFaceJawPose:
    """Keep the original fitting stage order inside one undo transaction."""
    def __init__(self,host): self.host=host
    def apply(self,stage,smooth_iterations=50):
        methods={"open":"fit_original_jaw_open","open_finish":"finish_original_jaw_open",
                 "lip_up":"fit_original_lip_up","lip_up_finish":"finish_original_lip_up",
                 "lip_down":"fit_original_lip_down","lip_down_finish":"finish_original_lip_down",
                 "lip_side":"fit_original_lip_side","lip_side_finish":"finish_original_lip_side"}
        if stage not in methods: raise ValueError("未知 Jaw/Lip 修形阶段："+stage)
        source=self.host.capture_jaw_finish_input(smooth_iterations) if stage=="open" else None
        if stage=="open" and source is None: return None
        with self.host.transaction("Face 修形："+stage):
            before=self.host.capture_face_build_node_ids()
            operation=getattr(self.host,methods[stage])
            result=operation(source) if stage=="open" else operation()
            if result:
                skins=(source.skin,) if source else ()
                if source and source.multi_skin_clusters: skins+=("JawSC",)
                self.host.register_face_module_nodes(before,"JawSet",reuse=True,production_skins=skins)
            return result
