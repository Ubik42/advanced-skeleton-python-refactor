"""Native inherited-scale FK receivers and their parent FKX compensation."""
from adv_py.core.character_registry import CharacterRegistryError

MARKER = 'advPySourceFkFollowerParentScale'
SOURCE = 'advPySourceFkFollowerParentJoint'


def configure(host, plan, driver_by_body):
    host._require_transaction()
    c = host._cmds
    controls = {control.driven_joint: control for control in plan.controls}
    for follower in plan.followers:
        if follower.use_offset_parent_matrix or not follower.inherit_scale:
            continue
        body = follower.scale_source_body_joint or follower.source_body_joint
        control = controls.get(driver_by_body.get(body, body))
        if control is None or not control.source_override_joint:
            continue
        parent = control.source_override_path
        if not parent or c.nodeType(parent) != 'joint':
            raise CharacterRegistryError('来源 FK 跟随父级不是 FKX 关节')
        # This applies even when the child control is in an independent
        # FKParentConstraintTo branch rather than a direct FKX child.
        c.setAttr(parent + '.segmentScaleCompensate', False)
        c.addAttr(follower.path, longName=MARKER, attributeType='bool')
        c.setAttr(follower.path + '.' + MARKER, True, lock=True)
        c.addAttr(follower.path, longName=SOURCE, attributeType='message')
        c.connectAttr(parent + '.message', follower.path + '.' + SOURCE)
        c.setAttr(follower.path + '.' + SOURCE, lock=True)
        host._transaction_changed = True


def configure_inverse_scale(host, plan):
    """Native joint creation links inverseScale even when SSC is disabled.

    orientConstraint still consumes this plug for inherited-scale FK bodies.
    """
    host._require_transaction()
    c = host._cmds
    for control in plan.controls:
        joint = control.driven_joint
        if c.getAttr(joint + '.segmentScaleCompensate'):
            continue
        parent = (c.listRelatives(joint, parent=True, fullPath=True) or [None])[0]
        if parent is None or c.nodeType(parent) != 'joint':
            continue
        target = joint + '.inverseScale'
        current = c.connectionInfo(target, sourceFromDestination=True)
        if current and not c.isConnected(parent + '.scale', target):
            raise CharacterRegistryError('来源 FK inverseScale 已有不同来源：' + joint)
        if not current:
            c.connectAttr(parent + '.scale', target)
        c.addAttr(joint, longName='advPySourceFkInverseScale', attributeType='bool')
        c.setAttr(joint + '.advPySourceFkInverseScale', True, lock=True)
        host._transaction_changed = True


def audit_registered(host, registration):
    c = host._cmds
    owned = {node.path for node in registration.nodes}
    for node in registration.nodes:
        inverse_marker = node.path + '.advPySourceFkInverseScale'
        if c.objExists(inverse_marker):
            parent = (c.listRelatives(node.path, parent=True, fullPath=True) or [None])[0]
            if (node.node_type != 'joint' or not c.getAttr(inverse_marker)
                    or not c.getAttr(inverse_marker, lock=True)
                    or c.connectionInfo(inverse_marker, isDestination=True)
                    or parent not in owned or c.nodeType(parent) != 'joint'
                    or not c.isConnected(parent + '.scale', node.path + '.inverseScale')):
                raise CharacterRegistryError('来源 FK inverseScale 父级接线改变：' + node.path)
        marker = node.path + '.' + MARKER
        if not c.objExists(marker):
            continue
        source = node.path + '.' + SOURCE
        parents = c.listConnections(source, source=True, destination=False) or []
        paths = c.ls(parents, long=True, type='joint') or []
        if (node.node_type != 'transform' or not c.getAttr(marker)
                or not c.getAttr(marker, lock=True)
                or c.connectionInfo(marker, isDestination=True)
                or not c.getAttr(source, lock=True) or len(paths) != 1
                or paths[0] not in owned
                or not c.isConnected(paths[0] + '.message', source)
                or c.getAttr(paths[0] + '.segmentScaleCompensate')):
            raise CharacterRegistryError('来源 FK 跟随父级的缩放继承改变：' + node.path)
