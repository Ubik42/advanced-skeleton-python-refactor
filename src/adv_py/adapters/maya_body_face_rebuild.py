"""Retain the native Face boundary while replacing its registered Body.

MEL asReBuildAdvancedSkeleton leaves FaceAllSet in the scene, rebuilds Body,
then rejoins the Face sets and their external connections (77930, 78505).
The Face DAG has two Body-owned parents: FaceGroup under Group and
FaceJoint_M under Head_M (31549-31562). Keep both native subtrees by UUID.
"""

from adv_py.core.character_registry import CharacterRegistryError


def retained_roots(host, registration):
    c = host._cmds
    if not c.objExists('FaceAllSet'):
        return ()
    if not (c.objExists('FaceFitSkeleton') and c.objExists('FaceMotionSystem')):
        raise CharacterRegistryError('FaceAllSet 缺少原版 Face 构建根节点')
    group = c.ls('FaceGroup', long=True, type='transform') or []
    joint = c.ls('FaceJoint_M', long=True, type='joint') or []
    if len(group) != 1 or len(joint) != 1:
        raise CharacterRegistryError('Face 保留根节点不唯一')
    generated = {row.path for row in registration.nodes}
    parents = (c.listRelatives(group[0], parent=True, fullPath=True) or [],
               c.listRelatives(joint[0], parent=True, fullPath=True) or [])
    if (parents[0] != [host.scene_address('|Group')]
            or len(parents[1]) != 1 or parents[1][0] not in generated
            or parents[1][0].rsplit('|', 1)[-1] != 'Head_M'
            or not c.sets(joint[0], isMember='FaceAllSet')):
        raise CharacterRegistryError('Face 与 Body 的原版挂接层级已改变')
    return group[0], joint[0]


def boundary_edges(host, edges, registration):
    """Return exact cross-system edges; never infer ownership from a prefix."""
    if not retained_roots(host, registration):
        return frozenset()
    c = host._cmds
    cache = {}
    def face_node(node):
        if node not in cache:
            cache[node] = bool(node in ('FaceAllSet', 'FaceControlSet', 'FaceAreas')
                               or (c.objExists(node) and c.sets(node, isMember='FaceAllSet')))
        return cache[node]
    return frozenset(edge for edge in edges
                     if any(face_node(plug.split('.', 1)[0]) for plug in edge))


def retired_body_helpers(host, registration, replacement_names):
    """Find old Eye/Face Body utilities omitted by the new Fit-driven build.

    EyeBall Fit removes native Eye and Jaw Body branches before building Face.
    The old Body AllSet can retain detached AimEye helpers. MEL deletes these
    with prefix_AllSet. Retire only reserved, old-only nodes whose remaining
    graph never reaches a Face-owned or user-owned node.
    """
    if not retained_roots(host, registration):
        return frozenset()
    from .maya_character_preservation import connections
    c = host._cmds
    old_members = set(host.capture_body_all_set_members())
    saved = {row.path for row in registration.nodes}
    candidates = {node for node in old_members - set(replacement_names)
                  if node not in saved or node.rsplit('|', 1)[-1] == 'AimSystem'
                  if (node.rsplit('|', 1)[-1].startswith('AdvPy_')
                      or node.rsplit('|', 1)[-1] in (
                          'EyeFat', 'EyeEndFat', 'JawFat', 'JawEndFat',
                          'AimSystem'))
                  and c.objExists(node)
                  and not c.sets(node, isMember='FaceAllSet')}
    # Set membership itself is an owned bookkeeping edge. Any other peer
    # outside the old Body graph makes this node ineligible for retirement.
    allowed = old_members | saved | {
        'AllSet', 'ControlSet', 'DeformSet', 'Sets', 'AdvPy_CharacterRegistry'}
    result = set()
    for node in candidates:
        peers = {plug.split('.', 1)[0] for edge in connections(host, node)
                 for plug in edge} - {node}
        if peers <= allowed and all(not c.sets(peer, isMember='FaceAllSet')
                                    for peer in peers if c.objExists(peer)):
            result.add(node)
    return frozenset(result)
