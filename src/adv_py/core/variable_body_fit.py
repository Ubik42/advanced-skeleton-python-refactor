from .body_description import BodyAxialDescription
from .fit_template import FitJointSpec,FitTemplateSpec,synthetic_body_source_fit_template
from .fit_settings import FitSkeletonValidationError
from .fit_hierarchy import FitHierarchySnapshot
import re


def variable_axial_description(spine_segments=2):
    if isinstance(spine_segments,bool) or not isinstance(spine_segments,int) or not 1<=spine_segments<=63:
        raise FitSkeletonValidationError('脊柱段数必须为 1..63 的整数')
    return BodyAxialDescription(('Root_M',*(f'Spine{i}_M' for i in range(1,spine_segments)),'Chest_M'))


def axial_description_from_fit(snapshot: FitHierarchySnapshot,
                               requested_segments: int | None = None):
    """Resolve the Body axial chain from a Fit snapshot before scene writes."""
    names = {joint.short_name for joint in snapshot.joints}
    indices = sorted(int(name[5:]) for name in names
                     if re.fullmatch(r'Spine[1-9]\d*', name))
    if 'Chest' not in names or indices != list(range(1, len(indices) + 1)):
        raise FitSkeletonValidationError(
            'Fit 脊柱关节须为连续 Spine1…SpineN，末端为 Chest')
    actual = len(indices) + 1
    if requested_segments is not None:
        variable_axial_description(requested_segments)
        if requested_segments != actual:
            raise FitSkeletonValidationError(
                f'Fit 实际脊柱为 {actual} 段，输入为 {requested_segments} 段')
    return None if actual == 2 else variable_axial_description(actual)


def variable_body_fit_template(up_axis,*,spine_segments=2,scale=1.,with_hand=True):
    description=variable_axial_description(spine_segments)
    if not isinstance(with_hand,bool):raise FitSkeletonValidationError('with_hand 必须是布尔值')
    from .body_hand_fit import synthetic_body_with_hand_source_fit_template
    base=(synthetic_body_with_hand_source_fit_template if with_hand else synthetic_body_source_fit_template)(up_axis,scale=scale)
    joints={j.name:j for j in base.joints}
    step=tuple((a+b)/spine_segments for a,b in zip(joints['Spine1'].local_position,joints['Chest'].local_position))
    names=tuple(n.removesuffix('_M') for n in description.spine)
    chain=tuple(FitJointSpec(name,parent,step,joints['Chest'].label) for name,parent in zip(names[1:],names))
    return FitTemplateSpec('synthetic_variable_body',tuple(j for j in base.joints if j.name not in ('Spine1','Chest'))+chain)
