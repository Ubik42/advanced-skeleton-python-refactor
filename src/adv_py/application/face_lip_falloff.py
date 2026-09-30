"""Original Lip Falloff construction and subsequent updates."""
class BuildFaceLipFalloff:
    def __init__(self,host): self.host=host
    def apply(self,options):
        options=self.host.resolve_lip_falloff_options(options)
        context=self.host.capture_lip_falloff_context(options)
        if context is None: return None
        with self.host.transaction("构建 Lip Falloff"):
            before=self.host.capture_face_build_node_ids()
            result=self.host.create_lip_falloff(context,options)
            self.host.register_face_module_nodes(before,"LipFalloffSet",reuse=True)
            return result
