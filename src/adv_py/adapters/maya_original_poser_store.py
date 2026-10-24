"""Original Poser capture, label and media operations (MEL 11750/27789)."""
from pathlib import Path
import os
import re
import subprocess
import sys

from .maya_original_clipboard import _attributes, _helper, clipboard_path
from .maya_original_control_identity import source_control_name


def icon_directory(raw):
    # Both original procedures share asGetTempDirectory, retaining its path.
    return clipboard_path(raw, False).parents[1] / 'Poser' / 'untitled'


def child_index(raw, ui_name):
    order = raw.gridLayout(ui_name + 'GridLayout', query=True, gridOrder=True) or ()
    last = 0
    for index, control in enumerate(order, 1):
        if control.rsplit('|',1)[-1].startswith('asPoser'):
            last = index
    return last + 1


def replace_extension(path, extension):
    return Path(re.sub(r'[.][a-z][a-z][a-z]', '.' + extension, str(path), count=1))


class MayaOriginalPoserStoreMixin:
    def capture_original_poser_command(self, ui_name='asPoserDefault', animation=False,
                                      *, only_selected=None, selected_attributes=None, progress=None, **state):
        """asPoserGetCmd: its checkbox is independent of clipboard modifiers."""
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, 'raw', c)
        selection = tuple(c.ls(selection=True) or ())
        if only_selected is None:
            only_selected = bool(raw.checkBox('asPoserOnlySel', query=True, value=True))
        attrs = _attributes(raw) if selected_attributes is None else tuple(selected_attributes)
        sets = self.original_control_sets(ui_name, **state)
        if not only_selected and not sets:
            raise ValueError('No ControlSets')
        if only_selected:
            identity = getattr(c, 'identity', None)
            controls = tuple(node for node in selection if identity is None or identity.owns(self.scene_address(node)))
        else:
            if not c.objExists(sets[0]):
                raise ValueError('Object :"' + sets[0] + '" does not exists !')
            controls = tuple(c.sets(sets, query=True) or ())
        if not controls:
            raise ValueError('No Controls Available!')
        child = child_index(raw, ui_name)
        path = icon_directory(raw) / ('untitled_' + str(child) + '.ma')
        info = None
        rows = []
        self._transaction_changed = True
        if progress:
            raw.progressBar(progress, edit=True, status='Storing Data', beginProgress=True,
                            isInterruptable=True, minValue=0, maxValue=len(controls))
        try:
            c.select(clear=True)
            if animation:
                info = _helper(raw, 'poserAnimationInfo')
                raw.addAttr(info, longName='cmd', dataType='string')
                raw.select(info)
            for control in controls:
                if progress:
                    raw.progressBar(progress, edit=True, step=1)
                    if raw.progressBar(progress, query=True, isCancelled=True):
                        raise RuntimeError('Interrupted')
                keyable = c.listAttr(control, keyable=True, multi=True, shortNames=True) or ()
                chosen = attrs if only_selected and attrs else keyable
                role = source_control_name(self, control)
                for attribute in chosen:
                    plug = control + '.' + attribute
                    for available in keyable:
                        if c.getAttr(plug, lock=True) or available != attribute:
                            continue
                        target = role + '.' + attribute
                        if animation:
                            for curve in c.listConnections(plug, type='animCurve', source=True, destination=False) or ():
                                address = self.scene_address(curve).lstrip(':')
                                raw.select(address, add=True)
                                rows.append('connectAttr ' + address + '.output ' + target + ';')
                        else:
                            value = c.getAttr(plug)
                            rows.append(target + ' ' + str(int(value) if isinstance(value, bool) else value) + ';')
            text = ''.join(rows)
            if animation:
                raw.setAttr(info + '.cmd', text, type='string')
                path.parent.mkdir(parents=True, exist_ok=True)
                raw.file(path.as_posix(), force=True, options='v=0', type='mayaAscii', exportSelected=True)
            if not text:
                return ''
            return 'asLoadAttrs ' + ui_name if animation else 'asSetAttrs ' + ui_name + ' "' + text + '"'
        finally:
            if info is not None and raw.objExists(info):
                raw.delete(info)
            c.select(selection, replace=True) if selection else c.select(clear=True)
            if progress:
                raw.progressBar(progress, edit=True, endProgress=True)

    def rename_original_poser_button(self, child):
        raw = getattr(self._cmds, 'raw', self._cmds)
        widget = 'asPoserDefaultText' + str(child)
        if not raw.text(widget, query=True, exists=True):
            raise ValueError('Cant find `text` uiElement')
        label = raw.text(widget, query=True, label=True)
        response = raw.promptDialog(message='名称：', text=label, title='AdvancedSkeleton',
            button=('确定', '取消'), defaultButton='确定', cancelButton='取消', dismissString='取消')
        if response == '取消':
            return None
        label = raw.promptDialog(query=True, text=True)
        raw.text(widget, edit=True, label=label)
        return label

    def delete_original_poser_button(self, ui_name, child):
        raw = getattr(self._cmds, 'raw', self._cmds)
        image = Path(raw.iconTextButton(ui_name + 'IconTextButton' + str(child), query=True, image=True))
        # The original removes PNG/JPG only; it leaves animation and movie data.
        for file in (image, Path(re.sub(r'[.]png', '.jpg', str(image), count=1))):
            file.unlink(missing_ok=True)
        layout = ui_name + 'ColumnLayout' + str(child)
        raw.evalDeferred(lambda: raw.deleteUI(layout))
        return str(image)

    def view_original_poser_media(self, ui_name, child):
        raw = getattr(self._cmds, 'raw', self._cmds)
        image = raw.iconTextButton(ui_name + 'IconTextButton' + str(child), query=True, image=True)
        animation = int(raw.rowColumnLayout(ui_name + 'RowColumnLayout' + str(child), query=True, annotation=True))
        media = replace_extension(image, 'avi' if animation else 'png')
        if os.name == 'nt':
            os.startfile(media)
        else:
            # Invoke the native host's registered media opener, as system(load).
            subprocess.Popen(['open' if sys.platform=='darwin' else 'xdg-open', str(media)])
        return str(media)
