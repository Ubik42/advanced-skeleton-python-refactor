"""Shared source fixtures and geometry sampling for Boolean/Warp/CutUp."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'validation/results/original-geometry-reference/boxes.mb'


def setup_fixture(kind, *, base=BASE):
    from maya import cmds as c
    c.file(str(base),open=True,force=True,executeScriptNodes=False)
    keep={'RootBox_M','ShoulderBox_R','ElbowBox_R','HeadBox_M'}
    for holder in (c.listRelatives('BoxesGeometry',children=True) or []) if c.objExists('BoxesGeometry') else []:
        meshes=[node for node in c.listRelatives(holder,children=True) or [] if c.listRelatives(node,shapes=True,noIntermediate=True,type='mesh')]
        if not any(node in keep for node in meshes):c.delete(holder)
    # This fixture records the tool settings rather than changing source procs.
    c.softSelect(softSelectEnabled=True,softSelectDistance=5.,softSelectFalloff=0,softSelectCurve='0,1,2,1,0,2')
    for name,color in [('SourceGreen',(0.1,.8,.2)),('SourceBlue',(.1,.2,.9))]:
        c.shadingNode('lambert',name=name,asShader=True);c.setAttr(name+'.color',*color,type='double3')
        c.sets(name=name+'SG',renderable=True,noSurfaceShader=True,empty=True);c.connectAttr(name+'.outColor',name+'SG.surfaceShader')
    if kind in ('boolean','warp'):
        source=c.polyCube(name='SourceGeometry',width=9.,height=18.,depth=2.5,constructionHistory=False)[0]
        c.setAttr(source+'.translate',.3,8.,.1,type='double3');c.setAttr(source+'.rotateY',12.)
        c.setAttr(source+'.scaleZ',1.1)
        c.sets(source,edit=True,forceElement='SourceGreenSG');c.sets(source+'.f[1:3]',edit=True,forceElement='SourceBlueSG')
    else:
        c.select(clear=True);c.joint(name='Auxiliary_R');c.parent('Auxiliary_R','ElbowPart1_R',relative=True)
        source=c.polyPlane(name='SourceGeometry',width=4.,height=2.,subdivisionsX=2,subdivisionsY=1,constructionHistory=False)[0]
        c.setAttr(source+'.translate',-3.,12.,.5,type='double3');c.setAttr(source+'.rotateZ',23.)
        c.sets(source,edit=True,forceElement='SourceGreenSG');c.sets(source+'.f[1]',edit=True,forceElement='SourceBlueSG')
        skin=c.skinCluster('Shoulder_R','Elbow_R','Auxiliary_R',source,toSelectedBones=True,maximumInfluences=3,dropoffRate=4)[0]
        c.skinPercent(skin,source+'.vtx[*]',transformValue=[('Shoulder_R',1.),('Elbow_R',0.),('Auxiliary_R',0.)])
        c.skinPercent(skin,source+'.vtx[4]',transformValue=[('Shoulder_R',.1),('Elbow_R',.9),('Auxiliary_R',0.)])
        c.skinPercent(skin,source+'.vtx[5]',transformValue=[('Shoulder_R',0.),('Elbow_R',0.),('Auxiliary_R',1.)])
        c.polyColorPerVertex(source+'.vtx[*]',rgb=(.2,.4,.6),colorDisplayOption=True)
    c.select(source,replace=True)
    return source


def snapshot(group):
    from maya import cmds as c
    from maya.api import OpenMaya as om
    rows={}
    for shape in c.listRelatives(group,allDescendents=True,type='mesh',fullPath=True) or []:
        if c.getAttr(shape+'.intermediateObject'):continue
        parent=c.listRelatives(shape,parent=True,fullPath=True)[0]
        path=om.MSelectionList().add(shape).getDagPath(0);fn=om.MFnMesh(path)
        shaders,assignments=fn.getConnectedShaders(path.instanceNumber())
        shader_names=[om.MFnDependencyNode(node).name() for node in shaders]
        rows[parent.rsplit('|',1)[-1]]={
            'points':c.xform(parent+'.vtx[*]',query=True,worldSpace=True,translation=True),
            'faces':[list(fn.getPolygonVertices(index)) for index in range(fn.numPolygons)],
            'materials':[shader_names[slot] if slot>=0 else None for slot in assignments],
            'uv_sets':list(fn.getUVSetNames()),
            'color_sets':list(fn.getColorSetNames()),
            'render':{name:c.getAttr(shape+'.'+name) for name in ('castsShadows','primaryVisibility','visibleInReflections')},
            'matrix':c.xform(parent,query=True,worldSpace=True,matrix=True)}
    return rows


def poses(group):
    from maya import cmds as c
    rows=[]
    for name,plug,value in [('main_move','Main.translateX',2.),('main_scale','Main.scaleY',1.3),
                             ('shoulder','FKShoulder_R.rotateZ',25.),('elbow','FKElbow_R.rotateZ',35.)]:
        old=c.getAttr(plug);c.setAttr(plug,value);rows.append({'name':name,'meshes':snapshot(group)})
        c.setAttr(plug,old)
    return rows
