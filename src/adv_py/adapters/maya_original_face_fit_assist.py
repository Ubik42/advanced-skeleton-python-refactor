"""asFaceAssist, original temporary EyeLid/Lip fitting deformation."""
from adv_py.application.face_pre import FacePreRole
from .maya_face_deformer_sets import original_face_deformer_sets


class MayaOriginalFaceFitAssistMixin:
    def toggle_original_face_fit_assist(self, section):
        self._require_transaction()
        if section not in ('EyeLid', 'Lip'):
            raise ValueError('原版 Assist 类型无效')
        c = self._cmds
        fit = self._fit(required=True)
        scale = float(c.getAttr(fit + '.faceScale'))
        raw = getattr(c, 'raw', c)
        selected = tuple(raw.ls(selection=True) or [])
        suffix = 'Left' if c.objExists(fit + '.NonSym') and c.getAttr(fit + '.NonSymSide') == 'Left' else ''
        self._transaction_changed = True
        if c.objExists('upperTempSoftModHandle'):
            c.delete('upperTempSoftModHandle')
            if c.objExists('lowerTempSoftModHandle'):
                c.delete('lowerTempSoftModHandle')
            return False
        geometry = self.read_face_objects(FacePreRole.FACE)[0]
        part = 'Outer' if section == 'Lip' else 'Main'
        try:
            for arc, factor in (('upper', 1), ('lower', -1)):
                # Native reads Right curves, then reflects sample X for Left.
                curve = arc + section + part + 'Curve'
                count = int(c.getAttr(curve + '.spans')) + int(c.getAttr(curve + '.degree'))
                middle = 0 if section == 'Lip' else (count - 1) // 2
                a = list(c.xform(curve + f'.cv[{middle}]', query=True, worldSpace=True, translation=True))
                b = list(c.xform(curve + f'.cv[{count - 1}]', query=True, worldSpace=True, translation=True))
                if suffix:
                    a[0], b[0] = -a[0], -b[0]
                c.select(geometry, replace=True)
                with original_face_deformer_sets(raw):
                    deform, handle = c.softMod(falloffMode=1, falloffAroundSelection=False)[:2]
                deform = c.rename(deform, arc + 'TempSoftMod')
                handle = c.rename(handle, arc + 'TempSoftModHandle')
                shape = c.listRelatives(handle, shapes=True)[0]
                c.setAttr(shape + '.origin', *a, type='float3')
                c.setAttr(deform + '.falloffCenter', *a, type='float3')
                c.xform(handle, pivots=a)
                c.setAttr(deform + '.falloffMode', 1)
                c.setAttr(deform + '.falloffRadius', abs(a[0] - b[0]))
                c.move(0, scale / 30. * factor, scale / 10., handle, relative=True)
                for field, value in (('FloatValue', 1), ('Position', .5), ('Interp', 2)):
                    c.setAttr(deform + '.falloffCurve[3].falloffCurve_' + field, value)
        finally:
            raw.select(selected, replace=True) if selected else raw.select(clear=True)
        return True
