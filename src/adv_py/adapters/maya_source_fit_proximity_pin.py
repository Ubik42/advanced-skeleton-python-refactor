"""MEL 84942–84984: uncorrected ProximityPin output and full matrix blend."""
from .maya_body_fit_proximity_pin import _matrix

def create(host,spec,state):
    c=host._cmds;plug=spec.receiver+'.offsetParentMatrix'
    if (c.connectionInfo(plug,sourceFromDestination=True) or None)!=state.receiver_opm_source:raise ValueError('Pin 原矩阵来源变化')
    if bool(c.getAttr(spec.receiver+'.inheritsTransform'))!=state.receiver_inherits_transform:raise ValueError('Pin 原变换继承状态变化')
    host._transaction_changed=True
    host._generate_body_proximity_pin(spec,state)
    blend=c.createNode('blendMatrix',name=spec.blend_matrix)
    c.connectAttr(spec.pin_node+'.outputMatrix[0]',blend+'.target[0].targetMatrix')
    c.connectAttr(spec.fk_offset+'.worldMatrix[0]',blend+'.inputMatrix')
    c.addAttr(spec.fk_control,longName='pin',attributeType='double',minValue=0,maxValue=10,defaultValue=10,keyable=True)
    weight=c.createNode('unitConversion',name=spec.weight_node)
    c.setAttr(weight+'.conversionFactor',.1)
    c.connectAttr(spec.fk_control+'.pin',weight+'.input');c.connectAttr(weight+'.output',blend+'.target[0].weight')
    delta=c.createNode('multMatrix',name=spec.delta_matrix)
    c.connectAttr(blend+'.outputMatrix',delta+'.matrixIn[0]');c.connectAttr(spec.fk_offset+'.worldInverseMatrix[0]',delta+'.matrixIn[1]')
    bridge=c.createNode('multMatrix',name=spec.receiver_matrix)
    if state.receiver_opm_source:
        c.connectAttr(state.receiver_opm_source,bridge+'.matrixIn[0]');c.disconnectAttr(state.receiver_opm_source,plug)
    else:c.setAttr(bridge+'.matrixIn[0]',*state.receiver_opm_value,type='matrix')
    c.connectAttr(delta+'.matrixSum',spec.input_transform+'.offsetParentMatrix',force=True)
    if state.receiver_inherits_transform:
        c.connectAttr(spec.input_transform+'.matrix',bridge+'.matrixIn[1]')
        c.connectAttr(delta+'.matrixSum',bridge+'.matrixIn[2]')
    c.connectAttr(bridge+'.matrixSum',plug)

def capture(host,spec,state):
    c=host._cmds
    kinds=((spec.pin_node,'proximityPin'),(spec.blend_matrix,'blendMatrix'),(spec.weight_node,'unitConversion'),(spec.delta_matrix,'multMatrix'),(spec.receiver_matrix,'multMatrix'),(spec.input_transform,'transform'))
    if any(not c.objExists(n) or c.nodeType(n)!=t for n,t in kinds) or c.objExists(spec.corrected_matrix):return False
    links=[(spec.pin_node+'.outputMatrix[0]',spec.blend_matrix+'.target[0].targetMatrix'),(spec.fk_offset+'.worldMatrix[0]',spec.blend_matrix+'.inputMatrix'),(spec.fk_control+'.pin',spec.weight_node+'.input'),(spec.weight_node+'.output',spec.blend_matrix+'.target[0].weight'),(spec.blend_matrix+'.outputMatrix',spec.delta_matrix+'.matrixIn[0]'),(spec.fk_offset+'.worldInverseMatrix[0]',spec.delta_matrix+'.matrixIn[1]'),(spec.delta_matrix+'.matrixSum',spec.input_transform+'.offsetParentMatrix'),(spec.receiver_matrix+'.matrixSum',spec.receiver+'.offsetParentMatrix')]
    if bool(c.getAttr(spec.receiver+'.inheritsTransform'))!=state.receiver_inherits_transform:return False
    if state.receiver_inherits_transform:
        links.extend(((spec.input_transform+'.matrix',spec.receiver_matrix+'.matrixIn[1]'),(spec.delta_matrix+'.matrixSum',spec.receiver_matrix+'.matrixIn[2]')))
    elif any(c.connectionInfo(spec.receiver_matrix+'.matrixIn['+str(i)+']',sourceFromDestination=True) for i in (1,2)):
        return False
    if state.receiver_opm_source:links.append((state.receiver_opm_source,spec.receiver_matrix+'.matrixIn[0]'))
    elif _matrix(c.getAttr(spec.receiver_matrix+'.matrixIn[0]'))!=state.receiver_opm_value:return False
    return (all(c.isConnected(a,b) for a,b in links)
        and all(abs(c.getAttr(spec.blend_matrix+'.target[0].'+attr)-1.)<1e-8 for attr in ('translateWeight','rotateWeight','scaleWeight','shearWeight'))
        and abs(c.getAttr(spec.weight_node+'.conversionFactor')-.1)<1e-8
        and all(c.getAttr(spec.pin_node+'.'+a)==0 for a in ('coordMode','normalAxis','relativeSpaceMode')))
