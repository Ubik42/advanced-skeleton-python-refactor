"""Create the original HeadSquash graph as one reversible scene operation."""
from adv_py.core.face_head_squash import HEAD_SQUASH_NAMES
from adv_py.core.fit_settings import FitSkeletonValidationError

class BuildFaceHeadSquash:
    def __init__(self,host): self.host=host

    def apply(self):
        source=self.host.capture_head_squash_input()
        collisions=tuple(name for name in HEAD_SQUASH_NAMES
                         if self.host.find_name_collisions(name))
        if collisions:
            raise FitSkeletonValidationError("HeadSquash 节点名称已被占用："+"、".join(collisions))
        with self.host.transaction("创建 HeadSquash"):
            if self.host.capture_head_squash_input()!=source:
                raise RuntimeError("HeadSquash 输入在构建前变化")
            before=self.host.capture_face_build_node_ids()
            result=self.host.create_head_squash(source)
            self.host.extend_face_build_pose(result.controls)
            self.host.register_head_squash_nodes(before)
            self.host.validate_head_squash(result)
        return result

class DeleteFaceHeadSquash:
    def __init__(self,host): self.host=host
    def apply(self):
        with self.host.transaction("删除 HeadSquash"):
            return self.host.delete_head_squash()

class OptimizeFaceHeadSquash:
    def __init__(self,host): self.host=host
    def apply(self):
        with self.host.transaction("优化 HeadSquash 影响范围"):
            return self.host.optimize_head_squash()

class IncludeSelectedInHeadSquash:
    def __init__(self,host): self.host=host
    def apply(self):
        with self.host.transaction("将所选对象加入 HeadSquash"):
            return self.host.include_selected_head_squash()
