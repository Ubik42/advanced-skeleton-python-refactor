"""Authored FaceRig display metadata, ADV MEL 23506 and 61086–61321."""
from adv_py.core.unreal_face_solver import LOOK_AT_CONTROLS, face_control_kind, face_control_adapter


def leaf(path):
    return path.rsplit('|', 1)[-1].rsplit(':', 1)[-1]


def vector(c, plug):
    value = c.getAttr(plug)
    if len(value) == 1 and isinstance(value[0], (tuple, list)):
        value = value[0]
    return tuple(float(item) for item in value)


def parent(c, node):
    return (c.listRelatives(node, parent=True) or [''])[0]


def inside(c, node, ancestors):
    current = parent(c, node)
    while current:
        if leaf(current) in ancestors:
            return True
        current = parent(c, current)
    return False


def _unsupported_shape(control, shape):
    return '1' in leaf(shape) and not leaf(shape).startswith(leaf(control))


def diameter(c, control):
    bounds = []
    for shape in c.listRelatives(control, shapes=True) or []:
        if not _unsupported_shape(control, shape):
            bounds.append((vector(c, shape + '.boundingBoxMin'), vector(c, shape + '.boundingBoxMax')))
    if not bounds:
        return 0.
    scale = c.xform(control, query=True, worldSpace=True, scale=True)
    return max(0., *((max(high[axis] for _, high in bounds) - min(low[axis] for low, _ in bounds)) * scale[axis]
                     for axis in range(3)))


def control_offset(c, control):
    shapes = c.listRelatives(control, shapes=True) or []
    name = leaf(control)
    if not name.startswith('ctrl') and len(shapes) != 1:
        return [0., 0., 0.]
    # Native ctrl controls require their first curve shape and parent.
    low, high = vector(c, shapes[0] + '.boundingBoxMin'), vector(c, shapes[0] + '.boundingBoxMax')
    scale = c.xform(control, query=True, worldSpace=True, scale=True)
    offset = [(low[axis] + high[axis]) / 2 * scale[axis]
              if abs(low[axis] + high[axis]) > .01 else 0. for axis in range(3)]
    if name.startswith('ctrl'):
        offset = list(vector(c, parent(c, control) + '.translate'))
    paths = c.ls(control, long=True) or []
    if paths and any(leaf(part) == 'DrivingSystem' for part in paths[0].split('|')) and name.endswith('_L'):
        offset = [-value for value in offset]
    return offset


def curve_shapes(c, control):
    result = []
    for shape in c.listRelatives(control, children=True, shapes=True,
                                  noIntermediate=True, type='nurbsCurve', fullPath=True) or []:
        if _unsupported_shape(control, shape):
            continue
        info = c.createNode('curveInfo', skipSelect=True)
        try:
            c.connectAttr(shape + '.local', info + '.inputCurve', force=True)
            rational = bool(c.objExists(shape + '.isRational') and c.getAttr(shape + '.isRational'))
            weights = c.getAttr(info + '.weights[*]') or [] if rational else []
            count = c.getAttr(info + '.controlPoints', size=True)
            points = [dict(position=list(vector(c, info + f'.controlPoints[{index}]')),
                           weight=weights[index] if index < len(weights) else 1.) for index in range(count)]
            enabled = bool(c.objExists(shape + '.overrideEnabled') and c.getAttr(shape + '.overrideEnabled'))
            color = [1., 1., 1.]
            if enabled and c.objExists(shape + '.overrideRGBColors') and c.getAttr(shape + '.overrideRGBColors'):
                color = list(vector(c, shape + '.overrideColorRGB'))
            elif c.objExists(shape + '.overrideColor'):
                color = list(c.colorIndex(c.getAttr(shape + '.overrideColor'), query=True))
            result.append(dict(name=leaf(shape), degree=c.getAttr(shape + '.degree'),
                form=('open', 'closed', 'periodic')[c.getAttr(shape + '.form')],
                is2D=bool(c.objExists(shape + '.is2D') and c.getAttr(shape + '.is2D')),
                knots=list(c.getAttr(info + '.knots[*]') or []), cvs=points,
                overrideEnabled=enabled, overrideColor=[*color, 1.],
                lineWidth=c.getAttr(shape + '.lineWidth') if c.objExists(shape + '.lineWidth') else 1.))
        finally:
            c.delete(info)
    return result


def face_control(c, control):
    name = leaf(control)
    bounds = c.exactWorldBoundingBox(control)
    shapes = c.listRelatives(control, shapes=True) or []
    color = [1., 1., 0.]
    if shapes and c.objExists(shapes[0] + '.overrideColor'):
        index = c.getAttr(shapes[0] + '.overrideColor')
        if 0 < index < 32:
            color = list(c.colorIndex(index, query=True))
    kind = 'Face' if name in LOOK_AT_CONTROLS else 'OnFace'
    row = dict(name=name, parent=leaf(parent(c, control)), type=kind,
        kind=face_control_kind(name), diameter=diameter(c, control),
        offset=control_offset(c, control),
        positionWorld=list(c.xform(control, query=True, worldSpace=True, translation=True)),
        rotationWorld=list(c.xform(control, query=True, worldSpace=True, rotation=True)),
        worldMatrix=list(c.xform(control, query=True, worldSpace=True, matrix=True)),
        shapePositionWorld=[(bounds[axis] + bounds[axis + 3]) / 2 for axis in range(3)],
        color=[*color, 1.], **face_control_adapter(name))
    if kind == 'Face':
        row['curveShapes'] = curve_shapes(c, control)
    return row


def visibility_groups(c):
    if not c.objExists('ctrlBox'):
        return []
    result = []
    for attr in c.listAttr('ctrlBox', userDefined=True, string='*Vis') or []:
        members = []
        for plug in c.listConnections('ctrlBox.' + attr, source=False, destination=True, plugs=True) or []:
            node, _, attribute = plug.partition('.')
            if attribute not in ('visibility', 'v', 'overrideVisibility', 'ovv'):
                continue
            if c.objectType(node, isAType='shape'):
                node = parent(c, node)
            if node and c.objectType(node, isAType='transform') and leaf(node) not in members:
                members.append(leaf(node))
        defaults = c.attributeQuery(attr, node='ctrlBox', listDefault=True) or []
        result.append(dict(control='ctrlBox', attribute=attr,
            default=bool(defaults[0]) if defaults else True, members=members))
    return result


def look_at_systems(c):
    required = ('AimEye_M', 'AimEye_R', 'AimEye_L', 'Eye_R', 'Eye_L', 'EyeAim_R', 'EyeAim_L')
    if not all(c.objExists(name) for name in required):
        return []
    return [dict(masterControl='AimEye_M', targets=['AimEye_R', 'AimEye_L'], eyes=[
        dict(control='Eye_' + side, aimTransform='EyeAim_' + side,
             result='SDKEye_' + side, target='AimEye_' + side,
             aimAxis=[0., 0., 1.], upAxis=[0., 1., 0.], upObject='AimEyeUpVec') for side in ('R', 'L')])]


def display_document(c, rest_joints):
    face_scale = c.getAttr('FaceFitSkeleton.faceScale') if c.objExists('FaceFitSkeleton.faceScale') else 1.
    controls = []
    for control in c.sets('FaceControlSet', query=True) or [] if c.objExists('FaceControlSet') else []:
        if (c.objExists(control) and c.nodeType(control) == 'transform'
                and inside(c, control, ('OnFacecontrols',))
                and not inside(c, control, ('ctrlBoxOffset', 'ctrlBox2Offset'))
                and c.listRelatives(control, shapes=True) and control not in controls):
            controls.append(control)
    for control in LOOK_AT_CONTROLS:
        if (c.objExists(control) and c.nodeType(control) == 'transform'
                and c.listRelatives(control, shapes=True) and control not in controls):
            controls.append(control)
    rig = dict(ctrlBoxOffsetWorldLocation=[0., 0., 0.], ctrlBoxOffsetWorldRotation=[0., 0., 0.],
        ctrlBoxOffsetBoundsScale=[1., 1., 1.], ctrlBoxShapeLocation=[0., -.2 * face_scale, 0.],
        ctrlBoxShapeScale=[.1 * face_scale, .22 * face_scale, .1 * face_scale],
        onFaceControlsScale=[1., 1., 1.], jawPlacementWorldLocation=[0., 0., 0.],
        mayaFaceJointHeight=c.xform('FaceJoint_M', query=True, worldSpace=True, translation=True)[1])
    jaw = 'Jaw' if c.objExists('Jaw') else 'ChinCreaseJoint_M' if c.objExists('ChinCreaseJoint_M') else None
    if jaw:
        rig['jawPlacementWorldLocation'] = list(c.xform(jaw, query=True, worldSpace=True, translation=True))
    if c.objExists('ctrlBoxOffset'):
        rig['ctrlBoxOffsetWorldLocation'] = list(c.xform('ctrlBoxOffset', query=True, worldSpace=True, translation=True))
        rig['ctrlBoxOffsetWorldRotation'] = list(c.xform('ctrlBoxOffset', query=True, worldSpace=True, rotation=True))
    if c.objExists('OnFacecontrols'):
        rig['onFaceControlsScale'] = list(c.xform('OnFacecontrols', query=True, worldSpace=True, scale=True))
    bases = {}
    for joint in rest_joints:
        if not c.objExists(joint):
            continue
        ancestor = parent(c, joint)
        world = c.xform(joint, query=True, worldSpace=True, matrix=True)
        local = world
        if ancestor and c.objExists(ancestor):
            probe = c.createNode('transform', name='asUnrealFaceSolverRestBasisProbe#', skipSelect=True)
            try:
                c.xform(probe, worldSpace=True, matrix=world)
                probe = c.parent(probe, ancestor, absolute=True)[0]
                local = c.xform(probe, query=True, matrix=True)
            finally:
                c.delete(probe)
        bases[leaf(joint)] = dict(parent=leaf(ancestor), mayaLocalMatrix=list(local))
    return dict(version=2, coordinateSystem=dict(source='Maya', upAxis='Y', rotationUnit='degrees'),
        rig=rig, controls=[face_control(c, node) for node in controls],
        visibilityGroups=visibility_groups(c), lookAtSystems=look_at_systems(c),
        matrixConvention=dict(layout='row-major', vectorConvention='row-vector',
            mayaLocalMatrixDefinition='jointWorldMatrix * inverse(parentWorldMatrix)'),
        jointRestBases=bases)
