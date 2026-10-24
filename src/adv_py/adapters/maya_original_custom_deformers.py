"""Literal Cluster and SoftMod custom-controller graphs, MEL 58151–58436."""
from math import dist
from contextlib import nullcontext

from .maya_face_deformer_sets import original_face_deformer_sets
from .maya_original_custom_skin import _parent_constraint
from .maya_original_transform_channels import align_original_transform


def _sphere(host, c, plan, kind, color, shader_color):
    address = host.scene_address
    shader = address("as" + kind + "ControlShader")
    if not c.objExists(shader):
        c.shadingNode("lambert", name=shader, asShader=True)
        group = c.sets(renderable=True, noSurfaceShader=True, empty=True, name=shader + "SG")
        c.connectAttr(shader + ".outColor", group + ".surfaceShader", force=True)
        c.setAttr(shader + ".color", *shader_color, type="float3")
    control = c.sphere(name=address(plan.control_name), pivot=(0,0,0), axis=(0,1,0),
        startSweep=0, endSweep=360, radius=plan.region.falloff_radius/4., degree=3,
        useTolerance=False, tolerance=.01, sections=8, spans=4, constructionHistory=False)[0]
    c.addAttr(control, longName="localOrient", attributeType="bool", defaultValue=plan.local)
    c.addAttr(control, longName=kind[0].lower()+kind[1:]+"Control", attributeType="bool", defaultValue=1)
    c.sets(control, edit=True, forceElement=shader + "SG")
    for shape in c.listRelatives(control, shapes=True, fullPath=True) or []:
        c.setAttr(shape + ".overrideEnabled", 1)
        c.setAttr(shape + ".overrideColor", color)
        for attr in ("castsShadows","receiveShadows","motionBlur","primaryVisibility",
                     "smoothShading","visibleInReflections","visibleInRefractions"):
            if c.objExists(shape + "." + attr):c.setAttr(shape + "." + attr, 0)
    return control


def _metadata(host, c, plan, control, deformer, parent, count, paths, base=None):
    c.addAttr(control, longName="parent", dataType="string")
    c.setAttr(control + ".parent", parent.rsplit("|",1)[-1], type="string")
    c.addAttr(control, longName="advPyCustomControlKind", dataType="string")
    c.setAttr(control + ".advPyCustomControlKind", plan.kind.value, type="string", lock=True)
    c.addAttr(control, longName="advPyCustomControlWeightCount", attributeType="long")
    c.setAttr(control + ".advPyCustomControlWeightCount", count, lock=True)
    for attribute, target in (("Deformer",deformer),("Parent",parent)):
        c.addAttr(control, longName="advPyCustomControl"+attribute, attributeType="message")
        c.connectAttr(target + ".message", control + ".advPyCustomControl" + attribute)
    c.delete(host._unique(plan.region.source_handle, "transform"))
    if c.objExists(plan.region.deformer):c.delete(plan.region.deformer)
    host._register_custom_nodes(paths, control, base)


def create_softmod(host, plan):
    host._require_transaction()
    from maya import cmds as c
    address = host.scene_address
    host._transaction_changed = True
    parent = host._unique_custom_parent(plan.parent_joint)
    if plan.partial_parent:parent = host._ensure_custom_partial_parent(parent)
    mesh = host._mesh(plan.region.mesh)
    source = host._unique(plan.region.deformer, "softMod")
    system = host._custom_system()
    control = _sphere(host, c, plan, "SoftMod", 14, (0,1,0))
    attach = c.createNode("transform", name=address(plan.auxiliary_name("attach")))
    attach = c.parent(attach, system)[0]
    scope = host._cmds._creation_namespace if hasattr(host._cmds,"_creation_namespace") else nullcontext
    with scope(), original_face_deformer_sets(host._cmds):
        deformer, handle = c.softMod(mesh)
    deformer = c.rename(deformer, address(plan.deformer_name))
    handle = c.rename(handle, address(plan.name + "SoftModModHandle" + plan.side))
    sets = c.listConnections(deformer + ".message") or []
    c.rename(sets[0], address(plan.name + "SoftModSet" + plan.side))
    shape = c.listRelatives(handle, shapes=True, fullPath=True)[0]
    c.setAttr(shape + ".origin", *plan.region.center, type="float3")
    c.setAttr(deformer + ".falloffCenter", *plan.region.center)
    c.xform(handle, pivots=plan.region.center)
    mirrored = c.objExists(address("CustomControlMirrorSoftModHandle"))
    if not mirrored:c.nodePreset(save=(source, "asSoftMod"))
    c.nodePreset(load=(deformer, "asSoftMod"))
    if mirrored:c.setAttr(deformer + ".falloffCenterX", -c.getAttr(deformer + ".falloffCenterX"))
    base = c.curve(name=address(plan.base_control_name), degree=1,
        point=((0,1,0),(0,-1,0),(0,0,0),(1,0,0),(-1,0,0)), knot=(0,1,2,3,4))
    c.addAttr(base, longName="localOrient", attributeType="bool", defaultValue=plan.local)
    size = plan.region.falloff_radius / 4. / .4
    c.scale(size, size, size, base + ".cv[0:4]", relative=True, pivot=(0,0,0))
    shape = c.listRelatives(base, shapes=True, fullPath=True)[0]
    c.setAttr(shape + ".overrideEnabled", 1);c.setAttr(shape + ".overrideColor", 17)
    base = c.parent(base, attach)[0]
    control = c.parent(control, base)[0]
    locator = c.spaceLocator(name=address(plan.auxiliary_name("locator")))[0]
    locator = c.parent(locator, base)[0]
    c.setAttr(locator + ".v", 0, lock=True);c.setAttr(handle + ".v", 0, lock=True)
    shape = c.listRelatives(locator, shapes=True, fullPath=True)[0]
    c.connectAttr(shape + ".worldPosition[0]", deformer + ".falloffCenter")
    c.xform(attach, worldSpace=True, translation=plan.region.center)
    if plan.local:c.delete(c.orientConstraint(parent, attach))
    _parent_constraint(host, c, parent, attach, True)
    shape = c.listRelatives(handle, shapes=True, fullPath=True)[0]
    c.disconnectAttr(shape + ".softModTransforms[0]", deformer + ".softModXforms")
    c.disconnectAttr(handle + ".worldMatrix[0]", deformer + ".matrix")
    c.delete(handle)
    c.connectAttr(attach + ".worldMatrix[0]", deformer + ".matrix")
    c.connectAttr(base + ".worldInverseMatrix[0]", deformer + ".postMatrix")
    c.connectAttr(base + ".worldMatrix[0]", deformer + ".preMatrix")
    matrix = c.createNode("multMatrix", name=address(plan.auxiliary_name("matrix")))
    c.connectAttr(control + ".worldMatrix[0]", matrix + ".matrixIn[0]")
    c.connectAttr(control + ".parentInverseMatrix[0]", matrix + ".matrixIn[1]")
    c.connectAttr(matrix + ".matrixSum", deformer + ".softModXforms.weightedMatrix")
    c.addAttr(control, longName="falloffRadius", attributeType="double", defaultValue=1, keyable=True)
    c.addAttr(control, longName="falloffMode", attributeType="enum", enumName="volume:surface:",
              defaultValue=plan.region.falloff_mode, keyable=True)
    c.connectAttr(control + ".falloffMode", deformer + ".falloffMode")
    factor = c.createNode("multiplyDivide", name=address(plan.auxiliary_name("radius_factor")))
    c.connectAttr(control + ".falloffRadius", factor + ".input1X")
    c.setAttr(factor + ".input2X", plan.region.falloff_radius)
    scale = c.createNode("multiplyDivide", name=address(plan.auxiliary_name("radius_scale")))
    c.connectAttr(factor + ".outputX", scale + ".input1X")
    c.connectAttr(attach + ".sx", scale + ".input2X")
    c.connectAttr(scale + ".outputX", deformer + ".falloffRadius")
    _metadata(host,c,plan,control,deformer,parent,sum(row.weight>0 for row in plan.region.weights),
              (attach,base,control),base)


def create_cluster(host, plan):
    host._require_transaction()
    from maya import cmds as c, mel
    address = host.scene_address
    host._transaction_changed = True
    parent = host._unique_custom_parent(plan.parent_joint)
    if plan.partial_parent:parent = host._ensure_custom_partial_parent(parent)
    mesh = host._mesh(plan.region.mesh)
    source = host._unique(plan.region.deformer, "softMod")
    source_handle = host._unique(plan.region.source_handle, "transform")
    system = host._custom_system()
    control = _sphere(host,c,plan,"Cluster",13,(1,0,0))
    group = c.createNode("transform", name=address(plan.auxiliary_name("cluster_group")), parent=system)
    c.setAttr(group + ".inheritsTransform", 0, lock=True)
    attach = c.createNode("transform", name=address(plan.auxiliary_name("attach")))
    attach = c.parent(attach,group)[0]
    offset = c.createNode("transform", name=address(plan.offset_name))
    subtract = c.createNode("transform", name=address(plan.auxiliary_name("subtract")))
    control = c.parent(control,subtract)[0]
    subtract = c.parent(subtract,offset)[0]
    offset = c.parent(offset,attach)[0]
    if not plan.local:offset = c.parent(offset,world=True)[0]
    dm = c.createNode("decomposeMatrix", name=address(plan.auxiliary_name("offset_decompose")))
    c.connectAttr(parent + ".worldMatrix[0]", dm + ".inputMatrix")
    c.connectAttr(dm + ".outputRotate", attach + ".r")
    c.connectAttr(dm + ".outputScale", attach + ".s")
    if not plan.local:offset = c.parent(offset,attach)[0]
    control = host._unique(plan.control_name,"transform")
    subtract = host._unique(plan.auxiliary_name("subtract"),"transform")
    pma = c.createNode("plusMinusAverage", name=address(plan.auxiliary_name("translation_subtract")))
    c.setAttr(pma + ".operation", 2)
    c.connectAttr(control + ".t", pma + ".input3D[0]", force=True)
    c.connectAttr(control + ".t", pma + ".input3D[1]", force=True)
    c.disconnectAttr(control + ".t", pma + ".input3D[0]")
    offset = c.parent(offset,world=True)[0]
    control = host._unique(plan.control_name,"transform")
    subtract = host._unique(plan.auxiliary_name("subtract"),"transform")
    c.connectAttr(pma + ".output3D", subtract + ".t", force=True)
    c.xform(offset,worldSpace=True,translation=plan.region.center)
    scope = host._cmds._creation_namespace if hasattr(host._cmds,"_creation_namespace") else nullcontext
    with scope(), original_face_deformer_sets(host._cmds):deformer,handle = c.cluster(mesh)
    deformer = c.rename(deformer,address(plan.deformer_name))
    handle = c.rename(handle,address(plan.auxiliary_name("handle")))
    sets = c.listConnections(deformer + ".message") or []
    c.rename(sets[0],address("ClusterSet"+plan.name+plan.side))
    shape = c.listRelatives(handle,shapes=True,fullPath=True)[0]
    c.setAttr(shape + ".origin",*plan.region.center,type="float3")
    c.xform(handle,pivots=plan.region.center)
    handle = c.parent(handle,group)[0]
    c.setAttr(handle + ".v",0,lock=True)
    matrix_nodes = []
    for number,family in enumerate(("T","R")):
        matrix = c.createNode("multMatrix",name=address("MM"+family+plan.name+plan.side))
        decompose = c.createNode("decomposeMatrix",name=address("DM"+family+plan.name+plan.side))
        c.connectAttr(control + ".matrix",matrix + f".matrixIn[{number}]")
        c.connectAttr(matrix + ".matrixSum",decompose + ".inputMatrix")
        c.connectAttr(control + ".rotateOrder",decompose + ".inputRotateOrder")
        matrix_nodes.append((matrix,decompose))
    (mt,dt),(mr,dr) = matrix_nodes
    c.connectAttr(dt + ".outputTranslate",handle + ".t")
    c.connectAttr(dt + ".outputScale",handle + ".s")
    c.connectAttr(dr + ".outputRotate",handle + ".r")
    temp = c.createNode("transform",name=address("tempMatrixXform"))
    temp = align_original_transform(c,temp,control,False,True)
    frame = c.xform(temp,query=True,objectSpace=True,matrix=True)
    c.setAttr(mt + ".matrixIn[1]",*frame,type="matrix")
    c.setAttr(mr + ".matrixIn[2]",*frame,type="matrix")
    inverse = c.getAttr(temp + ".inverseMatrix")
    if len(inverse) == 1 and isinstance(inverse[0], (tuple, list)):
        inverse = inverse[0]
    c.setAttr(mr + ".matrixIn[0]",*inverse,type="matrix")
    c.delete(temp)
    c.select(mesh,replace=True)
    c.polySelectConstraint(mode=3,type=1,dist=1,distbound=(0,plan.region.falloff_radius),distpoint=plan.region.center)
    vertices = c.ls(selection=True,flatten=True) or []
    c.polySelectConstraint(mode=0)
    history = c.listHistory(mesh,pruneDagObjects=True,interestLevel=2) or []
    for node in history:c.setAttr(node + ".nodeState",1)
    c.setAttr(source + ".nodeState",0)
    c.percent(deformer,mesh + ".vtx[0:99999]",value=0)
    progress = None
    if not c.about(batch=True):
        progress = mel.eval("$advPyCustomProgress = $gMainProgressBar")
        c.progressBar(progress,edit=True,status="Converting SoftMod ("+plan.side+")",
                      beginProgress=True,isInterruptable=True,minValue=0,maxValue=len(vertices))
    maximum = 0.; strongest = ""; count = 0
    try:
        for vertex in vertices:
            if progress:
                if c.progressBar(progress,query=True,isCancelled=True):raise RuntimeError("Interrupted")
                c.progressBar(progress,edit=True,step=1)
            c.setAttr(source_handle + ".t",0,1,0,type="float3")
            moved = c.xform(vertex,query=True,worldSpace=True,translation=True)
            c.setAttr(source_handle + ".t",0,0,0,type="float3")
            rest = c.xform(vertex,query=True,worldSpace=True,translation=True)
            weight = moved[1]-rest[1]
            c.percent(deformer,vertex,value=weight)
            count += weight>0
            if weight>maximum:maximum,strongest = weight,vertex
        for node in history:c.setAttr(node + ".nodeState",0)
    finally:
        if progress:c.progressBar(progress,edit=True,endProgress=True)
    c.select(strongest,replace=True)
    with scope():mel.eval("ConvertSelectionToEdges;")
    edges = c.ls(selection=True,flatten=True) or []
    c.select(edges[0],replace=True)
    with scope():curve,edge_node = c.duplicateCurve(constructionHistory=True,range=False,local=False)
    curve = c.rename(curve,address(plan.auxiliary_name("edge_curve")))
    c.rename(edge_node,address(plan.auxiliary_name("edge_source")))
    curve = c.parent(curve,group)[0]
    c.setAttr(curve + ".v",0,lock=True)
    point = c.createNode("pointOnCurveInfo",name=address(plan.auxiliary_name("curve_point")))
    c.setAttr(point + ".turnOnPercentage",1)
    shape = c.listRelatives(curve,shapes=True,fullPath=True)[0]
    c.connectAttr(shape + ".worldSpace[0]",point + ".inputCurve",force=True)
    c.connectAttr(point + ".position",attach + ".t",force=True)
    position = c.xform(strongest,query=True,worldSpace=True,translation=True)
    first = c.getAttr(point + ".position")[0]
    c.setAttr(point + ".parameter",1)
    second = c.getAttr(point + ".position")[0]
    if dist(position,first)<dist(position,second):c.setAttr(point + ".parameter",0)
    offset = c.parent(offset,attach)[0]
    control = host._unique(plan.control_name,"transform")
    subtract = host._unique(plan.auxiliary_name("subtract"),"transform")
    skin = ""
    for node in c.listHistory(mesh,pruneDagObjects=True) or []:
        if c.nodeType(node)=="skinCluster":skin=node
    if skin:
        try:c.reorderDeformers(skin,deformer,mesh)
        except RuntimeError:pass
    c.addAttr(control,longName="advPyClusterAttachmentVertex",attributeType="long")
    c.setAttr(control + ".advPyClusterAttachmentVertex",int(strongest.rsplit("[",1)[1][:-1]),lock=True)
    _metadata(host,c,plan,control,deformer,parent,count,(group,attach,offset,subtract,control))
