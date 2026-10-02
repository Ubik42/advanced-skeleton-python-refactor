"""MEL 80433–80499: IKParentConstraint → IKXOffset → zero-JO IKX."""
from dataclasses import dataclass,replace
from .body_limb_mechanisms import BodyLimbMechanismRole
from .source_body_matrix import SourceBodyMatrixPlan,decode_source_body_matrix


@dataclass(frozen=True,slots=True)
class SourceLimbRootFrame:
    frame: str
    offset: str
    parent: str
    source_parent: str | None
    source_joint: str
    joint: str
    parent_position: tuple
    parent_axes: tuple
    position: tuple
    axes: tuple
    rotate_order: int


@dataclass(frozen=True,slots=True)
class SourceIkRootFrameRecord:
    graph: SourceBodyMatrixPlan
    offset: str
    offset_matrix: tuple[float,...]
    joint: str
    rotate_order: int


def decode_record(text):
    from .character_registry import safe_json,exact,canonical,path,vector,CharacterRegistryError
    raw=exact(safe_json(text),('graph','offset','offset_matrix','joint','rotate_order'))
    graph=decode_source_body_matrix(canonical(raw['graph']))
    offset=path(raw['offset']);joint=path(raw['joint']);order=raw['rotate_order']
    if (type(order) is not int or not 0<=order<=5 or offset.rsplit('|',1)[0]!=graph.body
            or joint.rsplit('|',1)[0]!=offset):
        raise CharacterRegistryError('来源 IK 起点绑定层级记录无效')
    return SourceIkRootFrameRecord(graph,offset,vector(raw['offset_matrix'],16),joint,order)


def configure(plan,body):
    by_path={joint.path:joint for joint in body.joints};frames=[];rewrites=[]
    for joint in plan.joints:
        if joint.role is not BodyLimbMechanismRole.IK or joint.parent_path!=plan.root_path:continue
        source=by_path[joint.source_joint];parent=source.parent_path
        while parent in by_path and 'Part' in by_path[parent].name:parent=by_path[parent].parent_path
        reference=by_path.get(parent,source)
        stem='AdvPy_'+plan.limb_label+'IKParent_'+joint.side.value
        frame=plan.root_path+'|'+stem;offset=frame+'|'+stem+'Offset';target=offset+'|'+joint.name
        frames.append(SourceLimbRootFrame(frame,offset,plan.root_path,parent,joint.source_joint,target,
            reference.world_position,reference.world_axes,joint.world_position,joint.world_axes,source.rotation_order))
        rewrites.append((joint.path,target))
    def remap(path):
        for old,new in rewrites:
            if path==old or path.startswith(old+'|'):return new+path[len(old):]
        return path
    offsets={item.joint:item.offset for item in frames}
    joints=tuple(replace(joint,path=remap(joint.path),parent_path=offsets.get(remap(joint.path),remap(joint.parent_path)))
                 for joint in plan.joints)
    return replace(plan,joints=joints),tuple(frames)
