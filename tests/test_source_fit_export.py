"""Export failure must restore SDK identities and extracted limb parents."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from adv_py.adapters.maya_source_fit_export import (
    MayaSourceFitExportMixin,source_fit_export_is_limb,
)


class ExportCommands:
    def __init__(self, *, fail=False):
        self.parents = {'Group':None,'FitSkeleton':'Group','Root':'FitSkeleton',
                        'Shoulder':'Root','Wrist':'Shoulder','OtherRoot':'FitSkeleton','SDK':None}
        self.identities = {name:'id-'+name for name in self.parents}
        self.selection = ['Wrist']
        self.locked = True
        self.visible = False
        self.fail = fail
        self.undo_name = ''
        self.chunks = []
        self.deleted_snapshot = None
        self.exported = None
        self.export_options = None
        self.undos = 0

    def leaf(self, value):
        if value in self.identities.values():
            return next(name for name,item in self.identities.items() if item==value)
        return value.rsplit('|',1)[-1].lstrip(':')

    def path(self, name):
        parent = self.parents[name]
        return (self.path(parent) if parent else '')+'|'+name

    def ls(self, value=None, **kwargs):
        names = self.selection if kwargs.get('selection') else [self.leaf(value)]
        names = [name for name in names if name in self.parents]
        return [self.identities[name] if kwargs.get('uuid') else self.path(name)
                if kwargs.get('long') else name for name in names]

    def objExists(self, name):return self.leaf(name) in self.parents
    def getAttr(self, plug, **kwargs):return self.locked if kwargs.get('lock') else self.visible

    def setAttr(self, plug, value=None, **kwargs):
        if 'lock' in kwargs:self.locked = kwargs['lock']
        elif value is not None:self.visible = value

    def listRelatives(self, value, **kwargs):
        name = self.leaf(value)
        if kwargs.get('parent'):
            parent = self.parents[name]
            return [self.path(parent)] if parent else []
        return [self.path(child) for child,parent in self.parents.items() if parent==name]

    def parent(self, names, parent=None, **kwargs):
        if isinstance(names,str):names = [names]
        names = [self.leaf(name) for name in names]
        for name in names:self.parents[name] = None if kwargs.get('world') else self.leaf(parent)
        return [self.path(name) for name in names]

    def listConnections(self, node=None, **kwargs):
        return ['SDK'] if node else ['SDKCurve']

    def select(self, node, **kwargs):self.selection = [self.leaf(node)]

    def createNode(self, kind, *, name):
        name = self.leaf(name)
        self.parents[name] = None
        self.identities[name] = 'id-'+name
        return name

    def undoInfo(self, **kwargs):
        if kwargs.get('query'):
            return self.undo_name if kwargs.get('undoName') else True
        if kwargs.get('openChunk'):self.chunks.append(kwargs['chunkName'])
        if kwargs.get('closeChunk'):self.undo_name = self.chunks.pop()

    def delete(self, names):
        if isinstance(names,str):names = [names]
        names = [self.leaf(name) for name in names]
        if 'SDK' in names:self.deleted_snapshot = deepcopy((self.parents,self.identities))
        for name in names:
            self.parents.pop(name)
            self.identities.pop(name)

    def undo(self):
        self.parents,self.identities = self.deleted_snapshot
        self.undos += 1

    def file(self, destination, **kwargs):
        self.exported = deepcopy(self.parents)
        self.export_options = kwargs
        if self.fail:raise RuntimeError('disk unavailable')
        Path(destination).write_text('// simulated export',encoding='utf-8')


class SourceFitExportTests(unittest.TestCase):
    def host(self, commands):
        host = MayaSourceFitExportMixin()
        host._cmds = commands
        host.namespace = None
        host._transaction_active = False
        return host

    def test_native_limb_detection_requires_fit_at_world_root(self):
        self.assertTrue(source_fit_export_is_limb('|FitSkeleton|Root|Wrist'))
        self.assertFalse(source_fit_export_is_limb('|Group|FitSkeleton|Root|Wrist'))
        self.assertFalse(source_fit_export_is_limb('|FitSkeleton|Root'))
        self.assertTrue(source_fit_export_is_limb('|hero:FitSkeleton|hero:Root|hero:Wrist','hero'))

    def test_complete_export_restores_sdk_and_parent_and_keeps_source_visibility(self):
        commands = ExportCommands()
        # Source detects limbs before detaching Fit; an already grouped Fit
        # exports the whole skeleton even when a descendant is selected.
        before = deepcopy(commands.parents)
        with TemporaryDirectory() as directory:
            self.host(commands).export_source_fit_scene(Path(directory)/'fit.ma')
        self.assertEqual(commands.parents,before)
        self.assertNotIn('SDK',commands.exported)
        self.assertIsNone(commands.exported['FitSkeleton'])
        self.assertTrue(commands.locked)
        self.assertTrue(commands.visible)
        self.assertEqual(commands.undos,1)
        self.assertTrue(commands.export_options['channels'])
        self.assertTrue(commands.export_options['constructionHistory'])

    def test_failed_limb_export_restores_every_original_uuid_parent_and_sdk(self):
        commands = ExportCommands(fail=True)
        commands.parents['FitSkeleton'] = None
        before,identities = deepcopy(commands.parents),deepcopy(commands.identities)
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError,'disk unavailable'):
                self.host(commands).export_source_fit_scene(Path(directory)/'hand.ma')
        self.assertEqual(commands.parents,before)
        self.assertEqual(commands.identities,identities)
        self.assertEqual(commands.exported['Wrist'],'FitSkeleton')
        self.assertEqual(commands.exported['Root'],'previousFitSkeletonChildren')
        self.assertEqual(commands.undos,1)
        self.assertFalse(commands.chunks)

    def test_nested_export_cannot_undo_callers_transaction(self):
        commands = ExportCommands()
        host = self.host(commands)
        host._transaction_active = True
        with self.assertRaisesRegex(RuntimeError,'不能放入另一个事务'):
            host.export_source_fit_scene(Path('anything.ma'))
        self.assertEqual(commands.undos,0)
        self.assertFalse(commands.chunks)


if __name__ == '__main__':unittest.main()
