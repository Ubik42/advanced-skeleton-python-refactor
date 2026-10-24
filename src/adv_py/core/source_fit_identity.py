"""Resolve authored Fit settings through actual symmetry provenance.

The left output may mirror a right Fit joint or come from an independently
authored _NonSymmetry branch. A Body name alone cannot choose its settings.
"""
from .fit_settings import FitSkeletonValidationError


def source_fit_reference(body_name, instances):
    found = [instance.source_joint for instance in instances if instance.output_name==body_name]
    if len(found)>1:
        raise FitSkeletonValidationError('来源 Body 对应多个 Fit 关节：'+body_name)
    return found[0] if found else None


def source_fit_metadata(body_name, metadata, instances=()):
    reference = source_fit_reference(body_name,instances)
    if reference is not None:
        found = [item for item in metadata if item.joint==reference]
    else:
        source_name = body_name.rsplit('_',1)[0]
        found = [item for item in metadata if item.joint.rsplit('|',1)[-1].rsplit(':',1)[-1]==source_name]
    if len(found)>1:
        raise FitSkeletonValidationError('来源 Fit 设置身份不唯一：'+body_name)
    return found[0] if found else None


def source_fit_build_name(name):
    return name.rsplit(':',1)[-1].removesuffix('_NonSymmetry')


def source_fit_control_reference(control, instances):
    """Resolve mechanism FK aliases through the expanded Body side."""
    names = {source_fit_build_name(name.rsplit('|', 1)[-1])
             for name in control.fit_joint_names}
    found = {item.source_joint for item in instances
             if item.side == control.side
             and source_fit_build_name(item.output_name.rsplit('_', 1)[0]) in names}
    if len(found) > 1:
        raise FitSkeletonValidationError('控制器来源 Fit 身份不唯一：'+control.control_path)
    return next(iter(found)) if found else None


def source_fit_ik_length(hierarchy, start_name, end_name):
    """MEL 79456–79472 measures the unsuffixed asAdvJointIKInfo names."""
    from math import dist
    nodes={node.path:node for node in hierarchy.joints}
    named={}
    for node in hierarchy.joints:
        named.setdefault(node.short_name.rsplit(':',1)[-1],[]).append(node)
    start=named.get(source_fit_build_name(start_name),())
    end=named.get(source_fit_build_name(end_name),())
    if len(start)!=1 or len(end)!=1:
        raise FitSkeletonValidationError('原版 IK 长度需要唯一的无后缀 Fit 起点和末端')
    current=end[0];total=0.
    for _ in range(99):
        if current.path==start[0].path:
            return abs(total)
        parent=nodes.get(current.dag_parent)
        if parent is None:
            break
        total+=dist(current.world_position,parent.world_position)
        current=parent
    raise FitSkeletonValidationError('原版 IK 长度 Fit 父链未到达起点')


def source_fit_is_end_joint(hierarchy, fit_path, non_terminal_fit=()):
    """MEL 79066–79095 includes detached NonSym previousParent children."""
    return (fit_path not in non_terminal_fit
            and not any(node.dag_parent==fit_path for node in hierarchy.joints))


def source_fit_side_sign(body_name, instances=()):
    """MEL's b2: mirrored L and authored NonSymmetry both use -1."""
    reference=source_fit_reference(body_name,instances)
    under_non_symmetry=reference is not None and any(
        component.rsplit(':',1)[-1].endswith('_NonSymmetry')
        for component in reference.split('|'))
    instances_for_body = tuple(i for i in instances if i.output_name == body_name)
    mirrored = (getattr(instances_for_body[0], 'mirrored', body_name.endswith('_L'))
                if instances_for_body else body_name.endswith('_L'))
    return -1 if mirrored or under_non_symmetry else 1


def source_fit_control_matches(item, control, instances=()):
    """Select the physical Fit row; aliases only serve legacy planners."""
    if instances:
        reference = source_fit_control_reference(control, instances)
        if reference is not None:
            return item.joint == reference
    name = item.joint.rsplit('|', 1)[-1].rsplit(':', 1)[-1]
    return name in control.fit_joint_names
