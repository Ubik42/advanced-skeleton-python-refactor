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
