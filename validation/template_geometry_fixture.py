"""Native template geometry snapshots used for source comparisons."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'validation/results/original-bendy-reference/original-bendy-reference.mb'

def sample(group):
    from maya import cmds as c
    from maya.api import OpenMaya as om,OpenMayaAnim as oma
    rows={}
    for shape in c.listRelatives(group,allDescendents=True,type='mesh',fullPath=True) or []:
        if c.getAttr(shape+'.intermediateObject'):continue
        mesh=c.listRelatives(shape,parent=True,fullPath=True)[0]
        path=om.MSelectionList().add(shape).getDagPath(0);fn=om.MFnMesh(path)
        shaders,slots=fn.getConnectedShaders(path.instanceNumber());names=[om.MFnDependencyNode(shader).name() for shader in shaders]
        skins=[node for node in c.listHistory(mesh) or [] if c.nodeType(node)=='skinCluster']
        skin=skins[-1] if skins else None
        row={'points':c.xform(mesh+'.vtx[*]',q=True,ws=True,t=True),
            'faces':[list(fn.getPolygonVertices(i)) for i in range(fn.numPolygons)],
            'normals':[list(n) for n in fn.getNormals(om.MSpace.kObject)],
            'materials':[names[slot] if slot>=0 else None for slot in slots]}
        if skin:
            sf=oma.MFnSkinCluster(om.MSelectionList().add(skin).getDependNode(0))
            component=om.MFnSingleIndexedComponent();obj=component.create(om.MFn.kMeshVertComponent);component.addElements(range(fn.numVertices))
            weights,width=sf.getWeights(path,obj)
            row.update(influences=[dag.partialPathName().rsplit('|',1)[-1] for dag in sf.influenceObjects()],weights=list(weights),
                settings={attr:c.getAttr(skin+'.'+attr) for attr in ('maxInfluences','maintainMaxInfluences','normalizeWeights','skinningMethod')})
        rows[mesh.rsplit('|',1)[-1]]=row
    return rows

def setup(mode):
    from maya import cmds as c
    c.file(str(BASE),open=True,force=True,executeScriptNodes=False)
    c.softSelect(softSelectEnabled=True,softSelectDistance=5.,softSelectFalloff=0,softSelectCurve='0,1,2,1,0,2')
    if mode=='alternate_axes':
        for attribute in ('primaryAxis','secondaryAxis'):
            if not c.objExists('Main.'+attribute):c.addAttr('Main',longName=attribute,attributeType='enum',enumName='X:-X:Y:-Y:Z:-Z')
        c.setAttr('Main.primaryAxis',2);c.setAttr('Main.secondaryAxis',4)
    if mode=='retained_shader':
        c.shadingNode('lambert',name='shaderMannequin',asShader=True)
        c.sets(name='shaderMannequinSG',renderable=True,noSurfaceShader=True,empty=True)
    if mode=='generic_no_profile':
        for name,attributes,y in [('SourceExtra_R',{},11),('SourceFrontOnly_R',{'fat':1.4,'fatFront':.3},10),('SourceWidthOnly_R',{'fat':1.7,'fatWidth':.2},9)]:
            c.select(clear=True);joint=c.joint(name=name,position=(-9,y,1))
            c.joint(name=name[:-2]+'End_R',position=(-11,y,1))
            for attribute,value in attributes.items():
                c.addAttr(joint,longName=attribute,attributeType='double');c.setAttr(joint+'.'+attribute,value)
            c.parent(joint,'Root_M');c.sets(joint,edit=True,addElement='DeformSet')
    c.select(clear=True)

def poses(group):
    from maya import cmds as c
    rows=[]
    for name,plug,value in [('main_move','Main.translateX',2.),('main_scale','Main.scaleY',1.3),('shoulder','FKShoulder_R.rotateZ',25.),('elbow','FKElbow_R.rotateZ',35.),('ankle','FKAnkle_R.rotateZ',17.)]:
        old=c.getAttr(plug);c.setAttr(plug,value);rows.append({'name':name,'meshes':sample(group)});c.setAttr(plug,old)
    return rows
