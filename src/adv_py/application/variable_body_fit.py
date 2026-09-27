from dataclasses import replace

from adv_py.core.variable_body_fit import variable_body_fit_template,variable_axial_description
from adv_py.core.fit_orientation import FitOrientationChildSelection
from .body_hand_fit import body_with_hand_orientation_request
from .upper_body_fit import body_source_orientation_request
from .oriented_fit_template import BuildOrientedFitTemplate


def variable_body_source_inputs(up_axis, spine_segments, scale, with_hand):
    template = variable_body_fit_template(
        up_axis, spine_segments=spine_segments, scale=scale,
        with_hand=with_hand)
    description = variable_axial_description(spine_segments)
    base = (body_with_hand_orientation_request
            if with_hand else body_source_orientation_request)()
    chain = tuple(name.removesuffix('_M') for name in description.spine)
    selections = tuple(
        FitOrientationChildSelection('Root', chain[1])
        if selection.joint == 'Root' else selection
        for selection in base.child_selections)
    request = replace(base,
        joints=tuple(name for name in base.joints if name != 'Spine1')
            + chain[1:-1],
        child_selections=selections)
    return template, request


class BuildVariableBodySourceFit:
    def __init__(self,host):self._host=host

    def inputs(self,spine_segments,scale,with_hand):
        return variable_body_source_inputs(
            self._host.scene_up_axis(), spine_segments, scale, with_hand)

    def plan(self,container_name='FitSkeleton',*,spine_segments=2,scale=1.,with_hand=True):
        template,request=self.inputs(spine_segments,scale,with_hand)
        return BuildOrientedFitTemplate(self._host).plan(template,request,container_name)

    def apply(self,container_name='FitSkeleton',*,spine_segments=2,scale=1.,with_hand=True):
        template,request=self.inputs(spine_segments,scale,with_hand)
        return BuildOrientedFitTemplate(self._host).apply(template,request,container_name,
            transaction_label='构建可变脊柱全身 Fit',error_context='可变脊柱全身 Fit')
