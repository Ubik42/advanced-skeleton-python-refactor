"""Literal FK asFollowLevels (MEL 74359–74542), including non-OPM TRS."""


def _matrix(value):
    if len(value)==1 and isinstance(value[0],(tuple,list)):value=value[0]
    return tuple(value)


def create(host,spec):
    c=host._cmds
    host._transaction_changed=True
    # Advanced FollowSpaces removes the existing receiver before reading m1.
    plug=spec.fk_offset+('.offsetParentMatrix' if spec.use_offset_parent_matrix else '.translateX')
    old=c.listConnections(plug,source=True,destination=False) or []
    if old:c.delete(old[0])
    bind=_matrix(c.xform(spec.fk_offset,query=True,worldSpace=True,matrix=True))
    blend=c.createNode('blendMatrix',name=spec.blend_node)
    c.setAttr(blend+'.inputMatrix',*bind,type='matrix')
    for index,target in enumerate(spec.targets):
        matrix=c.createNode('multMatrix',name=target.matrix_node)
        c.setAttr(matrix+'.matrixIn[0]',*bind,type='matrix')
        inverse=_matrix(c.getAttr(target.source+'.worldInverseMatrix[0]'))
        c.setAttr(matrix+'.matrixIn[1]',*inverse,type='matrix')
        c.connectAttr(target.source+'.worldMatrix[0]',matrix+'.matrixIn[2]')
        c.connectAttr(matrix+'.matrixSum',blend+f'.target[{index}].targetMatrix')
        attr='follow'+target.label
        c.addAttr(spec.fk_control,longName=attr,attributeType='double',minValue=0,maxValue=10,defaultValue=0,keyable=True)
        c.createNode('multDoubleLinear',name=target.weight_node)
        c.connectAttr(spec.fk_control+'.'+attr,target.weight_node+'.input1')
        c.setAttr(target.weight_node+'.input2',.1)
        c.connectAttr(target.weight_node+'.output',blend+f'.target[{index}].weight')
    c.setAttr(spec.fk_control+'.followParent',10.)
    if spec.use_offset_parent_matrix:
        c.connectAttr(blend+'.outputMatrix',spec.fk_offset+'.offsetParentMatrix')
    else:
        c.createNode('decomposeMatrix',name=spec.output_node)
        c.setAttr(spec.output_node+'.inputRotateOrder',c.getAttr(spec.fk_offset+'.rotateOrder'))
        c.connectAttr(blend+'.outputMatrix',spec.output_node+'.inputMatrix')
        for kind in ('Translate','Rotate','Scale'):
            for axis in 'XYZ':
                c.connectAttr(spec.output_node+'.output'+kind+axis,spec.fk_offset+'.'+kind.lower()+axis)
        for axis,component in zip('XYZ',('XY','XZ','YZ')):
            c.connectAttr(spec.output_node+'.outputShear'+axis,spec.fk_offset+'.shear'+component)
    # Source connects its world matrix directly, then zeros local T/R.
    # Adding a parent inverse would change the original non-OPM behavior.
    c.xform(spec.fk_offset,objectSpace=True,translation=(0.,0.,0.),rotation=(0.,0.,0.))


def capture(host,spec):
    c=host._cmds
    if c.nodeType(spec.blend_node)!='blendMatrix':return False
    bind=_matrix(c.getAttr(spec.blend_node+'.inputMatrix'))
    links=[]
    for index,target in enumerate(spec.targets):
        if c.nodeType(target.matrix_node)!='multMatrix' or c.nodeType(target.weight_node)!='multDoubleLinear':return False
        if _matrix(c.getAttr(target.matrix_node+'.matrixIn[0]'))!=bind:return False
        if abs(c.getAttr(target.weight_node+'.input2')-.1)>1e-8:return False
        if c.getAttr(spec.fk_control+'.follow'+target.label)!=(10. if target.label=='Parent' else 0.):return False
        links.extend(((target.source+'.worldMatrix[0]',target.matrix_node+'.matrixIn[2]'),
            (target.matrix_node+'.matrixSum',spec.blend_node+f'.target[{index}].targetMatrix'),
            (spec.fk_control+'.follow'+target.label,target.weight_node+'.input1'),
            (target.weight_node+'.output',spec.blend_node+f'.target[{index}].weight')))
    if spec.use_offset_parent_matrix:
        links.append((spec.blend_node+'.outputMatrix',spec.fk_offset+'.offsetParentMatrix'))
    else:
        if c.nodeType(spec.output_node)!='decomposeMatrix':return False
        if c.getAttr(spec.output_node+'.inputRotateOrder')!=c.getAttr(spec.fk_offset+'.rotateOrder'):return False
        links.append((spec.blend_node+'.outputMatrix',spec.output_node+'.inputMatrix'))
        for kind in ('Translate','Rotate','Scale'):
            for axis in 'XYZ':links.append((spec.output_node+'.output'+kind+axis,spec.fk_offset+'.'+kind.lower()+axis))
        for axis,component in zip('XYZ',('XY','XZ','YZ')):
            links.append((spec.output_node+'.outputShear'+axis,spec.fk_offset+'.shear'+component))
    return all(c.isConnected(a,b,ignoreUnitConversion=True) for a,b in links)
