"""asMappingUIFunction AutoRigTransferSkinning, MEL 21408 and 21585–21662."""
from .maya_deform_skinning import freeze_native_skin_cluster
from adv_py.core.source_name_matcher import source_name_matcher_targets
from adv_py.application.name_matcher_constraints import NameMatcherSkinTransferResult


def transfer_source_skin(host, source_root, rows, rules):
    """Run the source handoff in order, with physical external DAG addresses.

    Only identity resolution survives DAG reparenting. Bind matrices, weights,
    direct-child selection and the five-parent deletion rule remain the MEL's.
    Maya Undo owns rollback through the enclosing host transaction.
    """
    host._require_transaction()
    c = host._cmds
    raw = getattr(c, 'raw', c)
    namespace = source_root.rsplit('|', 1)[-1].rpartition(':')[0]
    joints = c.listRelatives('DeformationSystem', type='joint',
        allDescendents=True, fullPath=True) or ()
    resolved = source_name_matcher_targets(joints, rows, rules, namespace=namespace)
    host._transaction_changed = True
    links = 0
    missing = []
    for joint, target in resolved:
        if not raw.objExists(target):
            missing.append(target)
        for destination in raw.listConnections(target, plugs=True, source=False,
                destination=True, type='skinCluster') or ():
            if '.matrix' not in destination:
                continue
            raw.connectAttr(host.scene_address(joint) + '.worldMatrix[0]',
                            destination, force=True)
            links += 1

    # Native short names stay valid after reparenting. UUIDs allow the same
    # lookup when an external hierarchy has duplicate leaf names/full paths.
    mapped_ids = frozenset(identity for _, target in resolved
        for identity in (raw.ls(target, uuid=True) or ()))

    def identity(node):
        ids = raw.ls(node, uuid=True) or ()
        if len(ids) != 1:
            raise ValueError('NameMatcher 关节身份不唯一：' + node)
        return ids[0]

    def current(node_id):
        paths = raw.ls(node_id, long=True) or ()
        if len(paths) != 1:
            raise ValueError('NameMatcher 重挂关节后身份丢失：' + node_id)
        return paths[0]

    retained = []
    retained_ids = []
    for joint, target in resolved:
        children = raw.listRelatives(target, children=True, type='joint',
                                     fullPath=True) or ()
        # A preceding reparent may change an entire descendant's path.
        child_ids = tuple(identity(child) for child in children)
        for child_id in child_ids:
            if child_id in mapped_ids:
                continue
            child = current(child_id)
            parents = raw.listRelatives(child, parent=True, fullPath=True) or ()
            previous_parent_id = identity(parents[0])
            if not raw.listConnections(child + '.worldMatrix'):
                raw.delete(child)
                continue
            display_name = child.rsplit('|', 1)[-1]
            raw.parent(child, host.scene_address(joint))
            retained.append(display_name)
            retained_ids.append(child_id)
            child = current(child_id)
            while child:
                descendants = raw.listRelatives(child, children=True,
                                                fullPath=True) or ()
                if not descendants:
                    break
                child = descendants[0]
                if identity(child) in mapped_ids:
                    raw.parent(child, current(previous_parent_id))
                    break
    # These remain the imported influences, not new ADV Body bindings. A
    # provenance tag lets ordinary Body enumeration keep its original set.
    # It changes no joint transform, constraint or Skin weight.
    for branch_id in retained_ids:
        branch = current(branch_id)
        for joint in (branch,*(raw.listRelatives(branch,allDescendents=True,
                type='joint',fullPath=True) or ())):
            attribute = 'advPyAuxiliaryInfluenceKind'
            if not raw.attributeQuery(attribute,node=joint,exists=True):
                raw.addAttr(joint,longName=attribute,dataType='string')
            raw.setAttr(joint+'.'+attribute,lock=False)
            raw.setAttr(joint+'.'+attribute,'name-matcher-external-v1',type='string',lock=True)
    if retained:
        raw.confirmDialog(title='Note', message=(
            'The following Joints does not have a Matching-Joint,\n'
            'so these will be parented to the DeformationSystem:\n\n'
            + '\n'.join(retained) + '\n'), button='Ok', defaultButton='Ok')

    if c.objExists('FaceJoint_M') and c.objExists('Head_M'):
        parents = c.listRelatives('FaceJoint_M', parent=True) or ()
        if not parents or parents[0].rsplit('|', 1)[-1] != 'Head_M':
            c.parent('FaceJoint_M', 'Head_M')
            for node in ('FaceMotionSystem', 'FaceDeformationFollowHead', 'LipFollowHead'):
                if c.objExists(node):
                    c.parentConstraint('Head_M', node, maintainOffset=True)
                    c.scaleConstraint('Head_M', node)

    if resolved:
        target = resolved[-1][1]
        if raw.objExists(target):
            for _ in range(5):
                parents = raw.listRelatives(target, parent=True, fullPath=True) or ()
                if not parents:
                    break
                target = parents[0]
            raw.delete(target)

    raw.dgdirty(allPlugs=True)
    skins = tuple(raw.ls(type='skinCluster') or ())
    for skin in skins:
        freeze_native_skin_cluster(skin, cmds=raw)
        for node in raw.listHistory(skin, future=True, interestLevel=1) or ():
            if raw.objectType(node) == 'mesh':
                raw.skinPercent(skin, node, normalize=True)
    return NameMatcherSkinTransferResult(len(skins), links, len(retained), 0,
                                        tuple(missing))
