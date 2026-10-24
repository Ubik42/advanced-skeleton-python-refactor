"""Native templates, exact side arithmetic and live ordered Fit placement."""
from pathlib import Path
import unittest

from adv_py.core.name_matcher_fit import NameMatcherRow,NameMatcherRules
from adv_py.core.source_name_matcher import (
    read_source_name_matcher_template,export_source_name_matcher_template,
    source_name_matcher_name,
)
from adv_py.core.source_import_matcher import source_import_matcher_joint
from adv_py.adapters.maya_source_name_matcher import MayaSourceNameMatcherMixin,source_name_matcher_catalog


class FitCommands:
    def __init__(self):
        self.fits = {'Root':'|FitSkeleton|Root','Head':'|FitSkeleton|Root|Head'}
        self.positions = {self.fits['Root']:(0.,1.,0.),self.fits['Head']:(0.,2.,0.),
                          '|source':(0.,0.,0.),'root':(0.,20.,0.),'head':(0.,10.,0.)}
        self.writes = []
        self.scale = None

    def ls(self, node=None, **kwargs):
        if kwargs.get('uuid'):return ['source-id']
        if node=='source-id':return ['|source']
        if node=='hip':return []
        if kwargs.get('type')=='joint' and node is None:return []
        if node in self.fits:return [self.fits[node]]
        return []

    def objExists(self, node):return node in ('root','head')
    def listRelatives(self, node, **kwargs):
        if node=='FitSkeleton':return list(self.fits.values())
        if node=='|source':return ['head','root']
        return []
    def setAttr(self, plug, *values, **kwargs):self.scale = values
    def warning(self, *args):pass
    def upAxis(self, **kwargs):return 'y'
    def select(self, *args, **kwargs):pass

    def xform(self, node, **kwargs):
        if kwargs.get('query'):return self.positions[node]
        value = tuple(kwargs['translation'])
        old = self.positions[node]
        self.positions[node] = value
        for path,point in tuple(self.positions.items()):
            if path.startswith(node+'|'):
                self.positions[path] = tuple(v+new-prior for v,new,prior in zip(point,value,old))
        self.writes.append(node)


class SourceNameMatcherTests(unittest.TestCase):
    def test_all_original_mapping_assets_parse_without_inventing_finger_aliases(self):
        templates = {path.stem:read_source_name_matcher_template(path.read_text(encoding='utf-8-sig'))
                     for path in source_name_matcher_catalog()}
        self.assertIn(NameMatcherRow('IndexFinger0','index_metacarpal'),templates['Unreal5'].rows)
        self.assertIn(NameMatcherRow('Spine5','spine_05'),templates['Unreal5'].rows)
        self.assertIn(NameMatcherRow('ThumbFinger4','HandThumb4'),templates['Mixamo'].rows)
        self.assertEqual(templates['Mixamo'].rules,NameMatcherRules('Right','Left','',True,False))

    def test_export_roundtrip_preserves_order_duplicate_rows_and_blank_middle(self):
        rows = (NameMatcherRow('Root','Hips'),NameMatcherRow('Root','pelvis'))
        rules = NameMatcherRules('r','l','',False,True)
        exported = export_source_name_matcher_template(rows,rules)
        decoded = read_source_name_matcher_template(exported)
        self.assertEqual((decoded.rows,decoded.rules),(rows,rules))
        self.assertIn('sideMiddle=\n',exported)

    def test_blank_right_marker_retains_underscore_but_blank_middle_omits_it(self):
        rules = NameMatcherRules('','','',False,True)
        self.assertEqual(source_name_matcher_name('Hand',rules),'Hand_')
        self.assertEqual(source_name_matcher_name('Root',rules,middle=True),'Root')
        self.assertEqual(source_name_matcher_name('Hand',NameMatcherRules('Right','Left','',True,False),
                                                namespace='mixamorig'),'mixamorig:RightHand')

    def test_import_scan_keeps_native_first_hip_and_excludes_dhi_deform_joint(self):
        joints = ('DHIbody:pelvis','hero:Hip','other:pelvis')
        self.assertEqual(source_import_matcher_joint('bipedGame',joints),'hero:Hip')
        self.assertIsNone(source_import_matcher_joint('Biped',joints))
        self.assertIsNone(source_import_matcher_joint('biped',joints,importing=True))
        self.assertIsNone(source_import_matcher_joint('cat',joints))

    def test_native_placement_keeps_row_order_and_child_moves_with_later_parent(self):
        c = FitCommands()
        host = MayaSourceNameMatcherMixin()
        host._cmds = c
        host._require_transaction = lambda:None
        host.check_source_name_matcher = lambda root:root
        imports = []
        host.import_source_fit_scene = lambda source,**kwargs:imports.append((Path(source),kwargs))
        host.manual_update_fit = lambda:None
        result = host.create_source_name_matched_fit('|source',
            (NameMatcherRow('Head','head'),NameMatcherRow('Root','root')),
            NameMatcherRules('','',''),template_name='Unreal5')
        self.assertEqual(imports[0][0].name,'Unreal5.ma')
        self.assertEqual(c.writes,[c.fits['Head'],c.fits['Root']])
        self.assertEqual(c.positions[c.fits['Head']],(0.,29.,0.))
        self.assertEqual(result.placed,2)
        self.assertEqual(result.scale,20./17.)


if __name__=='__main__':unittest.main()
