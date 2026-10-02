"""ADV 6.925 83335–83338: Root's preferred child's Twist uses FKOffset."""
from .fit_part import _source_rla_child


def source_root_primary_child(hierarchy, fit_scale=1.0):
    roots=[node for node in hierarchy.joints
           if node.short_name.rsplit(':',1)[-1]=='Root']
    if not roots:return None
    if len(roots)!=1:raise ValueError('来源 Root 身份不唯一')
    root=roots[0]
    children=sorted((node for node in hierarchy.joints if node.dag_parent==root.path),
                    key=lambda node:node.sibling_index)
    return _source_rla_child(root,children,0.01*fit_scale)


def plan_source_root_twist_references(build,paths,fk,splines=()):
    child=source_root_primary_child(build.symmetry.source.hierarchy,
                                    build.symmetry.source.fit_scale)
    if child is None:return {}
    starts={paths.remap_body_reference(part.start_body)
            for part in build.fit_parts if part.kind=='twist' and part.source_joint==child.path}
    if not starts:return {}
    # Spline FK controls may drive an independent mechanism with the original
    # deformation joint recorded separately; preserve that exact source identity.
    original_by_driver={joint.path:joint.source_joint for spline in splines for joint in spline.joints}
    result={}
    for control in fk.controls:
        original=original_by_driver.get(control.driven_joint,control.driven_joint)
        body=paths.remap_body_reference(original)
        if body not in starts:continue
        if body in result:raise ValueError('Root 首子 Twist 的 FKOffset 不唯一')
        result[body]=control.offset_path+'.worldInverseMatrix[0]'
    if set(result)!=starts:raise ValueError('Root 首子 Twist 缺少对应 FKOffset')
    return result
