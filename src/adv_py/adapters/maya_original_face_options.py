"""Native bool/enum storage for Face Pre; enum values stay menu indices."""
from adv_py.core.original_face_options import (
    ORIGINAL_FACE_OPTIONS, normalize_original_face_options,
)
from adv_py.core.fit_settings import FitSkeletonValidationError


class MayaOriginalFaceOptionsMixin:
    def read_original_face_options(self):
        c = self._cmds
        fit = self._fit()
        if fit is None:
            return None
        result = {}
        for option in ORIGINAL_FACE_OPTIONS:
            plug = fit+'.'+option.attribute
            if not c.objExists(plug):
                result[option.attribute] = option.default
            elif option.attribute == 'NonSym' and c.getAttr(plug, type=True) == 'string':
                # Native updateInfo deletes the obsolete string before read.
                # Reading alone never deletes user scene data; a later write
                # performs that explicit native compatibility conversion.
                result[option.attribute] = False
            elif option.items:
                result[option.attribute] = c.getAttr(plug, asString=True)
            else:
                result[option.attribute] = bool(c.getAttr(plug))
        return normalize_original_face_options(result, complete=True)

    def write_original_face_options(self, values, *, complete=False):
        self._require_transaction()
        values = normalize_original_face_options(values, complete=complete)
        c = self._cmds
        fit = self._fit(required=True)
        if c.referenceQuery(fit, isNodeReferenced=True):
            raise FitSkeletonValidationError('不能改写引用中的 Face 选项')
        for option in ORIGINAL_FACE_OPTIONS:
            if option.attribute not in values:
                continue
            plug = fit+'.'+option.attribute
            if c.objExists(plug):
                kind = c.getAttr(plug, type=True)
                if option.attribute == 'NonSym' and kind == 'string':
                    self._transaction_changed = True
                    c.deleteAttr(plug)
                elif kind != ('enum' if option.items else 'bool'):
                    raise FitSkeletonValidationError('原版 Face 选项属性类型不符：'+option.attribute)
            if not c.objExists(plug):
                self._transaction_changed = True
                if option.items:
                    c.addAttr(fit, longName=option.attribute, attributeType='enum',
                              enumName=':'.join(option.items)+':')
                else:
                    c.addAttr(fit, longName=option.attribute, attributeType='bool')
            self._transaction_changed = True
            if option.items:
                value = option.items.index(values[option.attribute])
                try:
                    c.setAttr(plug, value)
                except RuntimeError:
                    # Native added e.g. Mixed by deleting/recreating an old
                    # shorter enum after the selected menu index is rejected.
                    c.deleteAttr(plug)
                    c.addAttr(fit, longName=option.attribute, attributeType='enum',
                              enumName=':'.join(option.items)+':')
                    c.setAttr(plug, value)
            else:
                c.setAttr(plug, values[option.attribute])
            if option.attribute == 'NonSym' and not c.objExists(fit+'.NonSymSide'):
                c.addAttr(fit, longName='NonSymSide', dataType='string')
                c.setAttr(fit+'.NonSymSide', '', type='string')
        return self.read_original_face_options()
