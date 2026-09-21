from dataclasses import replace

from adv_py.core.variable_body_fit import variable_body_fit_template,variable_axial_description
from adv_py.core.fit_orientation import FitOrientationChildSelection
from .body_hand_fit import body_with_hand_orientation_request
from .upper_body_fit import body_source_orientation_request
from .oriented_fit_template import BuildOrientedFitTemplate


class BuildVariableBodySourceFit:
    def __init__(self,host):self._host=host

    def _inputs(self,spine_segments,scale,with_hand):
        template=variable_body_fit_template(self._host.scene_up_axis(),spine_segments=spine_segments,scale=scale,with_hand=with_hand)
        description=variable_axial_description(spine_segments)
        base=(body_with_hand_orientation_request if with_hand else body_source_orientation_request)()
        chain=tuple(n.removesuffix('_M') for n in description.spine)
        selections=tuple(FitOrientationChildSelection('Root',chain[1]) if s.joint=='Root' else s for s in base.child_selections)
        request=replace(base,joints=tuple(n for n in base.joints if n!='Spine1')+chain[1:-1],child_selections=selections)
        return template,request

    def plan(self,container_name='FitSkeleton',*,spine_segments=2,scale=1.,with_hand=True):
        template,request=self._inputs(spine_segments,scale,with_hand)
        return BuildOrientedFitTemplate(self._host).plan(template,request,container_name)

    def apply(self,container_name='FitSkeleton',*,spine_segments=2,scale=1.,with_hand=True):
        template,request=self._inputs(spine_segments,scale,with_hand)
        return BuildOrientedFitTemplate(self._host).apply(template,request,container_name,
            transaction_label='构建可变脊柱全身 Fit',error_context='可变脊柱全身 Fit')
