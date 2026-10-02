"""ADV 7694 FitGeometry segments and 7254 live visualizer aim dispatch."""
from dataclasses import dataclass

from .fit_part import _source_rla_child
from .fit_orientation import _rp_fit_chains


@dataclass(frozen=True, slots=True)
class FitGeometrySegment:
    joint: str
    child: str
    stem: str
    parts: int
    up_object: str
    up_type: str
    up_vector: tuple[float,float,float]
    world_up_vector: tuple[float,float,float]


def plan_fit_geometry(snapshot, *, poly_boxes=False):
    nodes=snapshot.hierarchy.joints
    metadata={item.joint:item for item in snapshot.metadata}
    labels=dict(snapshot.labels)
    rp=_rp_fit_chains(snapshot)
    secondary=snapshot.axis_configuration.secondary
    up=tuple((-1. if secondary.value.startswith('-') else 1.)
             if axis==secondary.value[-1] else 0. for axis in 'xyz')
    plans=[]
    # listRelatives -ad is descendants-first; keep its sibling order.
    paths={node.path for node in nodes}
    ordered=[]
    def visit(node):
        for child in sorted((child for child in nodes if child.dag_parent==node.path),
                            key=lambda child:child.sibling_index):
            visit(child)
        ordered.append(node)
    for root in sorted((node for node in nodes if node.dag_parent not in paths),
                       key=lambda node:node.sibling_index):
        visit(root)
    for node in ordered:
        stem=node.short_name.rsplit(':',1)[-1]
        children=sorted((child for child in nodes if child.dag_parent==node.path),
                        key=lambda child:child.sibling_index)
        child=_source_rla_child(node,children,.01*snapshot.fit_scale)
        if child is None and stem=='Root' and children: child=children[0]
        if child is None or '*Jaw*'==stem or 'Eye' in stem:
            continue
        if not poly_boxes and any(word in stem for word in ('Ankle','Wrist','Cup')):
            continue
        item=metadata.get(node.path)
        count=1+(item.twist_joints or 0)+(item.inbetween_joints or 0) if item else 1
        world_up_object=node.path
        up_type='objectrotation'
        local_up=(0.,1.,0.)
        world_up=up
        chain=rp.get(node.path)
        if chain and not (item and (item.free_orient or item.world_orient_up is not None)):
            start,end,role=chain
            if role=='start':
                world_up_object=end
                up_type='object'
                label=labels.get(start)
                local_up=(0.,-1. if label and 'Hip' in label.text else 1.,0.)
            else:
                world_up_object=start.rsplit('|',1)[-1].rsplit(':',1)[-1]+'Aim'
                world_up=(0.,1.,0.)
        plans.append(FitGeometrySegment(node.path,child.path,stem,count,
            world_up_object,up_type,local_up,world_up))
    return tuple(plans)
