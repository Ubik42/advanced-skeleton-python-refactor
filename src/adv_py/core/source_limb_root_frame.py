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
    measurements: tuple[tuple[str,tuple[float,...]],...] = ()


def decode_record(text):
    from .character_registry import safe_json,exact,canonical,path,vector,CharacterRegistryError
    raw=safe_json(text)
    if isinstance(raw,dict) and 'measurements' not in raw:raw={**raw,'measurements':[]}
    raw=exact(raw,('graph','offset','offset_matrix','joint','rotate_order','measurements'))
    graph=decode_source_body_matrix(canonical(raw['graph']), allow_decompose_outputs=True)
    offset=path(raw['offset']);joint=path(raw['joint']);order=raw['rotate_order']
    if (type(order) is not int or not 0<=order<=5 or offset.rsplit('|',1)[0]!=graph.body
            or joint.rsplit('|',1)[0]!=offset):
        raise CharacterRegistryError('来源 IK 起点绑定层级记录无效')
    rows=raw['measurements']
    if (not isinstance(rows,list) or len(rows)>1 or any(
            not isinstance(row,list) or len(row)!=2 for row in rows)):
        raise CharacterRegistryError('来源 IK 起点测量绑定数量无效')
    measurements=tuple((path(node),vector(matrix,16)) for node,matrix in rows)
    if any(node.rsplit('|',1)[0]!=graph.body or node in (offset,joint) for node,_ in measurements):
        raise CharacterRegistryError('来源 IK 起点测量绑定父级无效')
    return SourceIkRootFrameRecord(graph,offset,vector(raw['offset_matrix'],16),joint,order,measurements)


def plan_graph(frame, parent, source, rotate_order, use_offset_parent_matrix):
    """MEL asParentConstraint -includePickMatrix -FMM respects Fit.opm."""
    from .source_rp_dynamics import SourceRpNode
    if type(use_offset_parent_matrix) is not bool:
        raise ValueError('IK root matrix mode must be boolean')
    stem = frame.rsplit('|', 1)[-1]
    matrix, pick, dm = stem + 'MM', stem + 'PM', stem + 'DM'
    nodes = [SourceRpNode(matrix, 'multMatrix', connections=(
        (source + '.worldMatrix[0]', 'matrixIn[0]'), (parent + '.worldInverseMatrix[0]', 'matrixIn[1]'))),
        SourceRpNode(pick, 'pickMatrix', (('useScale', 0.), ('useShear', 0.)),
                     ((matrix + '.matrixSum', 'inputMatrix'),))]
    if use_offset_parent_matrix:
        outputs = ((pick + '.outputMatrix', frame + '.offsetParentMatrix'),)
    else:
        nodes.append(SourceRpNode(dm, 'decomposeMatrix', (('inputRotateOrder', float(rotate_order)),),
                                  ((pick + '.outputMatrix', 'inputMatrix'),)))
        outputs = tuple((dm + '.output' + channel + axis, frame + '.' + target + suffix)
                        for channel, target in (('Translate', 'translate'), ('Rotate', 'rotate'),
                                                ('Scale', 'scale'), ('Shear', 'shear'))
                        for axis, suffix in zip('XYZ', ('XY', 'XZ', 'YZ') if target == 'shear' else 'XYZ'))
    return SourceBodyMatrixPlan(frame, tuple(nodes), outputs)


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
