"""Original Fit import naming/merge boundaries, without opening Maya assets."""
from pathlib import Path
import unittest

from adv_py.adapters.maya_source_fit_import import (
    MayaSourceFitImportMixin, source_fit_asset_catalog,
)
from adv_py.core.source_fit_import import SourceFitMergePolicy, source_fit_import_rename,SourceFitPreparation


class MergeCommands:
    def __init__(self, namespace=''):
        prefix = namespace+':' if namespace else ''
        self.fit = prefix+'FitSkeleton'
        self.merge = prefix+'Merge'
        self.imported = self.merge+':FitSkeleton'
        self.nodes = {self.fit, prefix+'Root', self.imported,
                      self.merge+':Root',self.merge+':SDK'}
        self.parents = {self.merge+':Root':self.imported}
        self.attributes = {(self.fit,'lockCenterJoints')}
        self.calls = []
        self.scans = 0

    def getAttr(self, plug): return True
    def objExists(self, node): return node in self.nodes
    def setAttr(self, *args, **kwargs): self.calls.append(('set',args,kwargs))

    def attributeQuery(self, name, *, node, **kwargs):
        return (node,name) in self.attributes

    def addAttr(self, node, **kwargs):
        self.attributes.add((node,kwargs['longName']))
        self.calls.append(('add',node,kwargs))

    def listRelatives(self, node, **kwargs):
        if kwargs.get('parent'):
            return [self.parents[node]] if node in self.parents else []
        return [child for child,parent in self.parents.items() if parent == node]

    def parent(self, nodes, parent):
        if isinstance(nodes,str): nodes = [nodes]
        for node in nodes:self.parents[node] = parent
        return list(nodes)

    def listAttr(self, node, **kwargs):
        return ['unrelated','drivingSystem[4]','drivingSystem_SDK_curl[7]']

    def listConnections(self, plug, **kwargs):
        if plug.endswith('drivingSystem[4]') and kwargs.get('source'):
            return [self.merge+':SDK.drivingSystemOut']
        if plug.endswith('drivingSystem_SDK_curl[7]') and kwargs.get('destination'):
            return [self.merge+':SDK.curl']
        return []

    def connectAttr(self, *args, **kwargs):self.calls.append(('connect',args,kwargs))
    def disconnectAttr(self, *args, **kwargs):self.calls.append(('disconnect',args,kwargs))

    def delete(self, node):
        self.calls.append(('delete',node))
        self.nodes.discard(node)
        self.parents.pop(node,None)

    def ls(self, pattern):
        self.scans += 1
        if self.scans > 10:raise RuntimeError('namespace rename made no progress')
        return sorted(node for node in self.nodes if node.startswith(pattern[:-1]))

    def rename(self, node, name):
        name = name.lstrip(':')
        self.nodes.remove(node)
        self.nodes.add(name)
        if node in self.parents:self.parents[name] = self.parents.pop(node)
        self.calls.append(('rename',node,name))
        return name

    def namespace(self, **kwargs):self.calls.append(('namespace',kwargs))


class SourceFitImportTests(unittest.TestCase):
    def test_preparation_preserves_exact_object_text_and_native_option_vars(self):
        class Commands:
            def __init__(self):self.values,self.options = {},{}
            def objExists(self, name):return name=='FitSkeleton'
            def setAttr(self, plug, value, **kwargs):self.values[plug] = value
            def optionVar(self, *, intValue):self.options[intValue[0]] = intValue[1]
        c = Commands()
        host = MayaSourceFitImportMixin()
        host._cmds = c
        host._require_transaction = lambda:None
        host.save_source_fit_preparation(SourceFitPreparation(
            skin='model:Body model:Hands',right_eye='  model:Eye_R  ',
            game_engine=True,use_offset_parent_matrix=True,sub_controllers=False,extra_controllers=True))
        self.assertEqual(c.values['FitSkeleton.objectsRightEye'],'  model:Eye_R  ')
        self.assertEqual(c.values['FitSkeleton.objectsSkin'],'model:Body model:Hands')
        self.assertEqual(c.options,{'asBodyPreGameEngine':1,'asBodyPreOPM':1,'asBodyPreSub':0,'asBodyPreExtra':1})
        self.assertEqual(len(c.values),8)

    def test_catalog_uses_original_assets_without_importing_maya(self):
        assets = source_fit_asset_catalog()
        self.assertIn('biped.ma',{asset.name for asset in assets})
        self.assertEqual({asset.name for asset in source_fit_asset_catalog(limbs=True)},
                         {'hand.ma','foot.ma','tail.ma'})

    def test_native_numeric_rename_uses_first_available_and_final_98_candidate(self):
        self.assertEqual(source_fit_import_rename('Root',{'Root','Root1','Root2'}.__contains__),'Root3')
        self.assertEqual(source_fit_import_rename('Root',lambda _:True),'Root98')

    def test_mixed_dag_parent_namespace_does_not_prevent_imported_leaf_rename(self):
        self.assertEqual(MayaSourceFitImportMixin._source_import_leaf(
            '|hero:FitSkeleton|hero:Merge:Root','hero:Merge'),'Root')
        with self.assertRaises(ValueError):
            MayaSourceFitImportMixin._source_import_leaf('other:Root','hero:Merge')

    def test_keep_both_preserves_existing_root_and_all_sdk_array_indices(self):
        c = MergeCommands()
        host = MayaSourceFitImportMixin()
        host.namespace = None
        host._merge_source_fit_scene(c,'Merge',SourceFitMergePolicy.BOTH)
        self.assertIn('Root',c.nodes)
        self.assertIn('Root1',c.nodes)
        self.assertNotIn('Merge:FitSkeleton',c.nodes)
        self.assertIn(('connect',('FitSkeleton.drivingSystem_SDK_curl[7]','Merge:SDK.curl'),
                       {'force':True}),c.calls)
        self.assertIn(('connect',('Merge:SDK.drivingSystemOut','FitSkeleton.drivingSystem'),
                       {'nextAvailable':True}),c.calls)
        self.assertEqual(c.calls[-2],('set',('FitSkeleton.lockCenterJoints',True),{}))
        self.assertEqual(c.calls[-1],('namespace',{'removeNamespace':':Merge'}))

    def test_nested_character_transfer_does_not_rename_other_character(self):
        c = MergeCommands('hero')
        c.nodes.add('other:Root')
        host = MayaSourceFitImportMixin()
        host.namespace = 'hero'
        host._merge_source_fit_scene(c,'hero:Merge',SourceFitMergePolicy.BOTH)
        self.assertIn('hero:Root1',c.nodes)
        self.assertIn('other:Root',c.nodes)
        self.assertFalse(any(node.startswith('hero:Merge:') for node in c.nodes))

    def test_keep_existing_drops_only_imported_same_named_joint(self):
        c = MergeCommands()
        host = MayaSourceFitImportMixin()
        host.namespace = None
        host._merge_source_fit_scene(c,'Merge',SourceFitMergePolicy.EXISTING)
        self.assertIn(('delete','Merge:Root'),c.calls)
        self.assertIn('Root',c.nodes)
        self.assertNotIn('Root1',c.nodes)


if __name__ == '__main__':unittest.main()
