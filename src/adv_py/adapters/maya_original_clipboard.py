"""Native pose / animation clipboard, ADV MEL 11881–11997 and 12066–12178.

Use the original Maya ASCII carrier and Maya's copyKey/pasteKey. Animation
curves are never approximated by sampled poses or rewritten as JSON keys.
"""
from pathlib import Path
import os
import shlex

from .maya_original_control_identity import source_control_name, source_control_from_role


def clipboard_path(raw, animation):
    directory = raw.internalVar(userTmpDir=True).replace('\\', '/')
    if '~' in directory:
        directory = '/'.join(os.environ.get('USERNAME', part) if '~' in part else part
                             for part in directory.split('/'))
    return Path(directory) / 'AdvancedSkeleton' / 'Selector' / ('ClipBoard' + str(int(animation)) + '.ma')


def _attributes(raw):
    from maya import mel
    channel_box = mel.eval('$advPyChannelBox=$gChannelBoxName')
    return tuple(attribute for flag in ('selectedMainAttributes', 'selectedShapeAttributes',
                                       'selectedHistoryAttributes', 'selectedOutputAttributes')
                 for attribute in raw.channelBox(channel_box, query=True, **{flag: True}) or ())


def _helper(raw, name):
    # Helpers are root objects in the source, even for a namespaced character.
    # Existing objects are never mistaken for the temporary carrier we own.
    if raw.objExists(':' + name):
        raise ValueError('原版剪贴板临时对象已存在：' + name)
    return raw.createNode('transform', name=':' + name)


class MayaOriginalClipboardMixin:
    def copy_original_control_clipboard(self, animation=False, *, ui_name='', selected_attributes=None,
                                        modifiers=None, destination=None, progress=None, **state):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, 'raw', c)
        selection = tuple(c.ls(selection=True) or ())
        selected_attributes = _attributes(raw) if selected_attributes is None else tuple(selected_attributes)
        modifiers = raw.getModifiers() if modifiers is None else modifiers
        only_selected = bool(modifiers & (4 | 8))
        sets = self.original_control_sets(ui_name, **state)
        if not sets:
            raise ValueError('No controlSets detected. select a controller')
        controls = list(c.sets(sets, query=True) or ())
        if only_selected:
            # Source overwrites this array from index zero; its existing tail
            # remains when fewer controls are selected than belong to the set.
            owned = getattr(c, 'identity', None)
            picked = [node for node in selection if owned is None or owned.owns(self.scene_address(node))]
            for index, node in enumerate(picked):
                if index < len(controls):
                    controls[index] = node
                else:
                    controls.append(node)
        elif not c.objExists(sets[0]):
            raise ValueError('Object :"' + sets[0] + '" does not exists !')
        if not controls:
            raise ValueError('No Controls Available!')
        path = Path(destination) if destination is not None else clipboard_path(raw, animation)
        info = None
        self._transaction_changed = True
        if progress:
            raw.progressBar(progress, edit=True, status='Storing Data', beginProgress=True,
                            isInterruptable=True, minValue=0, maxValue=len(controls))
        try:
            info = _helper(raw, 'poserAnimationInfo')
            raw.addAttr(info, longName='cmd', dataType='string')
            raw.select(info)
            commands = []
            for control in controls:
                if progress:
                    raw.progressBar(progress, edit=True, step=1)
                    if raw.progressBar(progress, query=True, isCancelled=True):
                        raise RuntimeError('Interrupted')
                keyable = c.listAttr(control, keyable=True, multi=True, shortNames=True) or ()
                attrs = selected_attributes if only_selected and selected_attributes else keyable
                for attribute in attrs:
                    plug = control + '.' + attribute
                    for available in keyable:
                        if c.getAttr(plug, lock=True) or attribute != available:
                            continue
                        target = source_control_name(self, control) + '.' + attribute
                        if not animation:
                            value = c.getAttr(plug)
                            commands.append('setAttr ' + target + ' ' + str(int(value) if isinstance(value, bool) else value) + ';')
                        else:
                            for curve in c.listConnections(plug, type='animCurve', source=True, destination=False) or ():
                                raw.select(self.scene_address(curve), add=True)
                                commands.append('connectAttr ' + self.scene_address(curve).lstrip(':') + '.output ' + target + ';')
            raw.setAttr(info + '.cmd', ''.join(commands), type='string')
            path.parent.mkdir(parents=True, exist_ok=True)
            raw.file(path.as_posix(), force=True, options='v=0', type='mayaAscii', exportSelected=True)
            return str(path)
        finally:
            if info is not None and raw.objExists(info):
                raw.delete(info)
            c.select(selection, replace=True) if selection else c.select(clear=True)
            if progress:
                raw.progressBar(progress, edit=True, endProgress=True)

    def paste_original_control_clipboard(self, animation=False, *, ui_name='', modifiers=None,
                                         source=None, project_name='Selector', **state):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, 'raw', c)
        modifiers = raw.getModifiers() if modifiers is None else modifiers
        offset = float(c.currentTime(query=True)) if modifiers & 1 else 0.
        preserve_main = bool(modifiers & (4 | 8))
        selection = tuple(c.ls(selection=True) or ())
        if not self.original_control_sets(ui_name, **state):
            raise ValueError('No controlSets detected. select a controller')
        auto = bool(c.autoKeyframe(query=True, state=True))
        path = Path(source) if source is not None else clipboard_path(raw, animation)
        from .maya_native_animation_bake_boundary import capture, finish
        sets = self.original_control_sets(ui_name, **state)
        boundary = capture(self, tuple(self.scene_address(node) for node in c.sets(sets, query=True) or ()))
        helper = None
        reference = None
        self._transaction_changed = True
        try:
            if auto:
                c.autoKeyframe(state=False)
            if not raw.file(path.as_posix(), query=True, exists=True):
                raise ValueError('CLipboard file:"' + path.as_posix() + '" not found')
            nodes = raw.file(path.as_posix(), reference=True, type='mayaAscii', namespace=project_name,
                             options='v=0;p=17', returnNewNodes=True)
            if nodes:
                reference = raw.referenceQuery(nodes[0], referenceNode=True)
            carriers = [node for node in nodes if node.rsplit('|', 1)[-1].rsplit(':', 1)[-1] == 'poserAnimationInfo']
            if len(carriers) != 1:
                raise ValueError('原版剪贴板没有唯一 poserAnimationInfo')
            info = carriers[0]
            prefix = info.rsplit('|', 1)[-1].removesuffix('poserAnimationInfo')
            text = raw.getAttr(info + '.cmd') or ''
            helper = _helper(raw, 'tempXform')
            missing = []
            for statement in text.split(';'):
                if not statement.strip():
                    continue
                tokens = shlex.split(statement)
                if len(tokens) != 3 or tokens[0] not in ('setAttr', 'connectAttr'):
                    raise ValueError('原版剪贴板指令格式无效：' + statement)
                command, a, b = tokens
                address = a if command == 'setAttr' else b
                node, attribute = address.split('.', 1)
                if preserve_main and node.endswith('Main'):
                    continue
                target = source_control_from_role(self, node) + '.' + attribute
                if not c.objExists(target):
                    missing.append(self.scene_address(target))
                    continue
                if command == 'setAttr':
                    try:
                        c.setAttr(target, float(b))
                    except RuntimeError:
                        # MEL catch continues on a locked or connected channel.
                        pass
                else:
                    temporary = helper + '.' + attribute
                    if not raw.attributeQuery(attribute, node=helper, exists=True):
                        raw.addAttr(helper, keyable=True, longName=attribute, attributeType='double')
                    raw.connectAttr(prefix + a, temporary, force=True)
                    raw.copyKey(helper, time=':', hierarchy='none', attribute=attribute)
                    raw.pasteKey(self.scene_address(target), option='merge', copies=1, connect=False,
                                 timeOffset=offset, floatOffset=0, valueOffset=0)
            if missing:
                c.warning('The following attributes can not be set:' + ','.join(missing) + ',')
            finish(self, boundary, mark_baked=False)
            return tuple(missing)
        finally:
            if helper is not None and raw.objExists(helper):
                raw.delete(helper)
            if reference is not None:
                raw.file(removeReference=True, referenceNode=reference)
            c.select(selection, replace=True) if selection else c.select(clear=True)
            if auto:
                c.autoKeyframe(state=True)
