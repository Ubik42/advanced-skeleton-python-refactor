"""Original Selector select/key/align callbacks, MEL 10617–10705."""
from .maya_original_control_identity import source_control_from_role, source_control_name
from .maya_original_animation_bake import _current_registration, _bindings, _native_selected


class MayaOriginalSelectorCommandsMixin:
    def resolve_original_selector_control(self, name, control, *, extra=None):
        c = self._cmds
        raw = getattr(c, 'raw', c)
        role = source_control_name(self, control)
        if extra is None:
            checkbox = 'asSelector' + name + 'ExtraCheckBox'
            extra = bool(raw.checkBox(checkbox, query=True, exists=True)
                         and raw.checkBox(checkbox, query=True, value=True))
        if extra and len(role) > 2:
            extra_role = role[:2] + 'Extra' + role[2:]
            if 'RootX' in role:
                extra_role = role[:4] + 'Extra' + role[4:]
            candidate = source_control_from_role(self, extra_role)
            if c.objExists(candidate):
                return candidate
        return source_control_from_role(self, role)

    def select_original_selector_controls(self, name, controls, *, modifiers=None, extra=None):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, 'raw', c)
        controls = tuple(self.resolve_original_selector_control(name, control, extra=extra) for control in controls)
        modifier = raw.getModifiers() if modifiers is None else modifiers
        self._transaction_changed = True
        if not modifier & 1:
            c.select(clear=True)
        if not controls or controls[0] == '':
            c.select(clear=True)
            return ()
        for control in controls:
            if not c.objExists(control):
                raise ValueError('Object:"' + control + '" does not exists !')
        for control in controls:
            c.select(control, toggle=True)
        form = 'asSelector' + name + 'FormLayout'
        if raw.formLayout(form, query=True, exists=True):
            raw.setFocus(form)
        return controls

    def key_original_selector_controls(self, name, controls, *, linear=False, extra=None):
        self._require_transaction()
        c = self._cmds
        controls = tuple(self.resolve_original_selector_control(name, control, extra=extra) for control in controls)
        from .maya_native_animation_bake_boundary import capture, finish
        boundary = capture(self, tuple(self.scene_address(node) for node in controls))
        self._transaction_changed = True
        for control in controls:
            flags = dict(inTangentType='linear', outTangentType='linear') if linear else {}
            c.setKeyframe(control, **flags)
        finish(self, boundary, mark_baked=False)
        selected = c.ls(selection=True) or ()
        c.select(selected, replace=True) if selected else c.select(clear=True)
        from .maya_original_selection_feedback import refresh
        refresh(self)
        return controls

    def align_original_selector_fkik(self, controls, mode, *, switch=False, time_range=None):
        self._require_transaction()
        if mode not in ('fk', 'ik') or not controls:
            raise ValueError('原版 Selector FKIK 操作需要控制器及方向')
        role = source_control_name(self, controls[0])
        token = role[4:]
        saved = _current_registration(self)
        if saved is None:
            saved, rows = _native_selected(self, (token,))
            kind, binding, _ = rows[0]
        else:
            rows = _bindings(saved).get(token, ())
            if len(rows) != 1:
                raise ValueError('原版 Selector FKIK 系统不存在或不唯一：' + role)
            kind, binding, _ = rows[0]
            if kind == 'spline':
                saved = self.enable_source_spline_first_translation(saved)
                kind, binding, _ = _bindings(saved)[token][0]
        if switch and time_range is None:
            from maya import mel
            raw = getattr(self._cmds, 'raw', self._cmds)
            slider = mel.eval('$advPyPlaybackSlider=$gPlayBackSlider')
            time_range = tuple(raw.timeControl(slider, query=True, rangeArray=True))
        if kind == 'rp':
            from .maya_source_limb_matching import apply, switch as switch_limb
            if switch:
                return switch_limb(self, saved, binding, mode, time_range=time_range)
            return apply(self, saved, binding, mode, align_only=True)
        if switch:
            return self.switch_source_character_spline(saved, binding, mode, time_range=time_range)
        return self.align_source_character_spline(saved, binding, mode)
