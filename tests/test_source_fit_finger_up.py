"""Native Finger-up order, rounding, destructive display switch and graph."""
import unittest

from adv_py.adapters.maya_source_fit_finger_up import MayaSourceFitFingerUpMixin
from adv_py.core.source_fit_finger_up import (
    SOURCE_FINGERS, SourceFitFinger, source_fit_fingers, source_fit_finger_off_axis,
)


class FingerCommands:
    def __init__(self):
        self.calls = []
        self.nodes = {'FitSkeleton','FitSkeletonVisualizers'}
        self.nodes.update(finger+'Finger'+str(index) for finger in SOURCE_FINGERS
                          for index in (0,1))
        self.values = {}
        self.selection = ('ThumbFinger1',)

    def ls(self, **kwargs): return self.selection
    def objExists(self, node): return node in self.nodes
    def getAttr(self, plug): return self.values.get(plug,0.)

    def listRelatives(self, node, **kwargs):
        if kwargs.get('parent'):
            return [node[:-1]+'0' if node.endswith('1') else 'Wrist']
        return [node+'Shape']

    def xform(self, node, **kwargs):
        return (0.,0.,0.) if node.endswith('0') else (4.,0.,0.)

    def createNode(self, kind, **kwargs):
        self.calls.append(('create',kwargs['name'],kind))
        self.nodes.add(kwargs['name'])
        return kwargs['name']

    def parent(self, node, parent):
        self.calls.append(('parent',node,parent))
        return [node]

    def spaceLocator(self, *, name): return [name]
    def polyCreateFacet(self, **kwargs): return [kwargs['name']]
    def pointConstraint(self, *args): return [args[-1]+'_pointConstraint1']

    def delete(self, node):
        self.calls.append(('delete',node))
        if isinstance(node,str): self.nodes.discard(node)

    def setAttr(self, *args, **kwargs): self.calls.append(('set',args,kwargs))
    def connectAttr(self, *args, **kwargs): self.calls.append(('connect',args,kwargs))
    def sets(self, *args, **kwargs): pass
    def shadingNode(self, *args, **kwargs): pass
    def select(self, *args, **kwargs): self.calls.append(('select',args,kwargs))


def host(commands):
    item = MayaSourceFitFingerUpMixin()
    item._cmds = commands
    item._require_transaction = lambda: None
    item.manual_update_fit = lambda _: commands.calls.append(('manual',))
    return item


class SourceFitFingerUpTests(unittest.TestCase):
    def test_native_finger_order_fixed_indices_and_no_gap_bridging(self):
        rows = source_fit_fingers(('ThumbFinger0','ThumbFinger2','IndexFinger4','ThumbFinger5'))
        self.assertEqual(tuple(row.name for row in rows),SOURCE_FINGERS)
        self.assertEqual(rows[0].indices,(0,2))
        self.assertEqual(rows[-1].indices,(4,))
        self.assertEqual(rows[1].first,-1)

    def test_half_away_from_zero_rounding_controls_off_axis_prompt(self):
        self.assertEqual(source_fit_finger_off_axis((
            ('a','rotateX',.00049), ('a','rotateY',.0005), ('b','jointOrientZ',-.0005))),
            (('a','rotateY',.001), ('b','jointOrientZ',-.001)))

    def test_disable_clears_entire_visualizer_without_manual_or_selection_restore(self):
        c = FingerCommands()
        self.assertFalse(host(c).display_fit_finger_up(False))
        self.assertEqual(c.calls,[('delete','FitSkeletonVisualizers')])

    def test_cancel_occurs_after_manual_update_and_leaves_old_display_removed(self):
        c = FingerCommands()
        c.values['ThumbFinger1.rotateY'] = 3.
        prompts = []
        self.assertFalse(host(c).display_fit_finger_up(True,
            confirm=lambda prompt: prompts.append(prompt) or False))
        self.assertEqual(c.calls,[('delete','FitSkeletonVisualizers'),('manual',)])
        self.assertIn('ThumbFinger1.rotateY = 3',prompts[0])
        self.assertNotIn('FitSkeletonVisualizers',c.nodes)

    def test_graph_uses_surface_shader_and_three_world_position_inputs(self):
        c = FingerCommands()
        self.assertTrue(host(c).display_fit_finger_up(True))
        connections = [row[1] for row in c.calls if row[0]=='connect']
        self.assertIn(('Thumb1JointLocator.worldPosition[0]',
                       'VisualizeFingerUp_ThumbFinger1Shape.pnts[0]'), connections)
        self.assertIn(('Thumb0JointLocator.worldPosition[0]',
                       'VisualizeFingerUp_ThumbFinger1Shape.pnts[1]'), connections)
        self.assertIn(('ThumbUpLocator.worldPosition[0]',
                       'VisualizeFingerUp_ThumbFinger1Shape.pnts[2]'), connections)
        self.assertIn(('set',('ThumbUpLocator.localScale',1.,1.,1.),{'type':'float3'}),c.calls)
        self.assertIn(('set',('ThumbUpLocator.tz',2.),{}),c.calls)
        self.assertEqual(c.calls[-1],('select',(('ThumbFinger1',),),{'replace':True}))

    def test_gap_remains_reference_to_missing_previous_index_like_source(self):
        c = FingerCommands()
        host(c)._create_source_fit_finger_up(SourceFitFinger('Thumb',(0,2)))
        self.assertIn(('connect',('Thumb1JointLocator.worldPosition[0]',
            'VisualizeFingerUp_ThumbFinger2Shape.pnts[1]'),{'force':True}),c.calls)


if __name__ == '__main__': unittest.main()
