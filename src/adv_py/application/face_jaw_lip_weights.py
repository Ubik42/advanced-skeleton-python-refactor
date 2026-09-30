"""Update original JawOpenLayer Lip weights with existing mouth-open SoftMod."""
class UpdateFaceJawLipWeights:
    def __init__(self,host): self.host=host
    def apply(self):
        source=self.host.capture_jaw_lip_weights_input()
        with self.host.transaction("更新 Jaw 嘴唇权重"):
            if self.host.capture_jaw_lip_weights_input()!=source:
                raise RuntimeError("Jaw Lip 输入在写权重前变化")
            before=self.host.capture_face_build_node_ids()
            result=self.host.update_jaw_lip_weights(source)
            self.host.register_face_module_nodes(before,"JawLipWeightsSet",reuse=True)
            return result
