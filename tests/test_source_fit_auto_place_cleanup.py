"""Offline source-order checks for guide cleanup; no Maya process is started."""
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import unittest

from adv_py.adapters.maya_fit_auto_place_guides import update_joint_subtree
from adv_py.adapters.maya_fit_auto_place_mesh import cast, invert
from adv_py.adapters.maya_fit_auto_scale import _remove_softmods
from adv_py.core.fit_auto_scale import FitAutoScaleJoint


class SoftModCommands:
    def __init__(self):
        self.points={'parent':(1.,0.,0.),'child':(2.,0.,0.)}
        self.writes=[]
        self.deleted=[]
        self.wrap_queries=0

    def ls(self, **options):
        if options.get('type')=='softMod':return ['softMod1']
        if options.get('type')=='wrap':
            self.wrap_queries+=1
            return [] if self.wrap_queries==1 else ['wrap1']
        raise AssertionError(options)

    def xform(self, node, **options):
        if options.get('query'):
            if node=='warpCurve.cv[0]':return (20.,0.,0.)
            if node=='warpCurve.cv[1]':return (10.,0.,0.)
            return self.points[node]
        point=tuple(options['translation'])
        if node=='parent':
            delta=point[0]-self.points[node][0]
            child=self.points['child']
            self.points['child']=(child[0]+delta,*child[1:])
        self.points[node]=point
        self.writes.append(node)

    def setAttr(self, *args, **options):pass
    def blendShape(self, *args, **options):return ['unwarpBlend']
    def curve(self, **options):return 'warpCurve'
    def parent(self, node, *args, **options):return [node]
    def select(self, *args, **options):pass
    def delete(self, nodes):self.deleted.extend(nodes)


class SourceAutoPlaceCleanupTests(unittest.TestCase):
    def test_softmod_unwarp_sets_parent_before_child_to_preserve_world_targets(self):
        commands=SoftModCommands()
        host=SimpleNamespace(_cmds=commands,scene_address=lambda name:name)
        plan=SimpleNamespace(before=SimpleNamespace(joints=(
            FitAutoScaleJoint('child',(2.,0.,0.)),FitAutoScaleJoint('parent',(1.,0.,0.)))))
        maya=ModuleType('maya');maya.mel=SimpleNamespace(eval=lambda command:None)
        with patch.dict('sys.modules',{'maya':maya}), \
                patch('adv_py.adapters.maya_fit_auto_scale._combined_sample',side_effect=('deformed','undeformed')):
            _remove_softmods(host,plan,('Skin',),'temporaryGroup')
        self.assertEqual(commands.writes,['parent','child'])
        self.assertEqual(commands.points,{'parent':(10.,0.,0.),'child':(20.,0.,0.)})
        self.assertEqual(commands.deleted,['wrap1','softMod1'])

    def test_delete_guides_uses_the_original_recursive_wrist_update(self):
        calls=[]
        host=SimpleNamespace(update_source_fit_orientations=lambda roots,**options:calls.append((roots,options)))
        update_joint_subtree(host,'Wrist','FitSkeleton')
        self.assertEqual(calls,[(('Wrist',),dict(container='FitSkeleton',recursive=True))])

    def test_component_cast_replaces_only_the_first_selected_source_object(self):
        self.assertEqual(cast(('mesh.vtx[2]','other.vtx[3]','mesh.e[1:4]'),'copy'),
            ['copy.vtx[2]','other.vtx[3]','copy.e[1:4]'])

    def test_component_inversion_keeps_the_original_native_range_limit(self):
        for component,kind in (('mesh.vtx[2]','vtx'),('mesh.f[2]','f'),('mesh.e[2]','e')):
            calls=[]
            commands=SimpleNamespace(ls=lambda **options:['mesh'] if options.get('objectsOnly') else [component],
                select=lambda *args,**options:calls.append((args,options)))
            invert(commands)
            self.assertEqual(calls,[((f'mesh.{kind}[0:999999]',),dict(replace=True)),
                (([component],),dict(deselect=True))])

    def test_non_polygon_component_inversion_calls_maya_stock_fallback(self):
        calls=[]
        maya=ModuleType('maya');maya.mel=SimpleNamespace(eval=lambda command:calls.append(command))
        commands=SimpleNamespace(ls=lambda **options:['mesh'] if options.get('objectsOnly') else ['mesh.map[2]'])
        with patch.dict('sys.modules',{'maya':maya}):invert(commands)
        self.assertEqual(calls,['InvertSelection;'])


if __name__=='__main__':unittest.main()
