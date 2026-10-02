"""Source four-finger detection, topology growth and nCloth straightening."""
from contextlib import nullcontext
from math import sin,radians
from adv_py.core.fit_auto_place import FIT_AUTO_PLACE_FINGERS
from .maya_fit_auto_place_mesh import faces,invert,cast
from .maya_fit_auto_place_guides import stock_wrap


def project(s,skin,automatic=False):
    c=s.c
    if c.objExists('asFitScanPolyProjectionCurves'):c.delete('asFitScanPolyProjectionCurves')
    result=c.polyProjectCurve('asFitScanCurve',skin,constructionHistory=True,direction=s.direction,
                             pointsOnEdges=False,curveSamples=50,automatic=automatic)
    c.rename(result[0],'asFitScanPolyProjectionCurves')
    c.parent('asFitScanPolyProjectionCurves','asFitScanCurves',absolute=True)
    s.projected=c.listRelatives('asFitScanPolyProjectionCurves',children=True,type='transform') or []
    s.hits=len(c.listRelatives(s.projected,children=True) or []) if s.projected else 0


def detect_fingers(s):
    c=s.c
    if s.axis=='y' and not s.four_fingers and s.hits==4:project(s,'CombinedSkinUpper_M')
    if s.axis!='y' or s.four_fingers or s.hits!=4:return
    for index in range(1,199):
        agent=c.duplicate('asFitScanCurve',name='asFitScanCurveAgent')[0]
        c.move(0,0,s.step_z/10.*index,agent,relative=True,objectSpace=True,worldSpaceDistance=True)
        result=c.polyProjectCurve(agent,s.project_on,constructionHistory=True,direction=s.direction,
                                 pointsOnEdges=False,curveSamples=50,automatic=False)
        projection=c.rename(result[0],'asFitScanPolyProjectionCurvesAgent')
        hits=len(c.listRelatives(projection,children=True) or [])
        c.delete(agent,projection)
        if hits!=4:break
    project(s,'CombinedSkinUpper_M',True)
    for index,finger in enumerate(FIT_AUTO_PLACE_FINGERS):
        # Failed growth can retry on another scan slice. Keep one editable
        # curve / pair of pivots per finger, rather than letting Maya create
        # duplicate short names which make the original's next lookup fail.
        for name in ('FingerCurve'+finger,'asFitPivot'+finger+'Finger1','asFitPivot'+finger+'Finger4'):
            if c.objExists(name):c.delete(c.ls(name,long=True))
        curve='polyProjectionCurve1_'+str(index+1)
        minimum=c.getAttr(curve+'.boundingBoxMin')[0];maximum=c.getAttr(curve+'.boundingBoxMax')[0]
        s.max_finger_width=max(s.max_finger_width,maximum[2]-minimum[2])
        point=tuple((a+b)/2. for a,b in zip(minimum,maximum))
        c.setAttr('closestSampler.inPosition',*point,type='double3')
        def closest():return 'CombinedSkinUpper_M.vtx['+str(c.getAttr('closestSampler.closestVertexIndex'))+']'
        c.select(closest(),replace=True)
        for _ in range(199):
            before=c.ls(selection=True,flatten=True) or [];box=c.xform(query=True,worldSpace=True,boundingBox=True)
            c.polySelectConstraint(pp=1,type=1)
            if len(c.ls(selection=True,flatten=True) or [])==len(before):break
            box=c.xform(query=True,worldSpace=True,boundingBox=True)
            if box[3]>c.getAttr('asFitHandleWrist.translateX'):break
        if c.getAttr('asFitHandleWrist.translateX')>box[3]:
            faces(c);c.delete(c.ls(selection=True))
        c.select(closest(),replace=True)
        for _ in range(199):
            before=c.xform(query=True,worldSpace=True,boundingBox=True);c.polySelectConstraint(pp=1,type=1)
            after=c.xform(query=True,worldSpace=True,boundingBox=True)
            if not after[0]<before[0]:
                minimum_x=999.
                for vertex in c.ls(selection=True,flatten=True) or []:
                    point=c.xform(vertex,query=True,worldSpace=True,translation=True)
                    if point[0]<minimum_x:minimum_x=point[0];c.select(vertex,replace=True)
                break
        selected=c.ls(selection=True,flatten=True) or []
        point=c.xform(query=True,worldSpace=True,translation=True)[:3]
        tip=c.createNode('transform',name='asFitPivot'+finger+'Finger4',parent='asFitPivotsFingers',skipSelect=True)
        c.xform(tip,worldSpace=True,translation=point);c.select(selected,replace=True)
        points=[];average_diameter=0.;previous_box=(0,)*6
        for index in range(199):
            before=c.ls(selection=True,flatten=True) or [];c.polySelectConstraint(pp=1,type=1)
            grown=c.ls(selection=True,flatten=True) or [];c.select(before,deselect=True)
            if not c.ls(selection=True):s.finger_grow_failed=True;break
            box=c.xform(query=True,worldSpace=True,boundingBox=True);diameter=(box[5]-box[2])/2.
            if index==4:average_diameter=diameter
            knuckle=index>3 and diameter>average_diameter*2.
            if knuckle:
                node=c.createNode('transform',name='asFitPivot'+finger+'Finger1',parent='asFitPivotsFingers',skipSelect=True)
                c.xform(node,worldSpace=True,translation=tuple((previous_box[i]+previous_box[i+3])/2. for i in range(3)))
            else:points.append(tuple((box[i]+box[i+3])/2. for i in range(3)))
            previous_box=box;c.select(grown,replace=True)
            if knuckle:break
        curve=c.curve(degree=1,name='FingerCurve'+finger,point=points)
        c.parent(curve,'asFitPivotsFingers',absolute=True)
    c.setAttr('AutoPlacing.fingerWidth',s.max_finger_width)
    if not s.finger_grow_failed:s.four_fingers=True


def stock_selected(host,command):
    from maya import mel
    c=host._cmds
    with c._creation_namespace() if hasattr(c,'_creation_namespace') else nullcontext():
        return mel.eval(command)


def straighten_fingers(s):
    if not s.four_fingers or s.has_ncloth:return
    c=s.c;host=s.host;raw=getattr(c,'raw',c)
    def pos(node):return c.xform(node,query=True,worldSpace=True,translation=True)
    converge=c.createNode('transform',name='fingersConverge',parent='asFitPivots',skipSelect=True)
    c.pointConstraint('asFitPivotNeck',converge)
    for finger in FIT_AUTO_PLACE_FINGERS:c.pointConstraint('asFitPivot'+finger+'Finger1',converge)
    for finger in FIT_AUTO_PLACE_FINGERS:
        c.setAttr('closestSampler.inPosition',*pos('asFitPivot'+finger+'Finger1'),type='double3')
        base_index=c.getAttr('closestSampler.closestVertexIndex')
        c.setAttr('closestSampler.inPosition',*pos('asFitPivot'+finger+'Finger4'),type='double3')
        tip_index=c.getAttr('closestSampler.closestVertexIndex')
        mesh='CombinedSkin'+finger+'_R';c.duplicate('CombinedSkinUpper_M',name=mesh)
        c.parent(mesh,'asFitNCloth',absolute=True)
        c.select(mesh+'.vtx['+str(tip_index)+']',replace=True)
        previous=[]
        for _ in range(99):
            c.polySelectConstraint(pp=1,type=1)
            expanded=c.ls(selection=True,flatten=True) or []
            if mesh+'.vtx['+str(base_index)+']' in expanded:break
            previous=c.ls(selection=True) or []
        finger_vertices=c.ls(selection=True) or [];c.select(previous,deselect=True)
        edge_vertices=c.ls(selection=True,flatten=True) or []
        # Source tempSet preserves membership while deleting other faces;
        # component strings alone become stale when Maya renumbers vertices.
        edge_set=c.sets(edge_vertices,name='tempSet')
        c.select(finger_vertices,replace=True);faces(c,contained=True);invert(c);c.delete(c.ls(selection=True))
        c.select(mesh,replace=True)
        nucleus_before=set(raw.ls(type='nucleus') or [])
        shapes=stock_selected(host,'createNCloth 0;')
        cloth=c.listRelatives(shapes[0],parent=True)[0];cloth=c.rename(cloth,'nCloth'+finger)
        c.parent(cloth,'asFitNCloth',absolute=True)
        edge_vertices=c.sets(edge_set,query=True) or []
        c.select(cast(edge_vertices,mesh),replace=True)
        constraints=stock_selected(host,'createNConstraint transform 0;')
        parent=c.listRelatives(constraints[0],parent=True)[0];c.parent(parent,'asFitNCloth',absolute=True)
        c.delete(edge_set)
        for attr,value in (('collide',0),('selfCollide',0),('stretchResistance',40),
            ('compressionResistance',20),('bendResistance',.2),('bendAngleDropoff',.6),
            ('pointMass',.15),('tangentialDrag',.4),('damp',2),('ignoreSolverGravity',1)):
            c.setAttr(cloth+'.'+attr,value)
        c.delete(c.aimConstraint('asFitPivot'+finger+'Finger1',converge,offset=(0,0,0),weight=1.,
            aimVector=(-1,0,0),upVector=(0,1,0),worldUpType='scene'))
        angle=sin(radians(c.getAttr(converge+'.rotateY')))
        c.setAttr(cloth+'.localForce',-98.*(1.-angle),0,98.*angle,type='double3')
        created=set(raw.ls(type='nucleus') or [])-nucleus_before
        if created:s.nucleus=next(iter(created))
        elif not s.nucleus:
            connected=raw.listConnections(host.scene_address(cloth),type='nucleus') or []
            if connected:s.nucleus=connected[0]
    nucleus=c.rename(s.nucleus,'asFitNucleus');c.parent(nucleus,'asFitNCloth',absolute=True)
    c.setAttr(nucleus+'.spaceScale',160./s.maximum_y)
    wrap=stock_wrap(host,'CombinedSkinUpper_M','CombinedSkinIndex_R',
        '{ "1","0","0.1", "1", "0", "0", "1", "0" }')
    wrap=c.rename(wrap,'CombinedSkinUpperWrap_M')
    for finger in FIT_AUTO_PLACE_FINGERS[1:]:
        c.select('CombinedSkinUpper_M','CombinedSkin'+finger+'_R',replace=True)
        stock_selected(host,'AddWrapInfluence;')
    c.setAttr('asFitNCloth.visibility',False)
    for _ in range(40):s.orbit();c.currentTime(2);c.currentTime(3)
    c.setAttr('asFitDeltaMush.envelope',0.)
    c.duplicate('CombinedSkinUpper_M',name='fingerStraight')
    c.delete(wrap,'asFitNCloth');c.setAttr('asFitDeltaMush.envelope',1.)
    target=c.skinCluster(('asFitShoulderStraightBase','asFitShoulderStraight','asFitElbowStraight'),'fingerStraight',
        toSelectedBones=True,maximumInfluences=3,dropoffRate=4,removeUnusedInfluence=False)[0]
    c.copySkinWeights(sourceSkin='CombinedSkinUpperSC_M',destinationSkin=target,noMirror=True,
                      surfaceAssociation='closestPoint',influenceAssociation='closestJoint')
    shoulder=c.getAttr('asFitShoulderStraight.rotate')[0];elbow=c.getAttr('asFitElbowStraight.rotate')[0]
    c.setAttr('asFitShoulderStraight.rotate',0,0,0,type='double3');c.setAttr('asFitElbowStraight.rotate',0,0,0,type='double3')
    c.blendShape('fingerStraight','CombinedSkinUpper_M',name='straightenBS',frontOfChain=True,origin='world',weight=(0,1.))
    c.setAttr('asFitShoulderStraight.rotate',*shoulder,type='double3');c.setAttr('asFitElbowStraight.rotate',*elbow,type='double3')
    c.delete('fingerStraight');s.has_ncloth=True
    children=c.listRelatives('asFitPivotsFingers',children=True) or []
    if children:c.delete(children)
    s.four_fingers=False;s.minimum_x=c.getAttr('CombinedSkinUpper_M.boundingBoxMinX')
    c.setAttr('AutoPlacing.bbMinX',s.minimum_x)
    c.setAttr('asFitScanCurve.translate',s.minimum_x,s.maximum_y,0,type='double3');s.index=0
