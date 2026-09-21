import unittest
from adv_py.core.body_description import BodyAxialDescription
from adv_py.core.variable_body_fit import variable_axial_description,variable_body_fit_template
from adv_py.core.fit_template import predict_fit_template_hierarchy
from adv_py.core.fit_container import FitUpAxis
from adv_py.core.fit_settings import FitSkeletonValidationError


class VariableBodyTests(unittest.TestCase):
    def test_segment_counts_preserve_chest_and_limb_endpoints_at_both_up_axes(self):
        for axis in (FitUpAxis.Y,FitUpAxis.Z):
            for scale in (.25,3.):
                reference=None
                for count in (1,2,4,8):
                    template=variable_body_fit_template(axis,spine_segments=count,scale=scale)
                    rows=predict_fit_template_hierarchy(template,'|FitSkeleton').joints
                    positions={j.short_name:j.world_position for j in rows}
                    selected={k:positions[k] for k in ('Chest','Head','Wrist','Ankle')}
                    if reference is None:reference=selected
                    self.assertEqual(selected,reference)
                    self.assertEqual(sum(n.startswith('Spine') for n in positions),count-1)
                    self.assertEqual(len(variable_axial_description(count).spine),count+1)

    def test_invalid_or_ambiguous_descriptions_are_rejected(self):
        for count in (0,64,True,2.5):
            with self.assertRaises(FitSkeletonValidationError):variable_axial_description(count)
        for spine in (('Root_M',),('Root_M','Root_M'),('Root_M','Neck_M'),('Root_M','hero:Chest_M')):
            with self.assertRaises(FitSkeletonValidationError):BodyAxialDescription(spine=spine)
