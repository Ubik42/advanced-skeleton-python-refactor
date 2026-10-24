"""Persistent AlignIKTo identities for source Spline endpoints."""
from dataclasses import dataclass,asdict
from .character_registry import CharacterRegistryError,exact,path,canonical,safe_json
from .source_fit_identity import source_fit_reference,source_fit_build_name,source_fit_is_end_joint

ALIGNMENT_ATTRIBUTE='advPySourceSplineAlignment'


@dataclass(frozen=True,slots=True)
class SourceSplineAlignmentFrame:
    body: str
    parent: str
    target: str


def plan_source_spline_alignment_frames(spline,fk,all_splines,hierarchy,instances,*,non_terminal_fit=()):
    """MEL 80033–80055: EndJoint attaches to its Fit parent's FKX."""
    source_by_driver={joint.path:joint.source_joint for plan in all_splines for joint in plan.joints}
    fit_by_path={node.path:node for node in hierarchy.joints}
    controls_by_body={}
    for control in fk.controls:
        source=source_by_driver.get(control.driven_joint,control.driven_joint)
        controls_by_body.setdefault(source,[]).append(control)
    all_body={joint.source_joint for plan in all_splines for joint in plan.joints}
    all_body.update(controls_by_body)
    by_name={}
    for value in all_body:
        name=value.rsplit('|',1)[-1]
        if name in by_name and by_name[name]!=value:
            raise CharacterRegistryError('来源 Spline AlignIKTo 的 Body 名称不唯一：'+name)
        by_name[name]=value
    result=[]
    for ordinal,body in ((0,spline.body_joints[0]),(len(spline.body_joints)-1,spline.body_joints[-1])):
        fit_path=source_fit_reference(body.rsplit('|',1)[-1],instances)
        if fit_path not in fit_by_path:
            raise CharacterRegistryError('来源 Spline AlignIKTo 没有明确 Fit 身份：'+body)
        source=fit_by_path[fit_path]
        terminal=source_fit_is_end_joint(hierarchy,fit_path,non_terminal_fit)
        parent_body=body
        if terminal:
            parent_fit=fit_by_path.get(source.dag_parent)
            if parent_fit is None:
                raise CharacterRegistryError('来源 Spline 末端没有 Fit 父关节：'+body)
            side=body.rsplit('_',1)[-1]
            parent_body=by_name.get(source_fit_build_name(parent_fit.short_name)+'_'+side)
        controls=controls_by_body.get(parent_body,())
        if parent_body==body:
            expected=spline.pelvis_control if ordinal==0 else spline.fk_controls[-1]
            controls=tuple(control for control in controls if control.control_path==expected)
        else:
            # The source's own FKX parent is the authored control, not a
            # separate SplineBaseFK helper receiving the same start joint.
            controls=tuple(control for control in controls if 'SplineBaseFK' not in control.control_name)
        if len(controls)!=1:
            raise CharacterRegistryError('来源 Spline AlignIKTo 的 FKX 父级不唯一：'+str(parent_body))
        control=controls[0]
        parent=control.source_override_path or control.sub_control_path or control.control_path
        name='AlignIKTo'+body.rsplit('|',1)[-1]
        result.append(SourceSplineAlignmentFrame(body,parent,parent+'|'+name))
    return tuple(result)


def encode_source_spline_alignment(frames):
    value={'version':1,'frames':[asdict(frame) for frame in frames]}
    text=canonical(value)
    decode_source_spline_alignment(text)
    return text


def decode_source_spline_alignment(text):
    value=exact(safe_json(text),('version','frames'))
    if type(value['version']) is not int or value['version']!=1:
        raise CharacterRegistryError('来源 Spline AlignIKTo 版本无效')
    rows=value['frames']
    if not isinstance(rows,list) or len(rows)!=2:
        raise CharacterRegistryError('来源 Spline AlignIKTo 必须登记首尾两个节点')
    frames=tuple(SourceSplineAlignmentFrame(**{key:path(item) for key,item in
        exact(row,('body','parent','target')).items()}) for row in rows)
    # Export converters may rename Body without renaming its reference
    # transform. The locked Body UUID on the scene node proves ownership;
    # requiring the old Body spelling here would reject a valid conversion.
    if (len({frame.body for frame in frames})!=2
            or len({frame.target for frame in frames})!=2 or any(
                frame.target.rsplit('|',1)[0]!=frame.parent
                or not frame.target.rsplit('|',1)[-1].rsplit(':',1)[-1].startswith('AlignIKTo')
                for frame in frames)):
        raise CharacterRegistryError('来源 Spline AlignIKTo 路径或端点身份无效')
    return frames
