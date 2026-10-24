"""Source four-finger detection, topology growth and nCloth straightening."""
from contextlib import nullcontext
from adv_py.core.fit_auto_place import FIT_AUTO_PLACE_FINGERS,source_fit_finger_force
from .maya_fit_auto_place_mesh import faces,invert,cast
from .maya_fit_auto_place_guides import stock_wrap


def project(s,skin,automatic=False,*,refresh=False,read_hits=True):
    c=s.c
    if c.objExists('asFitScanPolyProjectionCurves'):c.delete('asFitScanPolyProjectionCurves')
    result=c.polyProjectCurve('asFitScanCurve',skin,constructionHistory=True,direction=s.direction,
                             pointsOnEdges=False,curveSamples=50,automatic=automatic)
    c.rename(result[0],'asFitScanPolyProjectionCurves')
    c.parent('asFitScanPolyProjectionCurves','asFitScanCurves',absolute=True)
    # Source main loop refreshes before querying the generated children.
    # A history projection can change its output count during evaluation.
    if refresh:c.refresh()
    if read_hits:
        s.projected=c.listRelatives('asFitScanPolyProjectionCurves',children=True,type='transform') or []
        s.hits=len(c.listRelatives(s.projected,children=True) or []) if s.projected else 0


def _selected_vertices(c):
    return c.ls(selection=True, flatten=True) or []


def _selection_box(c):
    return c.xform(query=True, worldSpace=True, boundingBox=True)


def _center(box):
    return tuple((box[i]+box[i+3])/2. for i in range(3))


def _closest_upper_vertex(c):
    index=c.getAttr('closestSampler.closestVertexIndex')
    return 'CombinedSkinUpper_M.vtx['+str(index)+']'


def _check_four_finger_interval(s):
    """Retain the source's forward probe, including its unused half-way result."""
    c=s.c
    for step in range(1,199):
        agent=c.duplicate('asFitScanCurve',name='asFitScanCurveAgent')[0]
        c.move(0,0,s.step_z/10.*step,agent,relative=True,
               objectSpace=True,worldSpaceDistance=True)
        result=c.polyProjectCurve(agent,s.project_on,constructionHistory=True,
            direction=s.direction,pointsOnEdges=False,curveSamples=50,automatic=False)
        projection=c.rename(result[0],'asFitScanPolyProjectionCurvesAgent')
        hits=len(c.listRelatives(projection,children=True) or [])
        c.delete(agent,projection)
        if hits!=4:
            break


def _remove_sampled_nail_shell(c):
    """Source 52622: a shell that cannot grow to the wrist is removed."""
    c.select(_closest_upper_vertex(c),replace=True)
    for _ in range(199):
        before=_selected_vertices(c)
        box=_selection_box(c)
        c.polySelectConstraint(pp=1,type=1)
        if len(_selected_vertices(c))==len(before):
            break
        box=_selection_box(c)
        if box[3]>c.getAttr('asFitHandleWrist.translateX'):
            break
    if c.getAttr('asFitHandleWrist.translateX')>box[3]:
        faces(c)
        c.delete(c.ls(selection=True))


def _find_finger_tip(c,finger):
    # Re-query after shell deletion because Maya renumbers the vertices.
    c.select(_closest_upper_vertex(c),replace=True)
    for _ in range(199):
        before=_selection_box(c)
        c.polySelectConstraint(pp=1,type=1)
        after=_selection_box(c)
        if after[0]<before[0]:
            continue
        minimum_x=999.
        for vertex in _selected_vertices(c):
            point=c.xform(vertex,query=True,worldSpace=True,translation=True)
            if point[0]<minimum_x:
                minimum_x=point[0]
                c.select(vertex,replace=True)
        break
    selected=_selected_vertices(c)
    point=c.xform(query=True,worldSpace=True,translation=True)[:3]
    tip='asFitPivot'+finger+'Finger4'
    c.createNode('transform',name=tip,parent='asFitPivotsFingers',skipSelect=True)
    c.xform(tip,worldSpace=True,translation=point)
    c.select(selected,replace=True)


def _grow_finger_curve(s,finger):
    """Keep averageDiam, prevBB and fingerGrowFail at procedure scope."""
    c=s.c
    points=[]
    for ring_index in range(199):
        before=_selected_vertices(c)
        c.polySelectConstraint(pp=1,type=1)
        grown=_selected_vertices(c)
        c.select(before,deselect=True)
        if not c.ls(selection=True):
            s.finger_grow_failed=True
            break
        box=_selection_box(c)
        diameter=(box[5]-box[2])/2.
        if ring_index==4:
            s.average_finger_diameter=diameter
        knuckle=(ring_index>3 and diameter>s.average_finger_diameter*2.)
        if knuckle:
            node='asFitPivot'+finger+'Finger1'
            c.createNode('transform',name=node,parent='asFitPivotsFingers',skipSelect=True)
            c.xform(node,worldSpace=True,translation=_center(s.previous_finger_box))
        else:
            points.append(_center(box))
        s.previous_finger_box=box
        c.select(grown,replace=True)
        if knuckle:
            break
    # MEL ignores the creation result, then addresses the requested name.
    # A retry can therefore hit an ambiguous name; using the returned path
    # silently bypasses that source behavior and changes the scan outcome.
    curve='FingerCurve'+finger
    c.curve(degree=1,name=curve,point=points)
    c.parent(curve,'asFitPivotsFingers',absolute=True)


def _sample_finger(s,finger,projection_index):
    c=s.c
    # Source retries do not delete earlier sampled curves/pivots. Let native
    # creation and name resolution retain the reference's actual behavior.
    curve='polyProjectionCurve1_'+str(projection_index+1)
    minimum=c.getAttr(curve+'.boundingBoxMin')[0]
    maximum=c.getAttr(curve+'.boundingBoxMax')[0]
    s.max_finger_width=max(s.max_finger_width,maximum[2]-minimum[2])
    point=tuple((a+b)/2. for a,b in zip(minimum,maximum))
    c.setAttr('closestSampler.inPosition',*point,type='double3')
    _remove_sampled_nail_shell(c)
    _find_finger_tip(c,finger)
    _grow_finger_curve(s,finger)


def detect_fingers(s):
    if s.axis!='y' or s.four_fingers or s.hits!=4:
        return
    s.host._require_transaction()
    s.host._transaction_changed=True
    project(s,'CombinedSkinUpper_M')
    if s.hits!=4:
        return
    _check_four_finger_interval(s)
    # Source automatic re-projection leaves numHits / projectedCurves alone.
    project(s,'CombinedSkinUpper_M',True,read_hits=False)
    for projection_index,finger in enumerate(FIT_AUTO_PLACE_FINGERS):
        _sample_finger(s,finger,projection_index)
    s.c.setAttr('AutoPlacing.fingerWidth',s.max_finger_width)
    if not s.finger_grow_failed:
        s.four_fingers=True


def stock_selected(host,command):
    from maya import mel
    c=host._cmds
    with c._creation_namespace() if hasattr(c,'_creation_namespace') else nullcontext():
        return mel.eval(command)


def straighten_fingers(s):
    if not s.four_fingers or s.has_ncloth:return
    s.host._require_transaction();s.host._transaction_changed=True
    from .maya_fit_auto_place_nucleus import temporary_nucleus
    with temporary_nucleus(s.host) as nucleus:
        s.nucleus=nucleus
        _straighten_fingers(s)


def _straighten_fingers(s):
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
        for _ in range(99):
            c.polySelectConstraint(pp=1,type=1)
            expanded=c.ls(selection=True,flatten=True) or []
            if mesh+'.vtx['+str(base_index)+']' in expanded:break
            s.previous_finger_selection=c.ls(selection=True) or []
        finger_vertices=c.ls(selection=True) or [];c.select(s.previous_finger_selection,deselect=True)
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
        force=source_fit_finger_force(c.getAttr(converge+'.rotateY'))
        c.setAttr(cloth+'.localForce',*force,type='float3')
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
    # ADV calls Maya's stock binding operation on this exact selection, then
    # transfers by the selected geometries. Preserve its shape discovery and
    # selection behavior instead of specifying guessed source/destination SCs.
    c.select('asFitShoulderStraightBase','asFitShoulderStraight','asFitElbowStraight','fingerStraight',replace=True)
    stock_selected(host,'newSkinCluster "-toSelectedBones -mi 3 -dr 4 -rui false";')
    c.select('CombinedSkinUpper_M','fingerStraight',replace=True)
    c.copySkinWeights(noMirror=True,surfaceAssociation='closestPoint',influenceAssociation='closestJoint')
    shoulder=c.getAttr('asFitShoulderStraight.rotate')[0];elbow=c.getAttr('asFitElbowStraight.rotate')[0]
    c.setAttr('asFitShoulderStraight.rotate',0,0,0,type='float3');c.setAttr('asFitElbowStraight.rotate',0,0,0,type='float3')
    c.blendShape('fingerStraight','CombinedSkinUpper_M',name='straightenBS',frontOfChain=True,origin='world',weight=(0,1.))
    c.setAttr('asFitShoulderStraight.rotate',*shoulder,type='float3');c.setAttr('asFitElbowStraight.rotate',*elbow,type='float3')
    c.delete('fingerStraight');s.has_ncloth=True
    children=c.listRelatives('asFitPivotsFingers',children=True) or []
    if children:c.delete(children)
    s.four_fingers=False;s.minimum_x=c.getAttr('CombinedSkinUpper_M.boundingBoxMinX')
    c.setAttr('AutoPlacing.bbMinX',s.minimum_x)
    c.setAttr('asFitScanCurve.translate',s.minimum_x,s.maximum_y,0,type='float3');s.index=0
