"""ADV BodyRig metadata helpers, source 23416–23888."""
from math import dist

from adv_py.core.original_body_rig import ik_axes, sdk_relationship, attribute_text
from adv_py.core.original_control_orientation import original_control_identity
from .maya_unreal_face_display import vector, parent, leaf, control_offset, curve_shapes


class MayaOriginalBodyRigDataMixin:
    def _body_rig_attributes(self, node, *, fit=False):
        c = self._cmds
        if not node or not c.objExists(node):
            return []
        result = []
        for attr in c.listAttr(node, keyable=True, userDefined=True) or []:
            plug = node + '.' + attr
            if fit and (attr.startswith('fat') or (
                    attr in ('twistJoints', 'inbetweenJoints') and c.getAttr(plug) == 0)):
                continue
            result.append(dict(name=attr, type=c.getAttr(plug, type=True),
                               value=attribute_text(c.getAttr(plug))))
        return result

    def _body_rig_diameter(self, control):
        c = self._cmds
        bounds = [(vector(c, shape + '.boundingBoxMin'), vector(c, shape + '.boundingBoxMax'))
                  for shape in c.listRelatives(control, shapes=True) or []]
        if not bounds:
            return 0.
        scale = c.xform(control, query=True, worldSpace=True, scale=True)
        return max(0., *((max(high[axis] for _, high in bounds) - min(low[axis] for low, _ in bounds))
                        * scale[axis] for axis in range(3)))

    def _body_rig_driving_system(self, control):
        c = self._cmds
        channels = []
        for attr in self.original_driving_attributes(control):
            relationships, ranges = [], []
            for curve in sorted(self.original_driving_curves(control, attr)):
                next_nodes = c.listConnections(curve + '.output', source=False,
                                               destination=True, skipConversionNodes=True) or []
                plugs = []
                if next_nodes and c.attributeQuery('output', node=next_nodes[0], exists=True):
                    plugs = c.listConnections(next_nodes[0] + '.output', source=False,
                        destination=True, skipConversionNodes=True, plugs=True) or []
                if not plugs:
                    plugs = c.listConnections(curve + '.output', source=False,
                        destination=True, skipConversionNodes=True, plugs=True) or []
                if not plugs or '.' not in plugs[0]:
                    continue
                target, attribute = plugs[0].split('.', 1)
                xs = c.keyframe(curve, query=True, floatChange=True) or []
                ys = c.keyframe(curve, query=True, valueChange=True) or []
                if not xs or len(xs) != len(ys):
                    continue
                ranges.extend(xs)
                row = sdk_relationship(target.replace('SDK', ''), attribute.rsplit('.', 1)[-1], xs, ys)
                if row is not None:
                    relationships.append(row)
            if relationships:
                channels.append(dict(name=attr, driverMin=min(ranges) if ranges else 0.,
                    driverMax=max(ranges) if ranges else 10., relationships=relationships))
        return channels

    def _body_rig_control(self, control, parent_control, joint, fit_joint,
                          kind, gizmo, world_space, ik=None):
        c = self._cmds
        color = [1., 0., 0.]
        shapes = c.listRelatives(control, shapes=True) or []
        if shapes:
            index = c.getAttr(shapes[0] + '.overrideColor') if c.objExists(shapes[0] + '.overrideColor') else 0
            if leaf(control).startswith('ctrl'):
                index = 17
            if 0 < index < 32:
                color = list(c.colorIndex(index, query=True))
        diameter = self._body_rig_diameter(control)
        return dict(name=leaf(control), parent=leaf(parent_control), joint=leaf(joint),
            type=kind, gizmo=gizmo, worldSpace=bool(world_space),
            diameter=diameter * 10. if kind == 'OnFace' else diameter,
            offset=control_offset(c, control),
            positionWorld=list(c.xform(control, query=True, worldSpace=True, translation=True)),
            rotationWorld=list(c.xform(control, query=True, worldSpace=True, rotation=True)),
            worldMatrix=list(c.xform(control, query=True, worldSpace=True, matrix=True)),
            color=[*color, 1.], curveShapes=curve_shapes(c, control),
            fitAttributes=self._body_rig_attributes(fit_joint, fit=True),
            controlAttributes=self._body_rig_attributes(control),
            drivingSystem=self._body_rig_driving_system(control) if kind == 'DrivingSystem' else [],
            ik=ik or {})

    def _body_rig_joint(self, joint):
        c = self._cmds
        parents = c.listRelatives(joint, parent=True, type='joint') or []
        is_joint = c.nodeType(joint) == 'joint'
        name = leaf(joint)
        fit = name[:-2] if name.endswith(('_L', '_R', '_M')) else name
        return dict(name=name, parent=leaf(parents[0]) if parents else '',
            translation=list(vector(c, joint + '.translate')),
            rotation=list(vector(c, joint + '.rotate')),
            jointOrient=list(vector(c, joint + '.jointOrient')) if is_joint else [0., 0., 0.],
            scale=list(vector(c, joint + '.scale')),
            rotateOrder=c.getAttr(joint + '.rotateOrder') if is_joint else 0,
            fitJointInfo=dict(name=fit, attributes=self._body_rig_attributes(fit, fit=True)))

    def _body_rig_position_local(self, position, ancestor, probe_name):
        c = self._cmds
        probe = c.createNode('transform', name=probe_name + '#', skipSelect=True)
        try:
            c.xform(probe, worldSpace=True, translation=position)
            probe = c.parent(probe, ancestor, absolute=True)[0]
            return vector(c, probe + '.translate')
        finally:
            c.delete(probe)

    def _body_rig_ik(self, start, middle, end, pole, default_ik):
        c = self._cmds
        middle_world = c.xform(middle, query=True, worldSpace=True, translation=True)
        pole_world, length, pole_local = [0., 0., 0.], 0., None
        if c.objExists(pole):
            pole_world = c.xform(pole, query=True, worldSpace=True, translation=True)
            length = dist(pole_world, middle_world)
        offset = self._body_rig_position_local(middle_world, start, 'asBodyRigAxisProbe')
        if c.objExists(pole):
            pole_local = self._body_rig_position_local(pole_world, middle, 'asBodyRigPoleProbe')
        primary, secondary = ik_axes(offset, pole_local)
        return dict(startJoint=leaf(start), middleJoint=leaf(middle), endJoint=leaf(end),
            primaryAxis=primary, secondaryAxis=secondary, polePositionWorld=list(pole_world),
            solver='ikRPsolver', poleControl=leaf(pole), poleLineLength=length, defaultIK=int(default_ik))

    def _body_rig_driving_joint(self, control):
        c = self._cmds
        constraint = control + '_parentConstraint1'
        if c.objExists(constraint):
            targets = c.listConnections(constraint + '.target[0].targetTranslate',
                                        source=True, destination=False) or []
            if targets and c.nodeType(targets[0]) == 'joint':
                return targets[0]
        for dm in c.listConnections(control + '.translate', source=True, destination=False) or []:
            if c.nodeType(dm) != 'decomposeMatrix':
                continue
            for mm in c.listConnections(dm + '.inputMatrix', source=True, destination=False) or []:
                if c.nodeType(mm) != 'multMatrix':
                    continue
                for joint in c.listConnections(mm + '.matrixIn', source=True, destination=False) or []:
                    if c.nodeType(joint) == 'joint':
                        return joint
        return ''

    def _body_rig_rock(self, control):
        c = self._cmds
        info = original_control_identity(leaf(control))
        result = dict(attribute='rock')
        any_pivot = False
        for label, role, minimum, maximum in (
                ('innerPivot', 'Inner', -200, 0), ('outerPivot', 'Outer', 0, 200)):
            pivot = 'IK' + info.name + 'FootRock' + role + 'Pivot' + info.side
            result[label] = None
            if c.objExists(pivot):
                any_pivot = True
                result[label] = dict(name=pivot,
                    positionWorld=list(c.xform(pivot, query=True, worldSpace=True, translation=True)),
                    worldMatrix=list(c.xform(pivot, query=True, worldSpace=True, matrix=True)),
                    rotationAxis='Z', inputMin=minimum, inputMax=maximum,
                    rotationMultiplier=-1. if info.side == '_L' else 1.)
        return result if any_pivot else None
