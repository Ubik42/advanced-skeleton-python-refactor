"""MEL 80408–80460 and 80489–80492: native IKX placement and parenting."""


def create(host,spec):
    host._require_transaction()
    c=host._cmds
    c.select(clear=True)
    joint=c.joint(name=spec.name)
    c.setAttr(joint+'.drawStyle',2)
    c.setAttr(joint+'.segmentScaleCompensate',False)
    c.setAttr(joint+'.rotateOrder',spec.rotation_order)
    position=c.xform(spec.source_joint,query=True,worldSpace=True,translation=True)
    rotation=c.xform(spec.source_joint,query=True,worldSpace=True,rotation=True)
    c.xform(joint,worldSpace=True,translation=position,rotation=rotation)
    joint=c.parent(joint,spec.parent_path,absolute=True)[0]
    if c.nodeType(spec.parent_path)=='joint':
        # MEL explicitly corrects the small rotation change introduced by
        # parenting before freezing JO. Axis reconstruction omits this step.
        constraint=c.orientConstraint(spec.source_joint,joint)[0]
        c.delete(constraint)
    c.makeIdentity(joint,apply=True,rotate=True)
    host._transaction_changed=True
    return (c.ls(joint,long=True) or [joint])[0]
