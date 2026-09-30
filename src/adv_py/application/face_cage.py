"""Ordered original Cage operations, with whole-operation undo boundaries."""
from adv_py.core.face_cage import FaceCageOptions
from adv_py.core.fit_settings import FitSkeletonValidationError

class BuildFaceCage:
    def __init__(self,host): self.host=host
    def apply(self,options=FaceCageOptions()):
        source=self.host.capture_face_cage_input()
        if source is None: return None
        names=("FaceCageSet","asCage","asCageSC","asCageJoints","cageOffJoint","TempPos")
        collisions=[name for name in names if self.host.find_name_collisions(name)]
        if collisions: raise FitSkeletonValidationError("Face Cage 名称已占用："+"、".join(collisions))
        with self.host.transaction("建立原版 Face Cage 与投射控制"):
            if self.host.capture_face_cage_input()!=source: raise RuntimeError("Face Cage 输入在构建前变化")
            before=self.host.capture_face_build_node_ids()
            result=self.host.create_original_face_cage(source,options)
            self.host.extend_face_build_pose(result["controls"])
            self.host.register_face_module_nodes(before,"FaceCageSet",production_skins=(source.skin,result["skin"]))
            return result

class TransferFaceCage:
    def __init__(self,host): self.host=host
    def apply(self,smooth_passes):
        FaceCageOptions(smooth_passes)
        source=self.host.capture_face_cage_input()
        if source is None: return None
        collisions=[name for name in ("PreCageWeights","PreCageWeightsSC","CageLayer","CageLayerSC")
                    if self.host.find_name_collisions(name)]
        if collisions: raise FitSkeletonValidationError("Cage 转移节点已占用："+"、".join(collisions))
        with self.host.transaction("Face Cage 转移到生产 Skin"):
            before=self.host.capture_face_build_node_ids()
            result=self.host.transfer_original_face_cage(source,smooth_passes)
            self.host.register_face_module_nodes(before,"FaceCageSet",reuse=True,production_skins=(source.skin,result["skin"]))
            return result

class EditFaceCage:
    def __init__(self,host): self.host=host
    def apply(self,action,smooth_passes=0):
        FaceCageOptions(smooth_passes)
        if action not in ("update","remove","finish"): raise ValueError("未知 Face Cage 操作")
        source=self.host.capture_face_cage_input()
        if source is None: return None
        with self.host.transaction("Face Cage："+action):
            if action=="remove":
                self.host.remove_original_face_cage_weights(source); return True
            if action=="finish": return self.host.finish_original_face_cage()
            return self.host.update_original_face_cage_weights(source,smooth_passes)

class BuildFaceBrow:
    def __init__(self,host): self.host=host
    def apply(self):
        source=self.host.capture_face_cage_input()
        if source is None: return None
        with self.host.transaction("建立原版 EyeBrow Region 与驱动"):
            before=self.host.capture_face_build_node_ids()
            result=self.host.create_original_face_eye_brow(source)
            if result:
                self.host.extend_face_build_pose(result["controls"])
                self.host.register_face_module_nodes(before,"FaceCageSet",reuse=True,
                    production_skins=(source.skin,result["skin"],*result["production_skins"]))
            return result
