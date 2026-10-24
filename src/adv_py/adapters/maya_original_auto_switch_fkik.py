"""asFindFKIKCtrl and asAutoSwitchFKIK, MEL 13522–13613."""
from .maya_original_control_identity import source_control_name
from .maya_original_animation_bake import _bindings, _native_selected, _current_registration


def find(c, control):
    """Follow the original visibility conditions, including hybrid shapes."""
    if 'FKIK' in control:
        return control
    parent = control
    for _ in range(99):
        parents = c.listRelatives(parent, parent=True) or ()
        if not parents:
            break
        parent = parents[0]
        inputs = c.listConnections(parent + '.v', source=True, destination=False) or ()
        if not inputs or c.objectType(inputs[0]) != 'condition':
            continue
        modes = c.listConnections(inputs[0] + '.firstTerm', source=True, destination=False) or ()
        if modes:
            return modes[0]
    shapes = c.listRelatives(control, shapes=True) or ()
    if shapes:
        inputs = c.listConnections(shapes[0] + '.v', source=True, destination=False) or ()
        if inputs:
            kind = c.objectType(inputs[0])
            condition = inputs[0] if kind == 'condition' else ''
            if kind == 'plusMinusAverage':
                rows = c.listConnections(inputs[0] + '.input1D[0]', source=True,
                                         destination=False, skipConversionNodes=True) or ()
                if rows and c.objectType(rows[0]) == 'condition':
                    condition = rows[0]
            if condition:
                modes = c.listConnections(condition + '.firstTerm', source=True, destination=False) or ()
                if modes:
                    return modes[0]
    return ''


class MayaOriginalAutoSwitchFKIKMixin:
    def auto_switch_original_fkik(self, selection=None, *, time_range=None):
        self._require_transaction()
        c = self._cmds
        selected = tuple(c.ls(selection=True) or ()) if selection is None else tuple(selection)
        saved = _current_registration(self)
        found = []
        for control in selected:
            role = source_control_name(self, control)
            mode = control if 'FKIK' in role else find(c, control)
            found.append(mode)
        modes = tuple(dict.fromkeys(found))
        if not modes or '' in modes:
            raise ValueError('First select a control that is part of FK/IK setup')
        if saved is None:
            saved, rows = _native_selected(self, tuple(source_control_name(self, control)[4:] for control in modes))
        else:
            catalog = _bindings(saved)
            rows = []
            for control in modes:
                role = source_control_name(self, control)
                matches = catalog.get(role[4:] if role.startswith('FKIK') else '', ())
                if len(matches) != 1:
                    raise ValueError('原版 FKIK 控制器没有唯一来源系统：' + control)
                rows.append(matches[0])
        if not getattr(saved, 'native_scene', False) and any(kind == 'spline' for kind, _, _ in rows):
            saved = self.enable_source_spline_first_translation(saved)
            catalog = _bindings(saved)
            rows = [catalog[source_control_name(self, control)[4:]][0] for control in modes]
        if time_range is None:
            raw = getattr(c, 'raw', c)
            # Maya's playback slider highlights an exclusive-end range.
            # This is exactly the range consumed by original asSwitchFKIK.
            try:
                from maya import mel
                slider = mel.eval('$advPyPlaybackSlider=$gPlayBackSlider')
                time_range = tuple(raw.timeControl(slider, query=True, rangeArray=True))
            except (ImportError, AttributeError):
                pass
        switched = []
        for control, (kind, binding, plug) in zip(modes, rows):
            current = float(c.getAttr(plug))
            self._transaction_changed = True
            if 0 < current < 5:
                c.setAttr(plug, 0)
            if 5 < current < 10:
                c.setAttr(plug, 10)
            direction = 'fk' if current > 5 else 'ik'
            if kind == 'rp':
                from .maya_source_limb_matching import switch
                result = switch(self, saved, binding, direction, time_range=time_range)
            else:
                result = self.switch_source_character_spline(saved, binding, direction, time_range=time_range)
            switched.append((control, direction, result))
        return tuple(switched)
