"""Original Regions stage, preserving completed Face module ownership."""
class BuildFaceRegions:
    def __init__(self,host): self.host=host
    def apply(self):
        source=self.host.capture_face_regions()
        if source is None: return None
        with self.host.transaction("建立 Regions 第二控制盒投影"):
            before=self.host.capture_face_build_node_ids()
            result=self.host.create_face_regions(source)
            self.host.register_face_module_nodes(before,"RegionsSet",reuse=True)
            return result
