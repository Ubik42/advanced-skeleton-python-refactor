"""Original Fit reselect, hide, side switch and show-both-sides operations."""
from adv_py.core.original_face_fitting_update import original_face_fit_reselect_node


class MayaOriginalFaceFitDisplayMixin:
    def reselect_original_face_fit(self, section, part=''):
        c = self._cmds
        fit = self._fit(required=True)
        has_non_sym = c.objExists(fit + '.NonSym')
        side = c.getAttr(fit + '.NonSymSide') if has_non_sym else ''
        holder = original_face_fit_reselect_node(section, part,
            has_non_sym=has_non_sym, side=side)
        if c.objExists(holder) and c.objExists(holder + '.selection'):
            tokens = (c.getAttr(holder + '.selection') or '').split()
            c.select(tokens, replace=True) if tokens else c.select(clear=True)
        return holder

    def switch_original_face_fit_side(self, right):
        """asFaceSwitchSide, 46700–46732; 0 Left, 1 Right, 2 Off."""
        self._require_transaction()
        if right not in (0, 1, 2):
            raise ValueError('Face Fit 侧别模式无效')
        c = self._cmds
        fit = self._fit()
        if fit is None:
            return False
        self._transaction_changed = True
        c.setAttr(fit + '.NonSym', right != 2)
        c.setAttr(fit + '.NonSymSide', ('Left', 'Right', '')[right], type='string')
        for child in c.listRelatives(fit, children=True, type='transform') or []:
            visibility = (right == 0) if child.endswith('Left') else right != 0
            c.setAttr(child + '.v', visibility)
        return True

    def show_original_face_fit_both_sides(self):
        self._require_transaction()
        c = self._cmds
        fit = self._fit(required=True)
        children = tuple(c.listRelatives(fit, children=True, type='transform') or [])
        self._transaction_changed = bool(children) or self._transaction_changed
        for child in children:
            c.setAttr(child + '.v', 1)
        return children

    def toggle_original_face_fit_visibility(self, section, part=''):
        """asFaceFitHide, MEL 42432–42441."""
        self._require_transaction()
        c = self._cmds
        fit = self._fit(required=True)
        has_non_sym = c.objExists(fit + '.NonSym')
        side = c.getAttr(fit + '.NonSymSide') if has_non_sym else ''
        holder = original_face_fit_reselect_node(section, part,
            has_non_sym=has_non_sym, side=side)
        visible = not bool(c.getAttr(holder + '.v'))
        self._transaction_changed = True
        c.setAttr(holder + '.v', visible)
        return visible

    def delete_original_face_fit(self, region):
        """asFaceDeleteFromCheckBox, MEL 42407–42430."""
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, 'raw', c)
        fit = self._fit(required=True)
        side = c.getAttr(fit + '.NonSymSide') if c.objExists(fit + '.NonSym') else ''
        suffix = 'Left' if side == 'Left' else ''
        if raw.confirmDialog(title='Confirm', message='Delete ' + region,
                button=['OK', 'Cancel'], defaultButton='Cancel', dismissString='Cancel') != 'OK':
            return None
        removed = []
        for name in dict.fromkeys(('FaceFit' + region + suffix,
                *(('FaceFit' + region + 'Left',) if region.startswith('Lip') else ()))):
            if c.objExists(name):
                self._transaction_changed = True
                c.delete(name)
                removed.append(name)
        return tuple(removed)

    def original_face_fit_exists(self, section, part=''):
        # Native checkbox state is based on the unsuffixed holder, even in
        # the non-symmetrical UI. Side switching only changes visibility.
        return bool(self._cmds.objExists('FaceFit' + section + part))

    def swap_original_face_fit_upper_lower(self, section, part=''):
        """asFaceFitSwapUpperLower, MEL 41501–41525, unsuffixed names."""
        self._require_transaction()
        if section not in ('EyeLid', 'Lip', 'EyeLidMain2'):
            raise ValueError('原版上下交换仅用于 EyeLid / Lip')
        if section == 'EyeLidMain2':
            if part:
                raise ValueError('EyeLidMain2 不使用层级后缀')
        elif part not in ('Outer', 'Main', 'Inner'):
            raise ValueError('Face Fit 层级无效')
        c = self._cmds
        self._transaction_changed = True
        for upper, lower in (
                ('upper' + section + 'Cylinder' + part, 'lower' + section + 'Cylinder' + part),
                ('upper' + section + part + 'Curve', 'lower' + section + part + 'Curve')):
            temporary = c.rename(upper, upper + 'Swapping')
            c.rename(lower, upper)
            c.rename(temporary, lower)
        upper = 'upper' + section + 'Cylinder' + part
        lower = 'lower' + section + 'Cylinder' + part
        # Read the SG after all native renames, then exchange assignments.
        groups = []
        for tube in (upper, lower):
            shape = c.listRelatives(tube, shapes=True, noIntermediate=True)[0]
            groups.append(c.listConnections(shape + '.instObjGroups[0]',
                source=False, destination=True)[0])
        c.sets(upper, edit=True, forceElement=groups[1])
        c.sets(lower, edit=True, forceElement=groups[0])
        return section + part
