"""Reversible Tongue input, Fit, build and finishing operations."""
from adv_py.core.fit_settings import FitSkeletonValidationError

class RecordFaceTongue:
    def __init__(self,host): self.host=host
    def apply(self):
        with self.host.transaction("记录 Tongue 输入"):
            return self.host.record_tongue_geometry()

class CreateFaceTongueFit:
    def __init__(self,host): self.host=host
    def apply(self):
        with self.host.transaction("创建 Tongue Fit"):
            return self.host.create_tongue_fit()

class BuildFaceTongue:
    def __init__(self,host): self.host=host
    def apply(self):
        source=self.host.capture_tongue_input()
        if source is None: return None
        names=["TongueSet","tempWeightCube","tongueBoxSC","Tongue0Follow_M",
               "Tongue0BM_M","Tongue0MMA_M","Tongue0MMB_M","Tongue0FollowDM_M",
               "Tongue0_MBlendJawFollow_MUnitConversion","Tongue0_MBlendJawFollow_MReverse",
               "bwTongue0_M_followJawFollow_M"]
        if source.skin is None: names.append("tongueSC")
        for index in range(source.control_count):
            names.extend((f"Tongue{index}_M",f"Tongue{index}Offset_M",f"SDKTongue{index}_M",
                          f"Tongue{index}Joint_M",f"Tongue{index}Joint_MScaleMPD",
                          f"Tongue{index}JointMM_M",f"Tongue{index}JointDM_M"))
        names.extend(f"TongueLattice{i}" for i in range(source.control_count+1))
        collisions=tuple(name for name in names if self.host.find_name_collisions(name))
        if collisions:
            raise FitSkeletonValidationError("Tongue 构建节点名称已占用："+"、".join(collisions))
        with self.host.transaction("构建 Tongue 控制链与 Skin"):
            if self.host.capture_tongue_input()!=source:
                raise RuntimeError("Tongue 输入在构建前变化")
            before=self.host.capture_face_build_node_ids()
            result=self.host.create_tongue_rig(source)
            self.host.extend_face_build_pose(result["controls"])
            self.host.register_face_module_nodes(before,"TongueSet",
                                                  production_skins=(result["skin"],))
            self.host.validate_tongue_rig(result)
        return result

class FinishFaceTongue:
    def __init__(self,host): self.host=host
    def apply(self):
        with self.host.transaction("完成 Tongue 构建显示"):
            return self.host.finish_tongue()
