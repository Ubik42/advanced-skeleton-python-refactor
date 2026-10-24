"""Original SwitchPivot / PivotControl, MEL 13617–13700."""
from .maya_original_control_identity import source_control_name, registration
from .maya_unreal_face_display import vector


def control_diameter(c, control):
    """asControlDiameter: union every shape bound, then multiply world scale."""
    scale = c.xform(control, query=True, worldSpace=True, scale=True)
    bounds = [(vector(c, shape + '.boundingBoxMin'), vector(c, shape + '.boundingBoxMax'))
              for shape in c.listRelatives(control, shapes=True) or ()]
    if not bounds:
        return 0.
    return max(0., *((max(high[axis] for _, high in bounds) - min(low[axis] for low, _ in bounds))
                     * scale[axis] for axis in range(3)))


class MayaOriginalPivotControlsMixin:
    def switch_original_control_pivot(self, selection=None):
        """Move Extra's pivot frame at this frame, holding the control pose."""
        self._require_transaction()
        c = self._cmds
        selected = tuple(c.ls(selection=True) or ()) if selection is None else tuple(selection)
        if len(selected) != 2:
            raise ValueError('Select 1 target object + 1 control')
        target, control = selected
        if '_' not in source_control_name(self, control) and '_' in source_control_name(self, target):
            target, control = control, target
        if 'Extra' in source_control_name(self, control):
            control = c.listRelatives(control, children=True, type='transform')[0]
        extra = c.listRelatives(control, parent=True)[0]
        if not c.objExists(extra):
            raise ValueError('parent of "' + control + '" is not a valid ExtraControl')
        position = c.xform(control, query=True, worldSpace=True, translation=True)
        rotation = c.xform(control, query=True, worldSpace=True, rotation=True)
        # Read both frames in original order before changing clock or Auto Key.
        c.xform(extra, query=True, worldSpace=True, translation=True)
        c.xform(extra, query=True, worldSpace=True, rotation=True)
        target_position = c.xform(target, query=True, worldSpace=True, translation=True)
        target_rotation = c.xform(target, query=True, worldSpace=True, rotation=True)
        auto = bool(c.autoKeyframe(query=True, state=True))
        current = c.currentTime(query=True)
        self._transaction_changed = True
        plugs = (extra + '.t', extra + '.r', control + '.t', control + '.r')
        try:
            if auto:
                c.autoKeyframe(state=False)
            c.currentTime(current - 1)
            c.setKeyframe(*plugs)
            c.currentTime(current)
            c.xform(extra, worldSpace=True, translation=target_position, rotation=target_rotation)
            c.xform(control, worldSpace=True, translation=position, rotation=rotation)
            c.setKeyframe(*plugs)
        finally:
            c.currentTime(current)
            if auto:
                c.autoKeyframe(state=True)
        c.select(extra)
        return extra

    def add_original_pivot_controls(self, selection=None):
        self._require_transaction()
        c = self._cmds
        selected = tuple(c.ls(selection=True) or ()) if selection is None else tuple(selection)
        before = registration(self)
        if before is not None:
            before = self.read_character_registration()
        created = []
        for control in selected:
            if control.endswith('_PivotControl'):
                raise ValueError('Selected object is already a PivotController.')
            pivot = control + '_PivotControl'
            self._transaction_changed = True
            if c.objExists(pivot):
                c.delete(pivot)
            c.spaceLocator(name=pivot)
            c.parent(pivot, control, relative=True)
            scale = control_diameter(c, control) * .75
            if scale == 0:
                scale = 1.
            c.setAttr(pivot + '.localScale', scale, scale, scale, type='float3')
            c.connectAttr(pivot + '.t', control + '.rotatePivot')
            c.connectAttr(pivot + '.t', control + '.scalePivot')
            created.append(pivot)
        if before is not None and created:
            from .maya_original_export_preparation import MayaOriginalExportPreparationHost
            MayaOriginalExportPreparationHost._remember_export_preparation(self, before)
        return tuple(created)
