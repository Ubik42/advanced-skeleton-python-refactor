"""Offline source graph/order checks; no Maya application is launched."""
from contextlib import nullcontext
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import unittest

from adv_py.core.custom_controller import (
    CustomControlKind, DeformJointCandidate, SoftModRegion, WeightedVertex,
    plan_custom_controller,
)
from adv_py.adapters.maya_original_custom_pose import _set_surface_uv
from adv_py.adapters.maya_original_custom_mirror import mirror_cluster_weights
from adv_py.adapters.maya_original_custom_deformers import create_softmod


class MirrorCommands:
    def __init__(self):
        self.selection = ['controller_R']
        self.vertices = ['mesh.vtx[8]', 'mesh.vtx[2]', 'mesh.vtx[4]']
        self.positions = {'mesh.vtx[8]': (-2., 0., 0.),
                          'mesh.vtx[2]': (-1., 0., 0.),
                          'mesh.vtx[4]': (0., 0., 0.)}
        self.weights = {'mesh.vtx[8]': .8, 'mesh.vtx[2]': 0., 'mesh.vtx[4]': .9}
        self.writes = []; self.connections = []; self.deleted = []

    def ls(self, **flags):
        return list(self.vertices if flags.get('flatten') else self.selection)

    def select(self, *nodes, **flags): self.selection = list(nodes[0]) if nodes and isinstance(nodes[0], list) else list(nodes)
    def listConnections(self, plug, **flags):
        return ['clusterSet.usedBy[0]'] if flags.get('plugs') else ['clusterSet']
    def percent(self, deformer, component, **flags):
        if flags.get('query'): return [self.weights[component]]
        self.writes.append((deformer, component, flags['value']))
    def objExists(self, node): return node == 'closestSampler'
    def createNode(self, kind, **flags): return flags['name']
    def connectAttr(self, source, destination): self.connections.append((source, destination))
    def about(self, **flags): return True
    def xform(self, vertex, **flags): return self.positions[vertex]
    def setAttr(self, *args): pass
    def getAttr(self, plug): return 9
    def delete(self, node): self.deleted.append(node)


class SoftModCommands:
    def __init__(self):
        self.parents = {}; self.connections = []; self.attributes = {}
        self.presets = []; self.sphere_options = {}; self.deleted = []
        self.nodes = {'source', 'sourceHandle', 'CustomSystem', 'parent_R'}

    def objExists(self, node): return node in self.nodes or node.endswith('.primaryVisibility')
    def shadingNode(self, kind, **flags): self.nodes.add(flags['name']); return flags['name']
    def sets(self, *args, **flags):
        if 'name' in flags: self.nodes.add(flags['name']); return flags['name']
    def sphere(self, **flags):
        self.sphere_options = flags; self.nodes.add(flags['name']); return [flags['name']]
    def addAttr(self, node, **flags): self.attributes[node + '.' + flags['longName']] = flags.get('defaultValue')
    def setAttr(self, plug, *values, **flags):
        if values: self.attributes[plug] = values[0] if len(values) == 1 else values
    def listRelatives(self, node, **flags): return [node + 'Shape']
    def createNode(self, kind, **flags): self.nodes.add(flags['name']); return flags['name']
    def parent(self, node, parent): self.parents[node] = parent; return [node]
    def softMod(self, mesh): return ['newSoftMod', 'newHandle']
    def rename(self, node, name): self.nodes.discard(node); self.nodes.add(name); return name
    def listConnections(self, plug): return ['newSet']
    def xform(self, *args, **flags): pass
    def nodePreset(self, **flags): self.presets.append(flags)
    def curve(self, **flags): self.nodes.add(flags['name']); return flags['name']
    def scale(self, *args, **flags): pass
    def spaceLocator(self, **flags): self.nodes.add(flags['name']); return [flags['name']]
    def connectAttr(self, source, target, **flags): self.connections.append((source, target))
    def disconnectAttr(self, *args): pass
    def orientConstraint(self, *args): return ['orientation']
    def delete(self, node):
        for item in (node if isinstance(node, (tuple, list)) else (node,)):
            self.nodes.discard(item); self.deleted.append(item)


class OriginalCustomTests(unittest.TestCase):
    def plan(self, kind=CustomControlKind.SOFT_MOD):
        return plan_custom_controller(kind,
            SoftModRegion('source', 'mesh', (-1., 2., 3.), 2,
                          (WeightedVertex(0, 1.), WeightedVertex(1, .2)),
                          'sourceHandle', 4.),
            (DeformJointCandidate('parent_R', (0., 0., 0.)),), 'Detail')

    def test_source_softmod_has_attach_base_control_without_extra_offset(self):
        plan = self.plan()
        self.assertEqual(plan.offset_name, 'DetailAttach_R')
        self.assertEqual(plan.created_names.count('DetailAttach_R'), 1)
        self.assertNotIn('OffsetDetail_R', plan.created_names)

    def test_default_parent_uses_rounded_distance_then_source_name(self):
        region = SoftModRegion('source', 'mesh', (0., 0., 0.), 1, (WeightedVertex(0, 1.),))
        joints = (DeformJointCandidate('|root|Z_R', (1.00001, 0., 0.)),
                  DeformJointCandidate('|root|A_R', (1.0004, 0., 0.)))
        plan = plan_custom_controller(CustomControlKind.SKIN, region, joints, 'Detail')
        self.assertEqual(plan.parent_joint, '|root|A_R')

    def test_native_uv_aliases_accept_namespace_sanitization_without_guessing(self):
        writes = []
        commands = SimpleNamespace(objExists=lambda plug:False,
            listAttr=lambda *args, **flags:['char_TempUVAttachMeshU0', 'char_TempUVAttachMeshV0'],
            setAttr=lambda *args:writes.append(args))
        _set_surface_uv(commands, 'constraint', .2, .8)
        self.assertEqual(writes, [('constraint.char_TempUVAttachMeshU0', .2),
                                  ('constraint.char_TempUVAttachMeshV0', .8)])

    def test_ambiguous_native_uv_targets_do_not_edit_either_surface(self):
        commands = SimpleNamespace(objExists=lambda plug:False,
            listAttr=lambda *args, **flags:['aU0','aV0','bU0','bV0'])
        with self.assertRaises(ValueError): _set_surface_uv(commands, 'constraint', .2, .8)

    def test_cluster_mirror_keeps_zero_and_last_native_set_write(self):
        commands = MirrorCommands()
        host = SimpleNamespace(_require_transaction=lambda:None,
            _unique=lambda name, kind:name, _mesh=lambda name:name,
            _cluster_meshes=lambda node:('mesh',), scene_address=lambda name:name)
        maya = ModuleType('maya'); maya.cmds = commands; maya.mel = SimpleNamespace()
        with patch.dict('sys.modules', {'maya':maya}):
            mirror_cluster_weights(host, 'ClusterDetail_R', 'ClusterDetail_L', 'mesh', 'R')
        self.assertEqual(commands.writes, [('ClusterDetail_L', 'mesh', 0),
            ('ClusterDetail_L', 'mesh.vtx[9]', .8), ('ClusterDetail_L', 'mesh.vtx[9]', 0.)])
        self.assertEqual(commands.connections, [('mesh.outMesh', 'closestSampler.inMesh')])
        self.assertEqual(commands.selection, ['controller_R'])

    def test_softmod_native_graph_preserves_source_frame_and_preset(self):
        commands = SoftModCommands(); registered = []; follows = []
        host = SimpleNamespace(_require_transaction=lambda:None,
            scene_address=lambda name:name, _unique=lambda name, kind:name,
            _unique_custom_parent=lambda name:name, _mesh=lambda name:name,
            _custom_system=lambda:'CustomSystem',
            _cmds=SimpleNamespace(_creation_namespace=nullcontext),
            _register_custom_nodes=lambda *args:registered.append(args))
        maya = ModuleType('maya'); maya.cmds = commands
        with patch.dict('sys.modules', {'maya':maya}), \
             patch('adv_py.adapters.maya_original_custom_deformers.original_face_deformer_sets', return_value=nullcontext()), \
             patch('adv_py.adapters.maya_original_custom_deformers._parent_constraint', side_effect=lambda *args:follows.append(args[2:])):
            create_softmod(host, self.plan())
        self.assertEqual(commands.parents['DetailAttach_R'], 'CustomSystem')
        self.assertEqual(commands.parents['DetailBase_R'], 'DetailAttach_R')
        self.assertEqual(commands.parents['Detail_R'], 'DetailBase_R')
        self.assertEqual(follows, [('parent_R', 'DetailAttach_R', True)])
        self.assertEqual(commands.presets, [dict(save=('source','asSoftMod')), dict(load=('DetailSoftMod_R','asSoftMod'))])
        self.assertIn(('DetailAttach_R.worldMatrix[0]', 'DetailSoftMod_R.matrix'), commands.connections)
        self.assertIn(('DetailBase_R.worldInverseMatrix[0]', 'DetailSoftMod_R.postMatrix'), commands.connections)
        self.assertEqual(commands.sphere_options['sections'], 8)
        self.assertEqual(commands.sphere_options['spans'], 4)
        self.assertFalse(commands.sphere_options['constructionHistory'])
        self.assertEqual(registered[0][0], ('DetailAttach_R','DetailBase_R','Detail_R'))


if __name__ == '__main__': unittest.main()
