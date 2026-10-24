"""asMirrorControlCurves' Body/Face curve and surface branches (57463)."""
from fnmatch import fnmatchcase
from .maya_original_control_identity import leaf,source_control_name,source_control_from_role


def mirror_source_control_curves(host, left_to_right=False, set_name='ControlSet', *, controls=None):
    host._require_transaction()
    if set_name not in ('ControlSet','FaceControlSet'):
        raise ValueError('Body／Face 曲线镜像需要对应原版控制集')
    if not host.confirm_original_control_build_pose():return ()
    c = host._cmds
    selected = tuple(c.ls(selection=True,long=True) or ())
    members = tuple(c.sets(set_name,query=True) or ()) if controls is None else tuple(controls)
    source_marker,target_marker = ('_L','_R') if left_to_right else ('_R','_L')
    mirrored = []
    try:
        for control in members:
            shapes = tuple(c.listRelatives(control,shapes=True) or ())
            if not shapes:continue
            shape = shapes[0]
            kind = c.nodeType(shape)
            if kind not in ('nurbsCurve','nurbsSurface'):continue
            if not fnmatchcase(leaf(shape),'*'+source_marker+'*'):continue
            if set_name=='FaceControlSet' and leaf(shape).startswith('ctrl'):continue
            opposite_shape = shape.replace(source_marker,target_marker,1)
            role = source_control_name(host,control)
            opposite_control = source_control_from_role(host,role.replace(source_marker,target_marker,1))
            if not c.objExists(opposite_shape):continue
            host._transaction_changed = True
            if kind=='nurbsSurface':
                c.select(shape+'.cv[0:999][0:999]',replace=True)
                for component in c.ls(selection=True,flatten=True) or ():
                    node,separator,suffix = component.partition('.')
                    if c.nodeType(node)=='transform':component=shape+separator+suffix
                    position = c.xform(component,query=True,worldSpace=True,translation=True)
                    c.xform(component.replace(shape,opposite_shape,1),worldSpace=True,
                            translation=(-position[0],position[1],position[2]))
                if (c.attributeQuery('softModControl',node=control,exists=True)
                        or c.attributeQuery('clusterControl',node=control,exists=True)):
                    c.reverseSurface(opposite_shape,direction=0,constructionHistory=False,replaceOriginal=True)
                mirrored.append(opposite_control)
                continue
            form = c.getAttr(shape+'.form')
            spans = c.getAttr(shape+'.spans')
            degree = c.getAttr(shape+'.degree')
            count = spans if form==2 else spans+degree
            # Native deliberately includes the seam CV beyond numCv-1.
            for index in range(count+1):
                position = c.xform(shape+'.cv['+str(index)+']',query=True,
                                   worldSpace=True,translation=True)
                c.xform(opposite_shape+'.cv['+str(index)+']',worldSpace=True,
                        translation=(-position[0],position[1],position[2]))
            base = role.split('_')[0]
            if c.objExists(base+'_NonSymmetry'):
                if c.objExists('tempXform'):c.delete('tempXform')
                temporary = c.createNode('transform',name='tempXform',parent=control)
                try:
                    temporary = c.parent(temporary,base)[0]
                    temporary = c.parent(temporary,base+'_NonSymmetry',relative=True)[0]
                    for axis in 'xyz':
                        plug = temporary+'.t'+axis
                        c.setAttr(plug,-c.getAttr(plug))
                    matrix = c.xform(temporary,query=True,worldSpace=True,matrix=True)
                    c.xform(opposite_control,worldSpace=True,matrix=matrix)
                finally:
                    c.delete(temporary)
                for index in range(count+1):
                    for axis in 'xyz':
                        attribute = '.cv['+str(index)+'].'+axis+'Value'
                        c.setAttr(opposite_shape+attribute,c.getAttr(shape+attribute))
            mirrored.append(opposite_control)
    finally:
        surviving = tuple(node for node in selected if c.objExists(node))
        c.select(surviving,replace=True) if surviving else c.select(clear=True)
    return tuple(mirrored)
