"""Read the original end-joint ikLocal enum without changing RP defaults."""
from dataclasses import replace


def configure_source_limb_ik(ik,mechanisms,body,metadata,end_name):
    by_name={joint.name:joint for joint in body.joints}
    item=next((item for item in metadata
               if item.joint.rsplit('|',1)[-1].rsplit(':',1)[-1]==end_name),None)
    specs=[]
    for spec in ik.limbs:
        end=by_name[end_name+'_'+spec.side.value]
        middle=next(joint for joint in mechanisms.joints if joint.path==spec.chain[1])
        # The original query takes the middle of the full source chain;
        # the mechanism plan already carries the corresponding bind point.
        specs.append(replace(spec,source_aligned_graph=True,
            ik_local_mode=item.ik_local_mode if item else None,
            source_middle_position=middle.world_position,
            source_middle_axes=middle.world_axes,
            source_rotation_order=end.rotation_order,
            source_foot_orientation=bool(end.label and 'Foot' in end.label.text)))
    return replace(ik,limbs=tuple(specs))
