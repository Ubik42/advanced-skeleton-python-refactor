"""Original mouth-open design layer creation."""
from adv_py.core.fit_settings import FitSkeletonValidationError

class CreateFaceMouthOpenDesign:
    def __init__(self,host): self.host=host
    def apply(self):
        source=self.host.capture_mouth_open_input()
        names=("LipDeformations","LipDeform","mouthOpenSoftMod","mouthOpenSoftModHandle","mouthOpenSoftModSet","MouthOpenSet")
        collisions=[name for name in names if self.host.find_name_collisions(name)]
        if collisions: raise FitSkeletonValidationError("Mouth Open 节点名称已占用："+"、".join(collisions))
        with self.host.transaction("建立原版 Mouth Open 修形"):
            if self.host.capture_mouth_open_input()!=source: raise RuntimeError("Mouth Open 输入变化")
            before=self.host.capture_face_build_node_ids()
            result=self.host.create_mouth_open_design(source)
            self.host.register_face_module_nodes(before,"MouthOpenSet")
            return result
