"""Feed reverse-foot orientation through the existing source IK end matrix."""


def validate_orientation(host,spec):
    c=host._cmds
    return (c.objExists(spec.source_end_matrix)
        and c.nodeType(spec.source_end_matrix)=='multMatrix'
        and c.objExists(spec.ankle_constraint_name)
        and c.nodeType(spec.ankle_constraint_name)=='decomposeMatrix'
        and c.isConnected(spec.source_end_receiver+'.worldMatrix[0]',
                          spec.source_end_matrix+'.matrixIn[0]')
        and c.isConnected(spec.source_end_matrix+'.matrixSum',
                          spec.ankle_constraint_name+'.inputMatrix')
        and c.isConnected(spec.ankle_constraint_name+'.outputRotate',
                          spec.ankle_driver_path+'.rotate'))


def connect_orientation(host,spec):
    from maya.api import OpenMaya as om
    c=host._cmds
    rest=om.MMatrix(c.xform(spec.source_end_receiver,query=True,worldSpace=True,matrix=True))
    source=om.MMatrix(c.xform(spec.ankle_orientation_source_path,query=True,worldSpace=True,matrix=True))
    matrix=c.createNode('multMatrix',name=spec.source_end_world_matrix,skipSelect=True)
    c.setAttr(matrix+'.matrixIn[0]',*tuple(rest*source.inverse()),type='matrix')
    c.connectAttr(spec.ankle_orientation_source_path+'.worldMatrix[0]',matrix+'.matrixIn[1]')
    c.connectAttr(matrix+'.matrixSum',spec.source_end_matrix+'.matrixIn[0]',force=True)


def capture_orientation(host,spec):
    c=host._cmds
    edges=((spec.ankle_orientation_source_path+'.worldMatrix[0]',spec.source_end_world_matrix+'.matrixIn[1]'),
           (spec.source_end_world_matrix+'.matrixSum',spec.source_end_matrix+'.matrixIn[0]'),
           (spec.source_end_matrix+'.matrixSum',spec.ankle_constraint_name+'.inputMatrix'),
           (spec.ankle_constraint_name+'.outputRotate',spec.ankle_driver_path+'.rotate'))
    if any(not c.isConnected(source,target) for source,target in edges):
        return None,None,None
    return spec.ankle_constraint_name,spec.ankle_orientation_source_path,spec.ankle_driver_path
