from .body_description import BodyAxialDescription
from .fit_template import FitJointSpec,FitTemplateSpec,synthetic_body_source_fit_template
from .fit_settings import FitSkeletonValidationError
from .fit_hierarchy import FitHierarchySnapshot
from .fit_ik import fit_joint_chain


def variable_axial_description(spine_segments=2):
    if isinstance(spine_segments,bool) or not isinstance(spine_segments,int) or not 1<=spine_segments<=63:
        raise FitSkeletonValidationError('脊柱段数必须为 1..63 的整数')
    return BodyAxialDescription(('Root_M',*(f'Spine{i}_M' for i in range(1,spine_segments)),'Chest_M'))


def axial_description_from_fit(snapshot: FitHierarchySnapshot,
                               requested_segments: int | None = None, *,
                               spine_chain: tuple[str, ...] | None = None):
    """Resolve the prepared torso by its DAG chain, not global name counts.

    MEL obtains its spline joints from the start/end ancestry. A Spine-like
    name elsewhere in the skeleton must not change this chain, and intermediate
    joints do not have to use consecutive numeric suffixes.
    """
    by_path = {joint.path: joint for joint in snapshot.joints}
    by_name = {joint.short_name: joint for joint in snapshot.joints}
    if len(by_path) != len(snapshot.joints) or len(by_name) != len(by_path):
        raise FitSkeletonValidationError('准备后的 Fit 关节路径和名称必须唯一')
    root = by_name.get('Root')
    chest = (by_path.get(spine_chain[-1]) if spine_chain
             else by_name.get('Chest'))
    if root is None or chest is None:
        raise FitSkeletonValidationError('身体主构建需要准备后的 Root 和 Chest')

    def ancestors_to(start, end):
        return tuple(by_path[path].short_name + '_M'
                     for path in fit_joint_chain(snapshot, start.path, end.path))

    spine = ancestors_to(root, chest)
    head = by_name.get('Head')
    neck = (ancestors_to(chest, head)[1:] if head is not None
            else BodyAxialDescription().neck)
    actual = len(spine) - 1
    if requested_segments is not None:
        variable_axial_description(requested_segments)
        if requested_segments != actual:
            raise FitSkeletonValidationError(
                f'Fit 实际脊柱为 {actual} 段，输入为 {requested_segments} 段')
    description = BodyAxialDescription(spine=spine, neck=neck)
    return None if description == BodyAxialDescription() else description


def variable_body_fit_template(up_axis,*,spine_segments=2,scale=1.,with_hand=True):
    description=variable_axial_description(spine_segments)
    if not isinstance(with_hand,bool):raise FitSkeletonValidationError('with_hand 必须是布尔值')
    from .body_hand_fit import synthetic_body_with_hand_source_fit_template
    base=(synthetic_body_with_hand_source_fit_template if with_hand else synthetic_body_source_fit_template)(up_axis,scale=scale)
    joints={j.name:j for j in base.joints}
    step=tuple((a+b)/spine_segments for a,b in zip(joints['Spine1'].local_position,joints['Chest'].local_position))
    names=tuple(n.removesuffix('_M') for n in description.spine)
    chain=tuple(FitJointSpec(name,parent,step,
                joints['Chest'].label if name=='Chest' else joints['Spine1'].label)
                for name,parent in zip(names[1:],names))
    return FitTemplateSpec('synthetic_variable_body',tuple(j for j in base.joints if j.name not in ('Spine1','Chest'))+chain)
