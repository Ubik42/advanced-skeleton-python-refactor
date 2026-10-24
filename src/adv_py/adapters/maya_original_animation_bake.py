"""Original Anim/Bake FKIK orchestration, MEL 14198–14271.

The original Bake dialog's playback-range loop differs from a highlighted
range switch: one initial switch, then forced alignment on every frame.
"""
from math import isfinite
from adv_py.core.character_registry import CharacterRegistryError
from adv_py.core.character_registry import REGISTRY_NAME
from adv_py.core.source_spline_animation import resolve_source_spline
from .maya_original_control_identity import control_roles, leaf, source_control_name, source_control_from_role, registration


def _bindings(saved):
    rows = {}
    channels = {channel.key: channel for channel in saved.channels}
    roles = control_roles(saved)
    for binding in saved.source_limbs:
        channel = channels[binding.blend_key]
        role = roles.get(leaf(channel.node), leaf(channel.node))
        if channel.attribute == 'FKIKBlend' and role.startswith('FKIK'):
            rows.setdefault(role[4:], []).append(('rp', binding, channel.node + '.FKIKBlend'))
    for plan in (saved.spine, *saved.additional_spines):
        if plan is None or not getattr(plan, 'source_mode', None):
            continue
        binding = resolve_source_spline(saved, plan.system_name)
        role = roles.get(leaf(plan.mode_control), leaf(plan.mode_control))
        if role.startswith('FKIK'):
            rows.setdefault(role[4:], []).append(('spline', binding, binding.blend_plug))
    return rows


def _current_registration(host):
    # A present, damaged Python registry must fail its real audit; it cannot
    # fall through into the adapter for an original scene without a registry.
    return host.read_character_registration() if host._cmds.objExists(REGISTRY_NAME) else None


def _native_selected(host, requested):
    from types import SimpleNamespace
    scenes, selected = [], []
    for token in requested:
        label, side = token.rsplit('_', 1)
        if host._cmds.objExists('Pole' + token):
            from .maya_original_rp_scene import read
            kind = 'rp'
        else:
            from .maya_original_spline_scene import read
            kind = 'spline'
        scene, binding = read(host, label, side)
        scenes.append(scene)
        selected.append((kind, binding, 'FKIK' + token + '.FKIKBlend'))
    channels = {row.key: row for scene in scenes for row in scene.channels}
    return SimpleNamespace(channels=tuple(channels.values()), source_limbs=tuple(row[1] for row in selected if row[0]=='rp'),
                           spine=None, additional_spines=(), nodes=(), native_scene=True), selected


class MayaOriginalAnimationBakeMixin:
    def bake_original_extra_animation(self, *, ui_name='', **state):
        """asAnimBakeExtra: bake the child frames, then install their native curves."""
        self._require_transaction()
        c = self._cmds
        sets = self.original_control_sets(ui_name, **state)
        if not sets:
            raise ValueError('No controlSets detected. select a controller')
        current = c.currentTime(query=True)
        before = registration(self)
        if before is not None:
            before = self.read_character_registration()
        extras = tuple(control for control in c.sets(sets, query=True) or ()
                       if source_control_name(self, control).startswith(('FKExtra', 'RootExtraX')))
        controls = tuple(source_control_from_role(self, source_control_name(self, control).replace('Extra', '', 1))
                         for control in extras)
        from .maya_native_animation_bake_boundary import capture, finish
        animation = capture(self, tuple(self.scene_address(node) for node in (*extras, *controls)))
        bakers = []
        self._transaction_changed = True
        for extra, control in zip(extras, controls):
            parent = c.listRelatives(extra, parent=True)[0]
            baker = c.createNode('transform', name=leaf(extra) + 'BAKER', parent=parent)
            bakers.append(baker)
            c.setAttr(baker + '.rotateOrder', c.getAttr(control + '.rotateOrder'))
            target = c.listRelatives(extra, children=True, type='transform')[0]
            c.parentConstraint(target, baker)
            c.scaleConstraint(target, baker)
        c.bakeResults(bakers, simulation=True,
            time=(c.playbackOptions(query=True, minTime=True), c.playbackOptions(query=True, maxTime=True)),
            sampleBy=1, disableImplicitControl=True, preserveOutsideKeys=False,
            sparseAnimCurveBake=False, removeBakedAttributeFromLayer=False,
            bakeOnOverrideLayer=False, controlPoints=False, shape=False)
        c.currentTime(current)
        c.select(bakers, replace=True)
        c.delete(staticChannels=True, unitlessAnimationCurves=False,
                 hierarchy='none', controlPoints=False, shape=True)
        for extra, control in zip(extras, controls):
            for node in (extra, control):
                curves = c.listConnections(node, source=True, destination=False, type='animCurve') or ()
                if curves:
                    c.delete(curves)
                c.xform(node, objectSpace=True, translation=(0, 0, 0), rotation=(0, 0, 0), scale=(1, 1, 1))
        for baker, control in zip(bakers, controls):
            for curve in c.listConnections(baker, source=True, destination=False, type='animCurve') or ():
                connections = c.listConnections(curve, source=False, destination=True, plugs=True, connections=True)
                source, destination = connections[:2]
                attribute = destination.split('.')[1]
                c.connectAttr(source, control + '.' + attribute)
                c.rename(source.split('.', 1)[0], leaf(control) + '_' + attribute)
        c.delete(bakers)
        finish(self, animation)
        if before is not None:
            from .maya_original_export_preparation import MayaOriginalExportPreparationHost
            MayaOriginalExportPreparationHost._remember_export_preparation(self, before)
        return controls

    def bake_original_quick_ik_animation(self, *, ui_name='', **state):
        """asAnimBakeQuickIK: native constraint/pairBlend controls, outside keys kept."""
        self._require_transaction()
        c = self._cmds
        sets = self.original_control_sets(ui_name, **state)
        if not sets:
            raise ValueError('No controlSets detected. select a controller')
        before = registration(self)
        if before is not None:
            before = self.read_character_registration()
        from .maya_original_quick_ik_state import capture as capture_quick, finish_bake as finish_quick
        quick = capture_quick(self)
        controls = []
        for control in c.sets(sets, query=True) or ():
            inputs = c.listConnections(control, source=True, destination=False, type='constraint') or ()
            if not inputs:
                inputs = c.listConnections(control, source=True, destination=False, type='pairBlend') or ()
            if inputs:
                controls.append(control)
        from .maya_native_animation_bake_boundary import capture, finish
        animation = capture(self, tuple(self.scene_address(node) for node in controls))
        self._transaction_changed = True
        c.select(controls, replace=True)
        c.bakeResults(controls, simulation=True,
            time=(c.playbackOptions(query=True, minTime=True), c.playbackOptions(query=True, maxTime=True)),
            sampleBy=1, disableImplicitControl=True, preserveOutsideKeys=True,
            sparseAnimCurveBake=False, removeBakedAttributeFromLayer=False,
            bakeOnOverrideLayer=False, controlPoints=False, shape=False)
        finish(self, animation)
        from .maya_static_animation_boundary import capture as capture_static, finish as finish_static
        static = capture_static(self)
        c.select(controls, replace=True)
        c.delete(staticChannels=True, unitlessAnimationCurves=False,
                 hierarchy='none', controlPoints=False, shape=True)
        finish_static(self, static)
        if c.objExists('QuickIK'):
            c.delete('QuickIK')
        finish_quick(self, quick, controls)
        c.select(clear=True)
        if before is not None:
            from .maya_original_export_preparation import MayaOriginalExportPreparationHost
            MayaOriginalExportPreparationHost._remember_export_preparation(self, before)
        return tuple(controls)

    def move_original_animation_to_extra(self, *, ui_name='', **state):
        """asAnimBakeToExtra: clean static input, then move only T/R connections."""
        self._require_transaction()
        c = self._cmds
        sets = self.original_control_sets(ui_name, **state)
        if not sets:
            raise ValueError('No controlSets detected. select a controller')
        before = registration(self)
        if before is not None:
            before = self.read_character_registration()
        from .maya_static_animation_boundary import capture as capture_static, finish as finish_static
        static = capture_static(self)
        self._transaction_changed = True
        c.select(sets, replace=True)
        c.delete(staticChannels=True, unitlessAnimationCurves=False,
                 hierarchy='none', controlPoints=False, shape=True)
        finish_static(self, static)
        c.select(clear=True)
        ports = []
        for extra in c.sets(sets, query=True) or ():
            role = source_control_name(self, extra)
            if 'Extra' not in role:
                continue
            control = source_control_from_role(self, role.replace('Extra', '', 1))
            for kind in ('translate', 'rotate'):
                for axis in 'XYZ':
                    source = control + '.' + kind + axis
                    if c.listConnections(source, source=True, destination=False, plugs=True, connections=True):
                        ports.append((self.scene_address(source), self.scene_address(extra + '.' + kind + axis)))
        from .maya_animation_port_move import capture, finish
        boundary = capture(self, ports)
        raw = getattr(c, 'raw', c)
        for move in boundary.moves:
            raw.connectAttr(move.driver, move.destination)
            raw.disconnectAttr(move.driver, move.source)
            raw.setAttr(move.source, 0)
        finish(self, boundary)
        if before is not None:
            from .maya_original_export_preparation import MayaOriginalExportPreparationHost
            MayaOriginalExportPreparationHost._remember_export_preparation(self, before)
        return tuple((move.source, move.destination) for move in boundary.moves)

    def original_animation_bake_systems(self):
        saved = _current_registration(self)
        if saved is None:
            return tuple(node.removeprefix('FKIK') for node in self._cmds.ls('FKIK*', type='transform') or ()
                         if self._cmds.objExists(node + '.FKIKBlend'))
        return tuple(_bindings(saved))

    def bake_original_fkik_animation(self, limbs, mode, *, ui_name='', baking_mocap=None, progress=None, **state):
        """asAnimBakeFKIK: include start and each frame below end + 1."""
        self._require_transaction()
        if mode not in ('fk', 'ik'):
            raise ValueError('原版动画烘焙方向需要 fk / ik')
        c = self._cmds
        raw = getattr(c, 'raw', c)
        if not self.original_control_sets(ui_name, **state):
            raise ValueError('No controlSets detected. select a controller')
        requested = tuple(name for name in limbs.split('|') if name) if isinstance(limbs, str) else tuple(limbs)
        if not requested:
            raise ValueError('请选择要烘焙的原版 FKIK 系统')
        saved = _current_registration(self)
        # Existing spline translation registration is part of the same source
        # alignment, not a substitute sampling or animation-transfer routine.
        if saved is None:
            saved, selected = _native_selected(self, requested)
        else:
            catalog = _bindings(saved)
            selected = []
            for name in requested:
                rows = catalog.get(name, ())
                if len(rows) != 1:
                    raise CharacterRegistryError('原版 FKIK 系统不存在或不唯一：' + name)
                selected.append(rows[0])
        if not getattr(saved, 'native_scene', False) and any(kind == 'spline' for kind, _, _ in selected):
            saved = self.enable_source_spline_first_translation(saved)
            catalog = _bindings(saved)
            selected = [catalog[name][0] for name in requested]
        start = float(c.playbackOptions(query=True, minTime=True))
        end = float(c.playbackOptions(query=True, maxTime=True))
        if not isfinite(start) or not isfinite(end) or end < start:
            raise ValueError('原版动画烘焙需要有效播放范围')
        auto = bool(c.autoKeyframe(query=True, state=True))
        current = float(c.currentTime(query=True))
        if baking_mocap is None:
            from .maya_source_limb_matching import original_baking_mocap
            baking_mocap = original_baking_mocap(c)
        self._transaction_changed = True
        if progress is not None:
            raw.progressBar(progress, edit=True, status='Baking', beginProgress=True,
                            isInterruptable=True, minValue=int(start), maxValue=int(end) + 1)
        sampled = []
        try:
            if not auto:
                c.autoKeyframe(state=True)
            c.currentTime(start)
            for kind, binding, plug in selected:
                c.setAttr(plug, 0 if mode == 'ik' else 10)
                if kind == 'rp':
                    from .maya_source_limb_matching import switch
                    switch(self, saved, binding, mode, baking_mocap=baking_mocap)
                else:
                    self.switch_source_character_spline(saved, binding, mode)
            frame = start
            while frame < end + 1:
                if progress is not None:
                    raw.progressBar(progress, edit=True, step=1)
                    if raw.progressBar(progress, query=True, isCancelled=True):
                        raise RuntimeError('Interrupted')
                c.currentTime(frame)
                for kind, binding, _ in selected:
                    if kind == 'rp':
                        from .maya_source_limb_matching import apply
                        apply(self, saved, binding, mode, align_only=True,
                              force=True, baking=True, baking_mocap=baking_mocap)
                    else:
                        self.align_source_character_spline(saved, binding, mode, baking=True)
                sampled.append(frame)
                frame += 1
            return tuple(sampled)
        finally:
            c.currentTime(current)
            if not auto:
                c.autoKeyframe(state=False)
            if progress is not None:
                raw.progressBar(progress, edit=True, endProgress=True)
