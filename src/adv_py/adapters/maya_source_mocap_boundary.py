"""Read the actual mapped source boundary without imposing a root hierarchy.

asMappingUIFunction addresses each target by name. Imported clips may use
separate DAG roots or driven transforms. Reading their identities does not
adopt their animation, remove their existing drivers, or alter their Skin.
"""
from .maya_source_name_matcher_session import _commands,_node,_plug
from .maya_source_name_matcher_animation import _skins
from adv_py.core.character_registry import CharacterRegistryError


def _nodes(c,targets):
    rows=[]
    for target in dict.fromkeys(targets):
        path,identity=_node(c,target)
        parents=c.listRelatives(path,parent=True,fullPath=True) or ()
        children=c.listRelatives(path,children=True,fullPath=True) or ()
        pairs=c.listConnections(path,source=True,destination=False,
                                plugs=True,connections=True) or ()
        if len(pairs)%2:
            raise CharacterRegistryError('动捕来源输入连接列表不完整：'+path)
        inputs=tuple(sorted((destination.split('.',1)[1],*_plug(c,source))
            for destination,source in zip(pairs[::2],pairs[1::2])))
        rows.append((path,identity,c.nodeType(path),
            tuple(_node(c,parent) for parent in parents),
            tuple(_node(c,child) for child in children),inputs,
            tuple(float(value) for value in c.xform(path,query=True,
                                                    worldSpace=True,matrix=True))))
    return tuple(rows)


def capture(host,mapping):
    c=_commands(host)
    return _nodes(c,(pair.external_joint for pair in mapping.pairs)),_skins(c)


def capture_character(host,source_root):
    """Native AutoRig accepts either a transform top node or a joint.

    It imports the selected source template; it does not reconstruct a
    synthetic Fit description from the imported source joints' metadata.
    """
    c=_commands(host)
    root,_=_node(c,source_root)
    if c.nodeType(root) not in ('joint','transform'):
        raise CharacterRegistryError('NameMatcher 来源顶层节点必须是 joint 或 transform')
    targets=(root,*(node for node in c.listRelatives(root,allDescendents=True,fullPath=True) or ()
                   if c.nodeType(node) in ('joint','transform')))
    return _nodes(c,targets),_skins(c)
