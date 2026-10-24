"""Original control-set selection, asNameControlSetsFromUiName (23174)."""


def resolve(host, ui_name='', *, selector_sets=None, picker_tab=None, poser_sets=None):
    """Use actual selection and authored set names, without assuming a rig kind.

    Explicit selector/picker/poser values are their existing UI state passed
    across the host boundary. With no UI name the source defaults to Body,
    except when the first selected object belongs to FaceControlSet.
    """
    c = host._cmds
    raw = getattr(c, 'raw', c)
    if ui_name == 'bodySetup':
        return ('ControlSet',)
    if ui_name == 'faceSetup':
        return ('FaceControlSet',)
    if selector_sets is not None:
        names = selector_sets.split() if isinstance(selector_sets, str) else selector_sets
        return tuple(name for name in names if c.objExists(name))
    if ui_name and raw.text(ui_name + 'ControlSetsText', query=True, exists=True):
        names = raw.text(ui_name + 'ControlSetsText', query=True, label=True).split()
        return tuple(name for name in names if c.objExists(name))
    if ui_name == 'asPicker' and picker_tab is None and raw.tabLayout('asPickerTabLayout', query=True, exists=True):
        labels = raw.tabLayout('asPickerTabLayout', query=True, tabLabel=True)
        index = raw.tabLayout('asPickerTabLayout', query=True, selectTabIndex=True)
        picker_tab = labels[index - 1]
    if ui_name == 'asPicker' and picker_tab is not None:
        return ('FaceControlSet' if 'face' in picker_tab else 'ControlSet',)
    if ui_name == 'asPoserDefault' and poser_sets is not None:
        return tuple(poser_sets)
    if ui_name == 'asPoserDefault' and raw.menuItem('asPoserControlSetsMenu', query=True, exists=True):
        return tuple(raw.menuItem(item, query=True, label=True)
                     for item in raw.menu('asPoserControlSetsMenu', query=True, itemArray=True) or ()
                     if raw.menuItem(item, query=True, checkBox=True))
    if ui_name == 'asPanel':
        # The original external ControlPanel exposes its chosen set through
        # scene.items(); inspect that existing state rather than a MEL global.
        import __main__
        ui = getattr(__main__, 'panel_ui', None)
        scene = getattr(ui, 'scene', None)
        items = getattr(scene, 'items', None)
        entries = items() if callable(items) else ()
        selected = next((item.select_str for item in entries
                         if hasattr(item, 'select_str') and 'ControlSet' in item.select_str), '')
        return ('FaceControlSet' if selected == 'FaceControlSet' else 'ControlSet',)
    result = ('ControlSet',) if c.objExists('ControlSet') else ()
    if ui_name == '' and c.objExists('FaceControlSet'):
        selection = c.ls(selection=True) or ()
        if selection and c.sets(selection[0], isMember='FaceControlSet'):
            result = ('FaceControlSet',)
    return result


class MayaOriginalControlSetsMixin:
    def original_control_sets(self, ui_name='', **state):
        return resolve(self, ui_name, **state)

    def mirror_original_control_pose(self, ui_name='', *, side=None, space=None, axis=None, selection_only=None, **state):
        """asMirror public options, including the existing native options window."""
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, 'raw', c)
        names = ('asMOSide','asMOSpace','asMOAxis','asMOSelOnly')
        values = ['asMOSideR2L','asMOSpaceMain','asMOAxisX','asMOSelOnlyAll']
        if raw.window('asMirrorOptions',query=True,exists=True):
            for name in names:
                selected = raw.radioCollection(name+'RadioCollection',query=True,select=True)
                raw.optionVar(stringValue=(name,selected))
        for index,name in enumerate(names):
            if raw.optionVar(exists=name):values[index]=raw.optionVar(query=name)
        side = values[0].removeprefix('asMOSide') if side is None else side
        space = values[1].removeprefix('asMOSpace') if space is None else space
        axis = values[2].removeprefix('asMOAxis') if axis is None else axis
        selection_only = values[3]=='asMOSelOnlySel' if selection_only is None else selection_only
        controls = c.ls(selection=True,long=True) or [] if selection_only else None
        from .maya_original_control_mirror import mirror_original_controls
        return mirror_original_controls(self,controls,side=side,space=space,axis=axis,
                                        ui_name=ui_name,ui_state=state)

    def go_to_original_control_build_pose(self, ui_name='', *, t_pose=False, preserve_main=None, **state):
        """The public original command uses the selected UI's first control set."""
        self._require_transaction()
        c = self._cmds
        sets = self.original_control_sets(ui_name, **state)
        if not sets:
            raise ValueError('No controlSets detected. select a controller')
        if preserve_main is None:
            raw = getattr(c, 'raw', c)
            preserve_main = bool(raw.getModifiers() & 4)
        failed = self.go_to_original_corrective_build_pose(
            face=sets[0].endswith('FaceControlSet'), t_pose=t_pose, preserve_main=preserve_main)
        for statement in failed:
            c.warning('Failed: ' + statement + '\n')
        if failed and ui_name in ('bodySetup', 'faceSetup'):
            rows = ''.join(statement + '\n' for statement in failed[:26])
            if len(failed) > 26:
                rows += '\n...And ' + str(len(failed)) + ' more..'
            message = ('The following commands failed,\n( Possibly these are controllers that have been removed)\n'
                       'Remove these commands from the Pose-command ?\n\n' + rows)
            choice = c.confirmDialog(title='Confirm', message=message,
                                     button=('Ok, Remove', 'Cancel'), defaultButton='Ok')
            if choice == 'Ok, Remove':
                self.update_original_driving_pose_attributes()
        return failed

    def clean_original_control_animation(self, ui_name='', **state):
        """asDeleteStaticChannels: native confirmation, set expansion and flags."""
        self._require_transaction()
        c = self._cmds
        selected = tuple(c.ls(selection=True, long=True) or ())
        sets = self.original_control_sets(ui_name, **state)
        if not sets:
            raise ValueError('No controlSets detected. select a controller')
        choice = c.confirmDialog(title='Confirm', message=(
            'Clean animation ?\nThis will delete static channels,\n'
            'which means remove all animation where the value is not changing'),
            button=('Yes', 'No'), defaultButton='Yes', cancelButton='No', dismissString='No')
        if choice != 'Yes':
            return ()
        from .maya_original_control_identity import registration
        from .maya_static_animation_boundary import capture, finish
        saved = registration(self)
        if saved is not None:
            saved = self.read_character_registration()
        boundary = capture(self)
        self._transaction_changed = True
        try:
            c.select(sets, replace=True)
            c.delete(staticChannels=True, unitlessAnimationCurves=False,
                     hierarchy='none', controlPoints=False, shape=True)
            finish(self, boundary)
            if saved is not None:
                # Native deletion may collapse pairBlend nodes. Refresh the
                # existing registry via the same exporter preservation path.
                from .maya_original_export_preparation import MayaOriginalExportPreparationHost
                MayaOriginalExportPreparationHost._remember_export_preparation(self, saved)
        finally:
            c.select(selected, replace=True) if selected else c.select(clear=True)
        return sets
