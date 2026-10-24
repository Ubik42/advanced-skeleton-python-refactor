"""Original Custom Reduce preview/application inside one native Undo chunk."""


class CustomReduceOriginalFace:
    def __init__(self, host):
        self.host = host

    def apply(self, kind, every, *, preview=False):
        if type(preview) is not bool:
            raise TypeError('预览标记必须是布尔值')
        plan = self.host.capture_original_custom_face_reduction(kind, every)
        with self.host.transaction('Custom Face Joint Reduce'):
            return self.host.apply_original_custom_face_reduction(plan, preview=preview)


class ReduceOriginalLipJoints:
    def __init__(self, host):
        self.host = host

    def apply(self, count=14):
        if type(count) is not int or count != 14:
            raise ValueError('原版面板的唇部缩减入口为 14 个关节')
        source = self.host.capture_original_lip_reduction()
        with self.host.transaction('Reduce Lip joints to 14'):
            return self.host.reduce_original_lip_joints(source, count)


class ReduceOriginalEyeLidJoints:
    def __init__(self, host):
        self.host = host

    def apply(self, count):
        if type(count) is not int or count not in (4, 8):
            raise ValueError('原版眼睑缩减只支持 4 或 8 个关节')
        source = self.host.capture_original_eye_lid_reduction()
        with self.host.transaction('Reduce EyeLid joints to ' + str(count)):
            return self.host.reduce_original_eye_lid_joints(source, count)
