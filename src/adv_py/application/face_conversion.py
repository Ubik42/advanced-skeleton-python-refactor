"""Original Face conversion commands with one undo boundary."""
from adv_py.core.face_blendshape_conversion import FaceBlendShapeConversionOptions


class ConvertOriginalFaceToBlendShapes:
    def __init__(self, host):
        self.host = host

    def apply(self, *, keep_joints=False, keep_targets=False):
        options = FaceBlendShapeConversionOptions(keep_joints=bool(keep_joints), keep_targets=bool(keep_targets))
        self.host.capture_original_face_bs_conversion(options)
        with self.host.transaction("将原版 Face 驱动转换为 BlendShape"):
            return self.host.convert_original_face_to_blendshapes(options)


class ConnectOriginalFaceARKit:
    def __init__(self, host):
        self.host = host

    def apply(self, blendshape=None, *, mouth_close_includes_open=False):
        with self.host.transaction("连接原版 Face ARKit"):
            return self.host.connect_original_face_arkit(blendshape,
                mouth_close_includes_open=bool(mouth_close_includes_open))

    def disconnect(self):
        with self.host.transaction("断开原版 Face ARKit"):
            return self.host.disconnect_original_face_arkit()


class EditOriginalFaceBlendShapes:
    def __init__(self, host):
        self.host = host

    def targets(self):
        return self.host.original_face_bs_editable_targets()

    def apply(self, action, *, target=None, step=0, auto_mirror=True, multiplier=1.3,
              attribute="", control="", mirror=True, weight=1):
        allowed = ("extract", "reset", "delete", "wizard_start", "wizard_next", "wizard_stop",
                   "extract_all", "delta_mush_all", "new", "weight")
        if action not in allowed:
            raise ValueError("原版 BlendShape 操作无效")
        self.host.original_face_bs_editable_targets()
        with self.host.transaction("原版 BlendShape 操作：" + action):
            before = self.host.capture_face_build_node_ids()
            if action == "weight": result = self.host.set_original_face_bs_edit_weight(target, weight)
            elif action == "extract":
                result = (self.host.adjust_original_face_bs_named_target(target, auto_mirror=auto_mirror)
                          if target else self.host.adjust_original_face_bs_target(auto_mirror=auto_mirror))
            elif action == "reset": result = self.host.reset_original_face_bs_target()
            elif action == "delete": result = self.host.finish_original_face_bs_edit()
            elif action == "wizard_start": result = self.host.start_original_face_bs_wizard(auto_mirror=auto_mirror)
            elif action == "wizard_next": result = self.host.next_original_face_bs_wizard(step, auto_mirror=auto_mirror)
            elif action == "wizard_stop": result = self.host.stop_original_face_bs_wizard()
            elif action == "extract_all": result = self.host.extract_all_original_face_bs_targets(auto_mirror=auto_mirror)
            elif action == "delta_mush_all": result = self.host.delta_mush_all_original_face_bs_targets(auto_mirror=auto_mirror, multiplier=multiplier)
            else: result = self.host.create_new_original_face_bs_target(attribute, control, mirror=mirror)
            c = self.host._cmds
            generated = [node for node in c.ls(objectsOnly=True) or []
                         if c.nodeType(node) not in ("objectSet", "partition")
                         and not before.intersection(c.ls(node, uuid=True) or [])]
            if generated:
                c.sets(generated, add="FaceAllSet")
            return result
