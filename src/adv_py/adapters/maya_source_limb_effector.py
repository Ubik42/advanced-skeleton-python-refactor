"""MEL 80802–80806: deterministic hidden effector and Fit rotation order."""
from adv_py.core.character_registry import CharacterRegistryError


def configure(host,spec,handle,effector):
    host._require_transaction();c=host._cmds
    effector=c.rename(effector,spec.source_effector_name)
    c.setAttr(effector+'.rotateOrder',spec.source_rotation_order)
    for node in (handle,effector):c.setAttr(node+'.visibility',False,lock=True)
    c.addAttr(handle,longName='advPySourceIkEffector',attributeType='message')
    c.connectAttr(effector+'.message',handle+'.advPySourceIkEffector')
    c.setAttr(handle+'.advPySourceIkEffector',lock=True)
    c.addAttr(handle,longName='advPySourceIkEffectorOrder',attributeType='long',minValue=0,maxValue=5)
    c.setAttr(handle+'.advPySourceIkEffectorOrder',spec.source_rotation_order,lock=True)
    host._transaction_changed=True


def audit_registered(host,registration):
    c=host._cmds;owned={node.path for node in registration.nodes}
    for node in registration.nodes:
        marker=node.path+'.advPySourceIkEffector'
        if not c.objExists(marker):continue
        effectors=c.listConnections(marker,source=True,destination=False,type='ikEffector') or []
        paths=c.ls(effectors,long=True,type='ikEffector') or []
        order=node.path+'.advPySourceIkEffectorOrder'
        if (node.node_type!='ikHandle' or len(paths)!=1 or paths[0] not in owned
                or not c.objExists(order)
                or not c.getAttr(marker,lock=True) or not c.getAttr(order,lock=True)
                or c.connectionInfo(order,isDestination=True)
                or c.getAttr(paths[0]+'.rotateOrder')!=c.getAttr(order)
                or not c.isConnected(paths[0]+'.message',marker)
                or not c.isConnected(paths[0]+'.handlePath[0]',node.path+'.endEffector')
                or any(c.getAttr(path+'.visibility') or not c.getAttr(path+'.visibility',lock=True)
                       for path in (node.path,paths[0]))):
            raise CharacterRegistryError('来源 IK Effector 身份、旋转顺序或显示变化：'+node.path)
