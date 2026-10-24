"""Direct port of native embedded Python, MEL 73815–73881."""
from adv_py.core.original_locked_skin_copy import original_locked_copy_weights


def copy_original_skin_weights_obey_locks(*, commands=None, om=None, oma=None):
    if commands is None:
        from maya import cmds as commands
    if om is None:
        import maya.api.OpenMaya as om
    if oma is None:
        import maya.api.OpenMayaAnim as oma
    selected = om.MGlobal.getActiveSelectionList()
    if selected.length() < 2:
        return None
    source_dag, target_dag = selected.getDagPath(0), selected.getDagPath(1)
    source_mesh, target_mesh = source_dag.partialPathName(), target_dag.partialPathName()
    def skin(mesh):
        return next((node for node in commands.listHistory(mesh, pruneDagObjects=True) or []
                     if commands.nodeType(node) == 'skinCluster'), None)
    source_skin, target_skin = skin(source_mesh), skin(target_mesh)
    if not source_skin or not target_skin:
        return None
    source_influences = commands.skinCluster(source_skin, query=True, influence=True) or []
    target_influences = commands.skinCluster(target_skin, query=True, influence=True) or []
    for influence in source_influences:
        if influence not in target_influences:
            commands.skinCluster(target_skin, edit=True, addInfluence=influence, weight=0.0)
    skin_selection = om.MSelectionList()
    skin_selection.add(target_skin)
    target_skin_fn = oma.MFnSkinCluster(skin_selection.getDependNode(0))
    paths = target_skin_fn.influenceObjects()
    locked = tuple(index for index, influence in enumerate(paths)
        if commands.getAttr(influence.partialPathName()+'.lockInfluenceWeights'))
    flags = dict(sourceSkin=source_skin, destinationSkin=target_skin, noMirror=True,
                 surfaceAssociation='closestPoint', influenceAssociation='closestJoint')
    if not locked:
        commands.copySkinWeights(**flags)
        return target_skin
    component_fn = om.MFnSingleIndexedComponent()
    components = component_fn.create(om.MFn.kMeshVertComponent)
    mesh_fn = om.MFnMesh(target_dag)
    component_fn.addElements(list(range(mesh_fn.numVertices)))
    original, _ = target_skin_fn.getWeights(target_dag, components)
    commands.copySkinWeights(**flags, normalize=True)
    copied, _ = target_skin_fn.getWeights(target_dag, components)
    final = om.MDoubleArray(original_locked_copy_weights(original, copied, len(paths), locked))
    # Native embedded Python uses physical 0..N-1 indices here. Preserve it
    # rather than silently switching to a different influence-index policy.
    indices = om.MIntArray(list(range(len(paths))))
    target_skin_fn.setWeights(target_dag, components, indices, final, normalize=True)
    return target_skin
