"""asConfirmIfNotInBuildPose, ADV 6.925 MEL 55487–55617.

This is the original operation's Maya dialog, not a Codex approval flow.
Batch reconstruction does not call it. No scene script text is evaluated.
"""
from .maya_original_control_identity import source_main


def original_non_default_pose_rows(host):
    c = host._cmds
    if not c.objExists('DeformSet') or not c.objExists('buildPose.udAttr'):
        return ()
    opm = bool(c.objExists('FitSkeleton.useOffsetParentMatrix')
               and c.getAttr('FitSkeleton.useOffsetParentMatrix'))
    rows = []
    if opm:
        attributes = ('tx','ty','tz','rx','ry','rz','sx','sy','sz')
        defaults = (0.,0.,0.,0.,0.,0.,1.,1.,1.)
        controls = c.sets('ControlSet', query=True) or [] if c.objExists('ControlSet') else []
    else:
        attributes = ('rx','ry','rz','sx','sy','sz')
        defaults = (0.,0.,0.,1.,1.,1.)
        controls = c.sets('DeformSet', query=True) or []
    for control in controls:
        if not opm and c.objExists(control + '.partialJoint'):
            continue
        for attribute, default in zip(attributes, defaults):
            plug = control + '.' + attribute
            if opm and not c.getAttr(plug, settable=True):
                continue
            value = c.getAttr(plug)
            if abs(value - default) > .01:
                rows.append((plug, value))
            if len(rows) > 35:
                break
        if len(rows) > 35:
            break
    if not opm:
        try:
            main = source_main(host)
        except ValueError:
            main = 'Main'
        for control in (main, *('MainExtra' + str(index) for index in range(1, 9))):
            if not c.objExists(control):
                break
            for channel, expected in (('t',0.), ('r',0.), ('s',1.)):
                for axis in 'xyz':
                    plug = control + '.' + channel + axis
                    value = c.getAttr(plug)
                    if value != expected:
                        rows.append((plug, value))
    return tuple(rows)


def confirm_original_build_pose(host):
    rows = original_non_default_pose_rows(host)
    if not rows:
        return 1
    message = '\n'.join(plug + ' = ' + str(value) for plug, value in rows)
    if len(rows) > 35:
        message += '\n……还有其他通道。'
    raw = getattr(host._cmds, 'raw', host._cmds)
    restore, proceed, cancel = '回到构建姿态并继续', '直接继续', '取消'
    result = raw.confirmDialog(title='当前不在构建姿态',
        message=message + '\n建议先回到构建姿态。', button=(restore, proceed, cancel),
        dismissString=cancel, defaultButton=cancel)
    if result == restore:
        host.apply_body_build_pose(host.read_body_build_pose())
        raw.refresh()
        return 1
    return 2 if result == proceed else 0
