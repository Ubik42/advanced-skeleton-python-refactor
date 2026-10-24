"""Native asMirrorClusterControlWeights, MEL 58676–58745."""


def mirror_cluster_weights(host, source, target, mesh, side):
    host._require_transaction()
    from maya import cmds as c, mel

    source = host._unique(source, "cluster")
    target = host._unique(target, "cluster")
    mesh = host._mesh(mesh)
    if (side not in ("L", "R") or source == target
            or mesh not in host._cluster_meshes(source)
            or mesh not in host._cluster_meshes(target)):
        raise ValueError("Cluster 镜像源、目标或侧别无效")
    selection = c.ls(selection=True) or []
    host._transaction_changed = True
    from .maya_face_deformer_sets import original_deformer_set
    c.select(original_deformer_set(c, source), replace=True)
    vertices = c.ls(selection=True, flatten=True) or []
    c.percent(target, mesh, value=0)
    sampler_name = host.scene_address("closestSampler")
    if c.objExists(sampler_name):c.delete(sampler_name)
    sampler = c.createNode("closestPointOnMesh", name=sampler_name)
    # Source deliberately omits inputMatrix: it relies on frozen mesh xforms.
    c.connectAttr(mesh + ".outMesh", sampler + ".inMesh")
    progress = None
    try:
        if not c.about(batch=True):
            progress = mel.eval("$advPyProgress = $gMainProgressBar")
            c.progressBar(progress, edit=True, status="Mirroring", beginProgress=True,
                          isInterruptable=True, minValue=0, maxValue=len(vertices))
        for vertex in vertices:
            if progress:
                if c.progressBar(progress, query=True, isCancelled=True):
                    raise RuntimeError("Interrupted")
                c.progressBar(progress, edit=True, step=1)
            weights = c.percent(source, vertex, query=True, value=True)
            position = c.xform(vertex, query=True, worldSpace=True, translation=True)
            if ((side == "R" and position[0] > -.001)
                    or (side == "L" and position[0] < .001)):
                continue
            c.setAttr(sampler + ".inPosition", -position[0], position[1], position[2])
            index = c.getAttr(sampler + ".closestVertexIndex")
            # Each set member writes immediately. Zero weights and collisions
            # are meaningful; the last native traversal write wins.
            c.percent(target, mesh + ".vtx[%d]" % index, value=weights[0])
    finally:
        if progress:c.progressBar(progress, edit=True, endProgress=True)
        if c.objExists(sampler):c.delete(sampler)
        c.select(selection, replace=True) if selection else c.select(clear=True)
