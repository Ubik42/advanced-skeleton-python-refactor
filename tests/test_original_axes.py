import unittest
from itertools import permutations,product

from adv_py.core.adv_icon_axis import tertiary_axis,icon_axis_offset
from adv_py.adapters.maya_original_axes import original_axes
from adv_py.adapters.maya_adv_icons import original_fit_icon_axis_offset
from adv_py.adapters.maya_original_transform_channels import reset_original_custom_attributes


class Commands:
    def __init__(self,values):self.values=values;self.writes=[]
    def objExists(self,node):return node in self.values
    def getAttr(self,node,**flags):
        if flags.get('settable') or flags.get('keyable'):return True
        if flags.get('type'):return 'double'
        return self.values[node]
    def ls(self,node,**flags):
        return [node] if node in self.values else []
    def listAttr(self,node,**flags):return ['follow']
    def attributeQuery(self,attribute,**flags):return [0.]
    def setAttr(self,plug,value,**flags):self.writes.append((plug,value))


class OriginalAxesTests(unittest.TestCase):
    def test_all_signed_tertiary_axes_match_ordered_cross_product(self):
        basis={'X':(1,0,0),'Y':(0,1,0),'Z':(0,0,1)}
        for first,second in permutations('XYZ',2):
            for a,b in product((1,-1),repeat=2):
                x=tuple(a*v for v in basis[first]);y=tuple(b*v for v in basis[second])
                cross=(x[1]*y[2]-x[2]*y[1],x[2]*y[0]-x[0]*y[2],x[0]*y[1]-x[1]*y[0])
                index=next(i for i,v in enumerate(cross) if v)
                expected=('-' if cross[index]<0 else '')+'XYZ'[index]
                self.assertEqual(tertiary_axis(('-' if a<0 else '')+first,
                                             ('-' if b<0 else '')+second),expected)

    def test_reference_defaults_and_worldmatch_pair_override(self):
        c=Commands({'Main':True,'Main.primaryAxis':'Y','Main.secondaryAxis':'Z',
                    'FitSkeleton.worldmatch':False,'Wrist_R.primaryAxis':'-Z','Wrist_R.secondaryAxis':'X'})
        self.assertEqual(original_axes(c,'Wrist_R','Main'),('Y','Z'))
        c.values['FitSkeleton.worldmatch']=True
        self.assertEqual(original_axes(c,'Wrist_R','Main'),('-Z','X'))
        del c.values['Wrist_R.secondaryAxis']
        with self.assertRaises(KeyError):original_axes(c,'Wrist_R','Main')

    def test_icon_worldmatch_reads_body_axis_without_substituting_fit(self):
        c=Commands({'|Group|FitSkeleton':True,'|Group|FitSkeleton.worldmatch':True,
                    'AdvPy_Global':True,'AdvPy_Global.primaryAxis':'X','AdvPy_Global.secondaryAxis':'Y',
                    'Wrist.primaryAxis':'Z','Wrist.secondaryAxis':'Y'})
        self.assertEqual(original_fit_icon_axis_offset(c,('Wrist',),side='R'),(0,0,0))
        c.values.update({'Wrist_R.primaryAxis':'Z','Wrist_R.secondaryAxis':'Y'})
        self.assertEqual(original_fit_icon_axis_offset(c,('Wrist',),side='R'),icon_axis_offset('Z','Y'))

    def test_pole_leg_default_uses_source_role_not_python_name(self):
        c=Commands({})
        reset_original_custom_attributes(c,'AdvPy_Leg_R_Pole',source_name='PoleLeg_R')
        self.assertEqual(c.writes,[('AdvPy_Leg_R_Pole.follow',10.)])
        c.writes.clear()
        reset_original_custom_attributes(c,'AdvPy_Arm_R_Pole',source_name='PoleArm_R')
        self.assertEqual(c.writes,[('AdvPy_Arm_R_Pole.follow',0.)])
