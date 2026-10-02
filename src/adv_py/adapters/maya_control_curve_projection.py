"""Native curve-point projection of ADV 6.925 asProjectControlCurve.

The aim frame, -15 degree orbital offset, three-sample polyProjectCurve and
nearest nonnegative local Z hit are retained. No uniform-radius estimate or
mesh-diagonal clamp is substituted for the source operation.
"""
from adv_py.core.control_curve_projection import projection_factor,projection_cv_count
from adv_py.core.control_curves import ControlCurveValidationError


def project_control_curve(host,control,mesh):
    host._require_transaction()
    c=host._cmds
    shapes=c.listRelatives(control,children=True,type='nurbsCurve') or []
    if not shapes:
        return 0
    form=c.getAttr(control+'.form')
    spans=c.getAttr(control+'.spans')
    degree=c.getAttr(control+'.degree')
    count=projection_cv_count(form,spans,degree)
    host._transaction_changed=True
    # Returned names own the operation's temporary nodes. Source fixed names
    # are not used to delete unrelated objects in a shared character scene.
    group=c.createNode('transform',name='AdvPy_ControlProjectionTemp',skipSelect=True)
    projected=0
    try:
        frame=c.createNode('transform',name='asProjectTransform1',parent=group,skipSelect=True)
        target=c.createNode('transform',name='asProjectTransform2',parent=group,skipSelect=True)
        probe=c.createNode('transform',name='asProjectTransform3',parent=frame,skipSelect=True)
        position=c.xform(control,query=True,worldSpace=True,translation=True)
        c.xform(frame,worldSpace=True,translation=position)
        aim=c.aimConstraint(target,frame,aimVector=(0,0,1),upVector=(1,0,0),
            worldUpVector=(0,1,0),worldUpType='objectrotation',worldUpObject=control)[0]
        for index in range(count):
            cv=control+'.cv['+str(index)+']'
            local=tuple(c.getAttr(cv+'.'+axis+'Value') for axis in 'xyz')
            factor=projection_factor(control,index,local)
            if factor is None:
                continue
            point=c.xform(cv,query=True,worldSpace=True,translation=True)
            c.xform(target,worldSpace=True,translation=point)
            matrix=c.getAttr(frame+'.worldMatrix')
            c.xform(probe,worldSpace=True,translation=point)
            c.setAttr(aim+'.offsetY',-15.)
            start=c.xform(probe,query=True,worldSpace=True,translation=True)
            c.setAttr(aim+'.offsetY',0.)
            end=c.xform(probe,query=True,worldSpace=True,translation=True)
            scan=c.curve(name='asProjectCurve',degree=1,point=(start,end),knot=(0,1))
            c.parent(scan,group,absolute=True)
            projection=None
            try:
                result=c.polyProjectCurve(scan,mesh,constructionHistory=True,
                    direction=matrix[8:11],pointsOnEdges=False,curveSamples=3,automatic=False)
                projection=c.parent(result[0],group,absolute=True)[0]
                minimum=999.
                for curve in c.listRelatives(projection,children=True) or []:
                    if c.getAttr(curve+'.spans')==0:
                        continue
                    hit=c.xform(curve+'.cv[1]',query=True,worldSpace=True,translation=True)
                    c.xform(probe,worldSpace=True,translation=hit)
                    distance=c.getAttr(probe+'.translateZ')
                    if distance>=0 and distance<minimum:
                        minimum=distance
                if minimum==999.:
                    continue
                c.setAttr(probe+'.translate',0.,0.,minimum*factor,type='double3')
                point=c.xform(probe,query=True,worldSpace=True,translation=True)
                c.xform(cv,worldSpace=True,translation=point)
                projected+=1
            finally:
                remove=[node for node in (projection,scan) if node and c.objExists(node)]
                if remove:c.delete(remove)
    finally:
        if c.objExists(group):c.delete(group)
    return projected


def project_control_curves(host,controls,mesh,*,strict=True):
    c=host._cmds
    if not mesh or not c.objExists(mesh):
        raise ControlCurveValidationError('请先选择有效的 Skin 网格')
    # Resolve every requested control before the first write, preserving the
    # application's existing strict/non-strict selection boundary.
    eligible=tuple(control for requested in controls
                   for control,shapes in (host._control_curve_shapes(requested,strict=strict),)
                   if control and shapes)
    before=host.capture_control_curves(eligible,strict=True) if eligible else ()
    raw=getattr(c,'raw',c)
    selection=raw.ls(selection=True,long=True) or []
    projected=0
    try:
        for state in before:
            projected+=project_control_curve(host,state.control,mesh)
            raw.select(clear=True)
            raw.refresh()
    finally:
        available=[node for node in selection if raw.objExists(node)]
        raw.select(available,replace=True) if available else raw.select(clear=True)
    return before,projected
