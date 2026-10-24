"""Face Pre option persistence, including native side-switch callbacks."""
from adv_py.core.original_face_options import normalize_original_face_options


class SetOriginalFaceOptions:
    def __init__(self, host):
        self.host = host

    def apply(self, values, *, switch_side=False):
        values = normalize_original_face_options(values)
        if self.host.read_original_face_options() is None:
            return None  # Native UI allows choosing options before Mask exists.
        with self.host.transaction('记录原版 Face Pre 选项'):
            result = self.host.write_original_face_options(values)
            if switch_side and 'NonSym' in values:
                c = self.host._cmds
                fit = self.host._fit(required=True)
                if not c.objExists(fit+'.NonSymSide'):
                    c.addAttr(fit, longName='NonSymSide', dataType='string')
                self.host.switch_original_face_fit_side(1 if values['NonSym'] else 2)
                result = self.host.read_original_face_options()
        return result
