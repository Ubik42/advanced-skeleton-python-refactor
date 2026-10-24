"""Native Mannequin FBX passes, ADV 6.925 MEL 60112–60634.

FBX plug-in commands and scene-authored custom export hooks cross the MEL
boundary. Rig creation, cleanup, native namespace callbacks and restoration
are Python scene operations; no ADV rig procedure is used as a fallback.
"""
import json
from pathlib import Path
import re
import shutil
from contextlib import contextmanager

from adv_py.core.original_fbx_export import (
    MANNEQUIN_EXPORT_CLEANUP, source_fbx_preset, source_fbx_path_from_history,
)


def _namespace_callback(text):
    """Decode the one native callback used here, without evaluating scripts."""
    if not text:
        return None
    match = re.fullmatch(r'\s*asFbxExportNameSpaceSelected\s+(?:"([^"\n]+)"|([^\s;]+))\s*;?\s*', text)
    if match is None:
        raise ValueError('导出回调不是独立的原版命名空间命令')
    value = match[1] or match[2]
    if value != ':' and (value.startswith(':') or value.endswith(':')
            or any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', part)
                   for part in value.split(':'))):
        raise ValueError('FBX 命名空间回调参数无效')
    return value


def _plug_identity(c, plug):
    """Keep an attribute's node identity through native export renames."""
    node, attribute = plug.split('.', 1)
    identities = c.ls(node, uuid=True) or []
    if len(identities) != 1:
        raise ValueError('FBX 临时连接节点不存在或不唯一：' + node)
    return identities[0], attribute


def _resolve_plug_identity(c, identity):
    nodes = c.ls(identity[0], long=True) or []
    if len(nodes) != 1:
        raise RuntimeError('FBX 临时连接的原节点已被删除：' + identity[0])
    return nodes[0] + '.' + identity[1]


def _export_callback_text(value):
    """Native exportFbxPre/Post are scene-authored MEL extension strings."""
    if not isinstance(value, str):
        raise ValueError('fbxExportOptions 的导出回调必须是字符串属性')
    return value


class MayaMannequinExportMixin:
    def _capture_mannequin_modifiers(self):
        override = getattr(self, '_mannequin_ctrl_button_override', None)
        self._mannequin_ctrl_button = (override if override is not None else
                                      bool(self._mannequin_cmds().getModifiers() & 4))

    @contextmanager
    def transaction(self, label):
        """Run native scene-root export assets in Maya's root namespace."""
        with super().transaction(label):
            c = self._mannequin_cmds()
            previous = c.namespaceInfo(currentNamespace=True, absoluteName=True)
            try:
                c.namespace(setNamespace=':')
                self._transaction_changed = True
                yield
            finally:
                c.namespace(setNamespace=previous)

    def confirm_native_fbx_export(self):
        """Shared native asExportFbxBrowser warning and Root Motion prompt."""
        c = self._mannequin_cmds()
        fit = self.scene_address('FitSkeleton.useOffsetParentMatrix')
        if c.objExists(fit) and c.getAttr(fit) and not c.objExists('asBatch'):
            c.confirmDialog(title='Warning', message=(
                'OPM rig detected.\n\nIn FBX-settings, Turn ON:,\n\n'
                'Animation & BakeAnimation.'), button=['OK'])
        if not self.namespace and not c.objExists('asMannequinExporting'):
            if not self._cmds.objExists('RootMotion_M'):
                result = c.confirmDialog(title='Confirm', message=(
                    'For Game Engines,\nit is recommended to use RootMotion-Joint\n\n'
                    'Add this now ?'), button=['OK', 'Skip', 'Cancel'],
                    defaultButton='OK', dismissString='Cancel')
                if result == 'Cancel':
                    return False
                if result == 'OK':
                    from adv_py.application.body_game_root_motion import SwitchGameRootMotion
                    command = SwitchGameRootMotion(self)
                    if self._transaction_active:
                        command.apply_in_transaction(create=True)
                    else:
                        command.apply(create=True)
        return True

    def preflight_mannequin_export(self, destination, template_path, options):
        c = self._mannequin_cmds()
        self._capture_mannequin_modifiers()
        if destination is not None and (not destination.is_absolute()
                or destination.suffix.lower() != '.fbx' or not destination.parent.is_dir()):
            raise ValueError('请选择现有目录中的绝对 FBX 文件路径')
        if not Path(template_path).is_file() or Path(template_path).suffix.lower() != '.ma':
            raise FileNotFoundError('请选择原版 asUnreal.ma 模板')
        self._unique('DeformSet', 'objectSet')
        self._unique('ControlSet', 'objectSet')
        if not c.pluginInfo('fbxmaya', query=True, loaded=True):
            raise RuntimeError('请先加载 Maya 的 fbxmaya 插件')
        # Original existing fbxExportOptions takes precedence over the newly
        # selected namespace, including its user-authored MEL extension hooks.
        for attr in ('exportFbxPre', 'exportFbxPost'):
            plug = 'fbxExportOptions.' + attr
            if c.objExists(plug):
                _export_callback_text(c.getAttr(plug))

    def clear_mannequin_export_assets(self):
        self._require_transaction()
        c = self._mannequin_cmds()
        self._transaction_changed = True
        for node in MANNEQUIN_EXPORT_CLEANUP:
            if c.objExists(node):
                c.delete(node)

    def remove_unused_mannequin_joints(self):
        self._require_transaction()
        c = self._mannequin_cmds()
        self._transaction_changed = True
        c.select('|Geometry', hierarchy=True, replace=True)
        from .maya_original_skin_history import remove_unused_selected_skin_influences
        remove_unused_selected_skin_influences(c)
        # Maya's descendant order visits leaves before their parents. Do not
        # precompute leaves: removing a child can make its parent a new leaf.
        for joint in c.listRelatives('|root', allDescendents=True,
                                     type='joint', fullPath=True) or []:
            if (c.objExists(joint) and not c.listRelatives(joint, children=True, fullPath=True)
                    and not c.listConnections(joint + '.worldMatrix', source=False,
                                               destination=True, type='skinCluster')):
                c.delete(joint)

    def prepare_mannequin_export(self, options):
        self._require_transaction()
        c = self._mannequin_cmds()
        self._transaction_changed = True
        if options.keep_joints:
            c.setAttr('|root.visibility', 0)
        if c.objExists('unrealMannequinSkeletonScaleToMatch'):
            c.delete('unrealMannequinSkeletonScaleToMatch')
        history = Path(c.internalVar(userTmpDir=True)) / 'asExportSelectionAsFBXExportHistory.txt'
        history.unlink(missing_ok=True)
        if not getattr(self, '_mannequin_ctrl_button', False):
            c.createNode('transform', name='asMannequinExporting')
        self._export_added_namespace = False
        self._export_added_options = False
        if options.namespace:
            if not c.objExists('fbxExportOptions'):
                c.createNode('transform', name='fbxExportOptions')
                self._export_added_options = True
                for attr, value in (
                        ('exportFbxPre', 'asFbxExportNameSpaceSelected ' + options.namespace),
                        ('exportFbxPost', 'asFbxExportNameSpaceSelected ":"')):
                    c.addAttr('fbxExportOptions', longName=attr, dataType='string')
                    c.setAttr('fbxExportOptions.' + attr, value, type='string')
            if not c.namespace(exists=options.namespace):
                c.namespace(addNamespace=options.namespace)
                self._export_added_namespace = True

    def _prepare_native_fbx_preset(self):
        from maya import mel
        c = self._mannequin_cmds()
        version = str(c.pluginInfo('fbxmaya', query=True, version=True))
        preset = Path(c.internalVar(userAppDir=True)) / 'FBX' / 'Presets' / version / 'export' / 'User defined.fbxexportpreset'
        if not preset.is_file():
            c.warning('AdvancedSkeleton 找不到 FBX 用户预设：' + str(preset))
            return
        try:
            xml = source_fbx_preset(preset.read_bytes())
        except OSError:
            c.warning('无法读取 FBX 用户预设：' + str(preset))
            return
        backup = Path(c.internalVar(userTmpDir=True)) / 'AdvancedSkeleton_UserDefined_fbxexportpreset.backup'
        shutil.copyfile(preset, backup)
        try:
            preset.write_bytes(xml)
        except OSError:
            c.warning('无法写入 FBX 用户预设：' + str(preset))
            return
        mel.eval('FBXLoadExportPresetFile -f ' + json.dumps(preset.as_posix(), ensure_ascii=False) + ';')
        c.optionVar(stringValue=('defaultFileExportActiveType', 'FBX export'))

    @contextmanager
    def _native_fbx_export_history(self):
        """asExportSelectionAsFBX's log scope; restore it after errors too."""
        c = self._mannequin_cmds()
        history = Path(c.internalVar(userTmpDir=True)) / 'asExportSelectionAsFBXExportHistory.txt'
        history.unlink(missing_ok=True)
        previous_file = c.scriptEditorInfo(query=True, historyFilename=True)
        previous_write = c.scriptEditorInfo(query=True, writeHistory=True)
        try:
            c.scriptEditorInfo(historyFilename=str(history))
            c.scriptEditorInfo(writeHistory=True)
            yield history
        finally:
            c.scriptEditorInfo(writeHistory=previous_write)
            if previous_file:
                c.scriptEditorInfo(historyFilename=previous_file)

    def _native_fbx_selection_export(self, destination):
        """Native Maya Export Selection browser or explicit/batch FBX path.

        The browser exposes Maya's FBX settings, as in the original Export
        button. Explicit destinations use the original batch plug-in route.
        No ADV business procedure is evaluated here.
        """
        from maya import mel
        c = self._mannequin_cmds()
        with self._native_fbx_export_history() as history:
            self._prepare_native_fbx_preset()
            if destination is None and c.objExists('asBatch.exportFbxFileName'):
                destination = Path(c.getAttr('asBatch.exportFbxFileName'))
            if destination is not None:
                mel.eval('FBXExport -f ' + json.dumps(destination.as_posix(), ensure_ascii=False) + ' -s;')
            else:
                mel.eval('ExportSelection;')
        if destination is None:
            try:
                filename = source_fbx_path_from_history(history.read_text(encoding='utf-8', errors='replace'))
            except OSError:
                return None
            if not filename:
                raise RuntimeError('Maya 导出历史中没有找到 FBX 文件路径')
            destination = Path(filename)
        if not destination.is_file():
            raise RuntimeError('Maya 没有生成 FBX 文件：' + str(destination))
        return destination

    def _restore_original_fbx_world_roots(self):
        c = self._mannequin_cmds()
        restore = getattr(self, '_fbx_world_root_restore', [])
        while restore:
            node_id, parent_id = restore[0]
            node = c.ls(node_id, long=True) or []
            ancestor = c.ls(parent_id, long=True) or []
            if len(node) != 1 or len(ancestor) != 1:
                raise RuntimeError('FBX 临时脱离的原节点或父级无法恢复')
            c.parent(node[0], ancestor[0], absolute=True)
            restore.pop(0)

    @contextmanager
    def original_fbx_world_roots(self, roots):
        self._require_transaction()
        c = self._mannequin_cmds()
        if self.namespace or c.objExists('asMannequinExporting'):
            yield
            return
        self._transaction_changed = True
        restore = []
        self._fbx_world_root_restore = restore
        try:
            for root in roots:
                ancestors = c.listRelatives(root, parent=True, fullPath=True) or []
                if not ancestors:
                    continue
                node_id = c.ls(root, uuid=True)[0]
                parent_id = c.ls(ancestors[0], uuid=True)[0]
                c.parent(root, world=True, absolute=True)
                restore.append((node_id, parent_id))
            yield
        finally:
            try:
                self._restore_original_fbx_world_roots()
            finally:
                self._fbx_world_root_restore = []

    def _native_fbx_export_roots(self):
        """Preserve the source's ordered root overrides, including optional roots."""
        c = self._mannequin_cmds()
        root = self._unique('Root_M', 'joint')
        if c.objExists('|root'):
            root = '|root'
        if c.objExists(self._node('RootMotion_M')):
            root = self._unique('RootMotion_M', 'joint')
        if c.objExists('|GameSkeletonRoot_M'):
            root = '|GameSkeletonRoot_M'
        return (root, '|Geometry') if c.objExists('|Geometry') else (root,)

    def _fbx_namespace_selected(self, namespace):
        """asFbxExportNameSpaceSelected's child-first selected DAG rename."""
        self._require_transaction()
        c = self._mannequin_cmds()
        selected = c.ls(selection=True, long=True) or []
        descendants = c.listRelatives(selected, allDescendents=True, fullPath=True) or [] if selected else []
        # Read names before any mutation, as in the two native parallel arrays.
        names = [(path, path.rsplit('|', 1)[-1]) for path in (*descendants, *selected)]
        for path, name in names:
            target = name.rsplit(':', 1)[-1] if namespace == ':' else namespace + ':' + name
            c.rename(path, ':' + target)

    def _run_native_fbx_callback(self, text):
        """Translate the native callback; retain the source's custom hook.

        This is the explicit extension point at MEL 23364–23380, rather than
        delegating rig construction or export preparation to original MEL.
        Existing pipelines may store arbitrary commands in these attributes.
        """
        if not text:
            return
        try:
            namespace = _namespace_callback(text)
        except ValueError:
            from maya import mel
            mel.eval(text)
        else:
            self._fbx_namespace_selected(namespace)

    @contextmanager
    def _native_fbx_display_connections(self):
        """Native temporary joint visibility and display-layer disconnection."""
        from .maya_original_control_identity import source_main
        c = self._mannequin_cmds()
        if self.namespace:
            yield
            return
        restore = []
        main = (source_main(self) if any(self._cmds.objExists(node)
                for node in ('Main', 'AdvPy_Global')) else None)
        joint = self._unique('Root_M', 'joint') if self._cmds.objExists('Root_M') else None
        visibility = main + '.jointVis' if main else ''
        if joint and visibility and c.objExists(visibility) and c.isConnected(visibility, joint + '.visibility'):
            edge = (_plug_identity(c, visibility), _plug_identity(c, joint + '.visibility'))
            c.disconnectAttr(visibility, joint + '.visibility')
            restore.append(edge)
            c.setAttr(joint + '.visibility', 1)
        try:
            for layer in c.ls(type='displayLayer') or []:
                if layer == 'defaultLayer':
                    continue
                pairs = c.listConnections(layer + '.drawInfo', source=False,
                    destination=True, plugs=True, connections=True) or []
                for source, target in zip(pairs[::2], pairs[1::2]):
                    if target:
                        edge = (_plug_identity(c, source), _plug_identity(c, target))
                        c.disconnectAttr(source, target)
                        restore.append(edge)
            yield
        finally:
            self._restore_original_fbx_world_roots()
            for source_identity, target_identity in restore:
                source = _resolve_plug_identity(c, source_identity)
                target = _resolve_plug_identity(c, target_identity)
                if not c.isConnected(source, target):
                    c.connectAttr(source, target)

    def export_mannequin_fbx(self, destination, options):
        self._require_transaction()
        c = self._mannequin_cmds()
        self._transaction_changed = True
        roots = self._native_fbx_export_roots()
        with self.original_fbx_world_roots(roots):
            with self._native_fbx_display_connections():
                # Unparenting can change a root's long DAG address. Query the
                # source override order again before selecting the export.
                c.select(self._native_fbx_export_roots(), replace=True)
                c.refresh()
                pre = post = ''
                for attr in ('exportFbxPre', 'exportFbxPost'):
                    plug = 'fbxExportOptions.' + attr
                    if c.objExists(plug):
                        value = _export_callback_text(c.getAttr(plug))
                        if attr == 'exportFbxPre':
                            pre = value
                        else:
                            post = value
                try:
                    self._run_native_fbx_callback(pre)
                    destination = self._native_fbx_selection_export(destination)
                finally:
                    self._run_native_fbx_callback(post)
        return destination

    def finish_mannequin_export(self, options):
        self._require_transaction()
        c = self._mannequin_cmds()
        self._transaction_changed = True
        for node in MANNEQUIN_EXPORT_CLEANUP:
            if node == '|root' and options.keep_joints:
                continue
            if c.objExists(node):
                c.delete(node)
        if getattr(self, '_export_added_options', False) and c.objExists('fbxExportOptions'):
            c.delete('fbxExportOptions')
        if getattr(self, '_export_added_namespace', False):
            c.namespace(removeNamespace=options.namespace)
        # Full export leaves the native rootUserCreated rename in place. The
        # separate Delete Mannequin command restores it; do not conflate them.
        pose = self.read_body_build_pose()
        self.preflight_body_build_pose(pose)
        self.apply_body_build_pose(pose)
