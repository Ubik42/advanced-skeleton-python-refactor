"""Keep native unmapped, reparented Skin influences across Body rebuilding."""
from adv_py.core.character_registry import CharacterRegistryError

MARKER='advPyAuxiliaryInfluenceKind'
KIND='name-matcher-external-v1'


def retained_roots(host,registration):
    """Discover the imported branches by their saved native provenance.

    These are the original joint objects moved by AutoRigTransferSkinning;
    they are attachments, not generated Body replacements. The existing
    extension handoff keeps their UUIDs, local transforms and Skin edges.
    """
    c=host._cmds
    generated={row.path for row in registration.nodes}
    body={joint.path for joint in registration.body}
    branches=set()
    for node in c.listRelatives(registration.body_root,allDescendents=True,
                               type='joint',fullPath=True) or ():
        if not c.attributeQuery(MARKER,node=node,exists=True):continue
        if c.getAttr(node+'.'+MARKER)!=KIND:continue
        if (node in generated or c.getAttr(node+'.'+MARKER,type=True)!='string'
                or not c.getAttr(node+'.'+MARKER,lock=True)):
            raise CharacterRegistryError('NameMatcher 保留影响关节的来源标记无效：'+node)
        branches.add(node)
    roots=tuple(sorted(node for node in branches
        if not any(node.startswith(parent+'|') for parent in branches if parent!=node)))
    for root in roots:
        parents=c.listRelatives(root,parent=True,fullPath=True) or ()
        if len(parents)!=1 or parents[0] not in body:
            raise CharacterRegistryError('NameMatcher 保留分支没有原版对应 Body 父级：'+root)
    return roots
