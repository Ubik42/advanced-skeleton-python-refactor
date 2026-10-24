"""asAdd/RemoveFitJointAttribute (MEL 4054–4280), without executing ADV MEL.

Selection is captured once in Maya order. Target choices remain native enum
labels; explicit low-level field editing is a separate operation.
"""
import re

from adv_py.core.fit_metadata import FitJointValidationError
from adv_py.core.source_fit_attributes import (
    SOURCE_FIT_ATTRIBUTE_COMPANIONS, SOURCE_FIT_ATTRIBUTE_TYPES,
)


def _exists(c, joint, attribute):
    return c.attributeQuery(attribute, node=joint, exists=True)


def _add(host, joint, attribute, kind='bool', default=1, **options):
    host._transaction_changed = True
    host._cmds.addAttr(joint, longName=attribute, attributeType=kind,
                       defaultValue=default, keyable=True, **options)


def _selected_shape(c, selected, shape_type, *, intermediate=False):
    result = ''
    for node in selected:
        shapes = c.listRelatives(node, shapes=True,
                                **({} if intermediate else {'noIntermediate': True})) or ()
        if shapes and c.objectType(shapes[0]) == shape_type:
            result = node
    return result


def _opm(host, explicit):
    if explicit is not None:
        return explicit
    raw = getattr(host._cmds, 'raw', host._cmds)
    if raw.checkBox('asBodyOffsetParentMatrixCheckBox', query=True, exists=True):
        return raw.checkBox('asBodyOffsetParentMatrixCheckBox', query=True, value=True)
    read = getattr(host, 'read_body_build_options', None)
    if read is not None:
        return read().use_offset_parent_matrix
    # Same scene option used by the Python preparation panel.
    from adv_py.core.fit_settings import FitSkeletonField
    settings = host.read_fit_skeleton_settings('FitSkeleton')
    return bool(settings.value(FitSkeletonField.USE_OFFSET_PARENT_MATRIX))


def _add_joint(host, selected, index, attribute, *, use_opm=None):
    c = host._cmds
    joint = selected[index]
    if _exists(c, joint, attribute) or c.objectType(joint) != 'joint':
        return False
    if attribute == 'twist/bendy' and _exists(c, joint, 'twistJoints'):
        c.warning('Skipping '+joint+', it has the attribute already added!')
        return False
    if attribute == 'tweakerControl' and not _opm(host, use_opm):
        c.warning('Rig must use OPM to use the "tweakerControl" attribute.')
        return False
    if attribute == 'twist/bendy':
        if _exists(c, joint, 'inbetweenJoints'):
            raise FitJointValidationError('不能混用 Twist 和 Inbetween 属性')
        _add(host, joint, 'twistJoints', 'long', 2, minValue=0)
        _add(host, joint, 'bendyCtrls', 'long', 0, minValue=0)
    elif attribute == 'inbetween':
        if any(_exists(c, joint, name) for name in ('twistJoints', 'bendyJoints')):
            raise FitJointValidationError('不能混用 Twist 和 Inbetween 属性')
        _add(host, joint, 'inbetweenJoints', 'long', 2, minValue=0)
        _add(host, joint, 'unTwister', default=0)
    elif attribute == 'global':
        _add(host, joint, attribute, 'double', 0, minValue=0, maxValue=10)
        _add(host, joint, 'globalTranslate', default=0)
    elif attribute == 'noMirror':
        _add(host, joint, attribute)
        _add(host, joint, 'noMirrorLeft', default=0)
    elif attribute == 'worldOrient':
        _add(host, joint, 'worldOrientUp', 'enum', 0,
             enumName='xUp:yUp:zUp:xDown:yDown:zDown:')
        _add(host, joint, 'worldOrientForward', 'enum', 6,
             enumName='xForward:yForward:zForward:xBackward:yBackward:zBackward:free:')
    elif attribute == 'ikLocal':
        _add(host, joint, attribute, 'enum', 0, enumName='addCtrl:nonZero:localOrient:')
    elif attribute in ('geoAttach', 'proximityPin'):
        raw = getattr(c, 'raw', c)
        if attribute == 'proximityPin':
            version = re.match(r'\d+(?:\.\d+)?', str(raw.about(version=True)))
            if version is None or float(version.group()) < 2020:
                raise FitJointValidationError('proximityPin 需要 Maya 2020 或更高版本')
        target = _selected_shape(c, selected, 'mesh')
        if len(selected) < 2 or not target:
            raise FitJointValidationError('请选择 Fit joint 和要附着的模型')
        _add(host, joint, attribute, 'enum', 0, enumName=target.replace(':', '__'))
        if attribute == 'geoAttach':
            _add(host, joint, 'geoAttachMode', 'enum', 2, enumName='point:orient:parent')
        c.select(joint, replace=True)
    elif attribute in ('aimAt', 'follow', 'ikFollow') or attribute.endswith('Constraint'):
        if any(c.objectType(node) != 'joint' for node in selected):
            raise FitJointValidationError('此属性只允许选择关节')
        if len(selected) < 2:
            raise FitJointValidationError('请先选目标关节，再选需要添加属性的 Fit joint')
        if index == 0:
            return False
        _add(host, joint, attribute, 'enum', 0, enumName=selected[0])
        if attribute == 'aimAt':
            _add(host, joint, 'aimAxis', 'enum', 0, enumName='x:y:z:')
            _add(host, joint, 'aimUpAxis', 'enum', 1, enumName='x:y:z:')
            _add(host, joint, 'aimUpObject', 'enum', 0, enumName='self:target:')
        elif attribute == 'follow':
            _add(host, joint, 'followLeftRight', default=0)
            _add(host, joint, 'followWorld', default=0)
        elif attribute == 'orientConstraint':
            _add(host, joint, 'orientConstraintMaintainOffset', default=0)
        c.select(joint, replace=True)
    elif attribute == 'follow*':
        if len(selected) < 2:
            raise FitJointValidationError('请先选目标，再选需要 Follow 的 Fit joint')
        if index == 0:
            return False
        name = 'follow'+selected[0]
        if _exists(c, joint, name):
            raise FitJointValidationError(joint+' 已设置 Follow：'+selected[0])
        _add(host, joint, name, 'double', 10, minValue=0, maxValue=10)
    elif attribute == 'curveGuide':
        target = _selected_shape(c, selected, 'nurbsCurve', intermediate=True)
        if len(selected) < 2 or not target:
            raise FitJointValidationError('请选择 Fit joint 和引导曲线')
        _add(host, joint, attribute, 'enum', 0, enumName=target.replace(':', '__'))
        _add(host, joint, 'curveGuideMode', 'enum', 1, enumName='point:aim')
        c.select(joint, replace=True)
    elif attribute == 'rootOptions':
        if selected[0] != 'Root':
            raise FitJointValidationError('rootOptions 只能添加到 Root joint')
        changed = False
        for name, kind, default, options in (
                ('numMainExtras', 'long', 0, {'minValue': 0}),
                ('legLock', 'bool', 1, {}),
                ('centerBetweenFeet', 'bool', 0, {})):
            if not _exists(c, selected[0], name):
                _add(host, selected[0], name, kind, default, **options)
                changed = True
        return changed
    elif attribute == 'childOfPart':
        _add(host, joint, attribute, 'long', 2, minValue=1, maxValue=10)
    else:
        _add(host, joint, attribute)
    return True


def _refresh_twist_geometry(host):
    from .maya_source_fit_mode import _SESSIONS
    session = _SESSIONS.get(getattr(host, 'namespace', None) or '')
    if session is not None and session.alive():
        session.update_geometry()


def add(host, attribute, *, selection=None, use_opm=None):
    if attribute not in SOURCE_FIT_ATTRIBUTE_TYPES:
        raise FitJointValidationError('未知原版 Fit 属性：'+str(attribute))
    selected = tuple(host._cmds.ls(selection=True) or ()) if selection is None else tuple(selection)
    updated = []
    for index, joint in enumerate(selected):
        # Geometry import owns its Undo snapshot and FitMode restart. Finish
        # the attribute transaction before invoking that original callback.
        with host.transaction('添加原版 Fit 属性：'+attribute):
            changed = _add_joint(host, selected, index, attribute, use_opm=use_opm)
        if changed:
            updated.append(joint)
            if attribute == 'twist/bendy':
                _refresh_twist_geometry(host)
    return tuple(updated)


def remove(host, attribute, *, selection=None):
    if attribute not in SOURCE_FIT_ATTRIBUTE_TYPES:
        raise FitJointValidationError('未知原版 Fit 属性：'+str(attribute))
    selected = (tuple(host._cmds.ls(selection=True, type='joint') or ())
                if selection is None else tuple(node for node in selection
                    if host._cmds.objectType(node) == 'joint'))
    updated = []
    with host.transaction('删除原版 Fit 属性：'+attribute):
        c = host._cmds
        for joint in selected:
            names = (attribute, *SOURCE_FIT_ATTRIBUTE_COMPANIONS.get(attribute, ()))
            if attribute == 'follow*':
                names += tuple(name for name in (c.listAttr(joint, userDefined=True) or ())
                               if name.startswith('follow'))
            changed = False
            for name in names:
                if _exists(c, joint, name):
                    host._transaction_changed = True
                    c.deleteAttr(joint+'.'+name)
                    changed = True
            if changed:
                updated.append(joint)
    return tuple(updated)
