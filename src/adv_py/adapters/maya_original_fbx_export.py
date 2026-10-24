"""ADV 6.925 asExportFbxBrowser (23262–23386) in Python.

Export the native deformation hierarchy, temporarily detach the original
scene roots, then restore their parents. No alternate export skeleton is built.
"""
from .maya_custom_controller import MayaCustomControllerHost
from .maya_unreal_mannequin_export import MayaMannequinExportMixin, _export_callback_text


class MayaOriginalFbxExportHost(MayaMannequinExportMixin, MayaCustomControllerHost):
    def _mannequin_cmds(self):
        return getattr(self._cmds, 'raw', self._cmds)

    def preflight_original_fbx_export(self, destination):
        c = self._mannequin_cmds()
        if destination is not None and (not destination.is_absolute()
                or destination.suffix.lower() != '.fbx' or not destination.parent.is_dir()):
            raise ValueError('请选择现有目录中的绝对 FBX 文件路径')
        from .maya_original_control_sets import resolve
        sets=resolve(self,getattr(self,'_original_export_ui_name',''))
        if not sets:
            raise ValueError('No controlSets detected. select a controller')
        for node in sets:
            self._unique(node,'objectSet')
        if not c.pluginInfo('fbxmaya', query=True, loaded=True):
            raise RuntimeError('请先加载 Maya 的 fbxmaya 插件')
        for attr in ('exportFbxPre', 'exportFbxPost'):
            plug = 'fbxExportOptions.' + attr
            if c.objExists(plug):
                _export_callback_text(c.getAttr(plug))
        self.original_fbx_scene_roots()

    def confirm_original_fbx_export(self):
        return self.confirm_native_fbx_export()

    def original_fbx_scene_roots(self):
        c = self._mannequin_cmds()
        joint = self.scene_address('Root_M')
        # Native override order is intentional: a Root Motion joint wins over
        # Mannequin root, and Custom Orient's world GameSkeletonRoot wins last.
        world_root = self.scene_address('|root')
        if c.objExists(world_root):
            joint = world_root
        if self._cmds.objExists('RootMotion_M'):
            joint = self._unique('RootMotion_M', 'joint')
        game_root = self.scene_address('|GameSkeletonRoot_M')
        if c.objExists(game_root):
            joint = game_root
        matches = c.ls(joint, long=True, type='joint') or []
        if len(matches) != 1:
            raise ValueError('FBX 原版导出根不存在或不唯一：' + joint)
        joint = matches[0]
        geometry = self.scene_address('|Geometry' if self.namespace else 'Geometry')
        roots = [joint]
        if c.objExists(geometry):
            matches = c.ls(geometry, long=True) or []
            if len(matches) != 1:
                raise ValueError('FBX Geometry 入口不唯一')
            roots.append(matches[0])
        return tuple(roots)

    def _native_fbx_export_roots(self):
        return self.original_fbx_scene_roots()
