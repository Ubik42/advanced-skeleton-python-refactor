"""Original unused-attribute cleanup and Controller tags in Python."""
from dataclasses import replace
from contextlib import contextmanager

from adv_py.core.character_registry import CharacterChannel
from adv_py.core.original_optimize import (
    removable_original_control_attribute, UNUSED_ATTRIBUTE_EXCEPTIONS,
)
from .maya_original_control_identity import registration, source_main, leaf
from .maya_original_export_preparation import MayaOriginalExportPreparationHost
from .maya_game_registration import scene_ids, remember_generated_nodes


class MayaOriginalOptimizeHost(MayaOriginalExportPreparationHost):
    @contextmanager
    def _controller_creation_namespace(self):
        # Scoped command hosts already apply their creation namespace. The
        # root host must also avoid creating tags in a user's current namespace.
        c = getattr(self._cmds, 'raw', self._cmds)
        previous = c.namespaceInfo(currentNamespace=True, absoluteName=True)
        try:
            c.namespace(setNamespace=':' + (self.namespace or ''))
            yield
        finally:
            c.namespace(setNamespace=previous)

    def preflight_original_optimize(self, operation):
        c = self._cmds
        if operation == 'remove_unused_attributes':
            self._unique('ControlSet', 'objectSet')
        elif operation == 'tag_all_controllers':
            if float(str(getattr(c, 'raw', c).about(version=True)).split()[0]) < 2018:
                raise ValueError('Controller 标签功能需要 Maya 2018 或以上')
            source_main(self)
        elif operation in ('delete_unused_nodes', 'delete_saved_uis'):
            pass
        else:
            raise ValueError('未知原版 Optimize 操作')

    def delete_unused_original_nodes(self):
        self._require_transaction()
        from maya import mel
        c = getattr(self._cmds, 'raw', self._cmds)
        before = frozenset(c.ls(uuid=True) or [])
        self._transaction_changed = True
        # Maya's Hypershade cleanup is a native host utility, not ADV logic.
        mel.eval('hyperShadePanelMenuCommand("", "deleteUnusedNodes");')
        return tuple(sorted(before - frozenset(c.ls(uuid=True) or [])))

    def delete_saved_original_uis(self):
        self._require_transaction()
        c = getattr(self._cmds, 'raw', self._cmds)
        self._transaction_changed = True
        removed = []
        for query, flags in (('sceneConfigurationScriptNode', {}),
                             ('uiConfigurationScriptNode', {}),
                             (None, {'type': 'hyperView'})):
            nodes = c.ls(query, **flags) if query else c.ls(**flags)
            if nodes:
                c.delete(nodes)
                removed.extend(nodes)
        return tuple(removed)

    def flush_original_saved_ui_undo(self):
        getattr(self._cmds, 'raw', self._cmds).flushUndo()

    def remove_unused_original_attributes(self):
        """asRemoveAllUnusedAttributes: no connected/locked attribute edits."""
        self._require_transaction()
        c = self._cmds
        before = registration(self)
        main = source_main(self)
        removed = []
        for control in c.sets('ControlSet', query=True) or []:
            if leaf(control) == leaf(main):
                continue
            for attribute in c.listAttr(control, userDefined=True) or []:
                plug = control + '.' + attribute
                locked = bool(c.getAttr(plug, lock=True))
                if locked:
                    continue
                # Source never queries connections for its protected fields.
                if attribute in UNUSED_ATTRIBUTE_EXCEPTIONS:
                    continue
                connections = c.listConnections(plug, source=True,
                                                  destination=True) or []
                if removable_original_control_attribute(attribute,
                        locked=locked, connected=bool(connections)):
                    getattr(c, 'raw', c).warning(
                        'Found un-used attribute:"' + plug + '", now removing this.')
                    self._transaction_changed = True
                    c.deleteAttr(plug)
                    removed.append(plug)
        self._remember_export_preparation(before)
        return tuple(removed)

    def tag_original_controllers(self):
        """asTagAllControllers including Face boxes and Parallel-evaluation edge."""
        self._require_transaction()
        c = self._cmds
        before = registration(self)
        previous = c.ls(selection=True) or []
        nodes_before = scene_ids(self)
        main = source_main(self)
        controls = list(c.sets('ControlSet', query=True) or []) if c.objExists('ControlSet') else []
        if c.objExists('FaceControlSet'):
            controls.extend(c.sets('FaceControlSet', query=True) or [])
        if c.objExists('ctrlBox'):
            controls.append('ctrlBox')
            controls.extend(c.listRelatives('ctrlBox', children=True, type='transform') or [])
        self._transaction_changed = True
        for control in controls:
            tag = leaf(control) + '_tag'
            if c.objExists(tag):
                c.delete(tag)
        try:
            c.select(controls, replace=True)
            # Maya's TagAsController runtime command is exactly `controller`.
            # Keep its actual selection and native node naming behavior.
            with self._controller_creation_namespace():
                c.controller()
            proximity = main + '.showOnMouseProximity'
            if not c.objExists(proximity):
                c.addAttr(main, keyable=True, longName='showOnMouseProximity',
                          attributeType='bool', defaultValue=True)
                c.setAttr(proximity, keyable=False, channelBox=True)
            mpd = 'showOnMouseProximityMPD'
            if not c.objExists(mpd):
                c.createNode('multiplyDivide', name=mpd)
                c.setAttr(mpd + '.input2X', 2)
                c.connectAttr(proximity, mpd + '.input1X')
            tagged = []
            for control in controls:
                tag = leaf(control) + '_tag'
                if not c.objExists(tag):
                    continue
                c.setAttr(tag + '.isHistoricallyInteresting', 0)
                if leaf(control) != leaf(main):
                    for attribute in ('vMode', 'visibilityMode'):
                        if c.objExists(tag + '.' + attribute):
                            c.connectAttr(mpd + '.outputX', tag + '.' + attribute)
                            break
                    if not c.objExists(control + '.vMode'):
                        c.addAttr(control, keyable=False, longName='vMode', attributeType='bool')
                    c.connectAttr(tag + '.visibilityMode', control + '.vMode')
                tagged.append(tag)
            main_path = (c.ls(main, long=True) or [main])[0]
            if before is not None and not any(channel.node == main_path
                    and channel.attribute == 'showOnMouseProximity' for channel in before.channels):
                before = replace(before, channels=(*before.channels,
                    CharacterChannel('display.showOnMouseProximity', main_path,
                                     'showOnMouseProximity', 0., 1.)))
            added = remember_generated_nodes(self, nodes_before)
            self._remember_export_preparation(before, added)
            return tuple(tagged)
        finally:
            c.select(previous, replace=True) if previous else c.select(clear=True)


def has_original_controller_tags(host):
    """Use the live native Main→MPD edge, not an invented completion marker."""
    c = host._cmds
    if not c.objExists('showOnMouseProximityMPD'):
        return False
    main = source_main(host)
    return bool(c.objExists(main + '.showOnMouseProximity')
                and c.nodeType('showOnMouseProximityMPD') == 'multiplyDivide'
                and c.isConnected(main + '.showOnMouseProximity',
                                  'showOnMouseProximityMPD.input1X'))
