"""Actual FK correspondence shared by source roles and animation consumers."""


def source_leaf(address):
    return address.rsplit('|', 1)[-1].rsplit(':', 1)[-1]


def source_fk_bindings(saved):
    """Yield full addresses; never derive a generated control from its name.

    Generic controls also cover ordinary source limbs. The explicit RP and
    spline records cover their dedicated mechanisms. Multiple records for
    the same pair are normal; conflicting pairs remain visible to callers.
    """
    if saved is None:
        return ()
    result = []
    for channel in saved.channels:
        if not channel.key.startswith('generic.fk.'):
            continue
        stem, *tail = channel.key[len('generic.fk.'):].split('.')
        if not stem.endswith('FK') or (tail and tail[0] in ('extra', 'sub')):
            continue
        # Native axis restrictions can remove rotateX (the default Jaw does).
        # Any registered primary TRS channel identifies the same FK control.
        if channel.attribute in ('translateX', 'translateY', 'translateZ',
                                 'rotateX', 'rotateY', 'rotateZ',
                                 'scaleX', 'scaleY', 'scaleZ'):
            result.append((stem[:-2], channel.node))
    for limb in saved.source_limbs:
        result.extend((source_leaf(row.body), row.control) for row in limb.joints
                      if row.control != row.fk_driver)
    for spline in (saved.spine, *saved.additional_spines):
        if spline is not None:
            result.extend((source_leaf(joint), control) for joint, control
                          in zip(spline.body_joints, spline.fk_controls))
    return tuple(dict.fromkeys(result))


def source_control_roles(saved):
    result = {source_leaf(control): 'FK' + joint
              for joint, control in source_fk_bindings(saved)}
    if saved is not None:
        for node in getattr(saved, 'nodes', ()):
            name = source_leaf(node.path)
            if name == 'AdvPy_Global':
                result['AdvPy_Global'] = 'Main'
            if name in ('AdvPy_RootX_M', 'AdvPy_RootExtraX_M', 'AdvPy_RootOffsetX_M'):
                result[name] = name.removeprefix('AdvPy_')
            if name.startswith('AdvPy_COG'):
                result[name] = name.removeprefix('AdvPy_')
        for spline in (saved.spine, *saved.additional_spines):
            if spline is None or not getattr(spline, 'source_mode', None):
                continue
            label, side = spline.source_mode.token.rsplit('_', 1)
            result[source_leaf(spline.mode_control)] = spline.source_mode.name
            for index, control in enumerate(spline.targets, start=1):
                result[source_leaf(control)] = 'IK' + label + str(index) + '_' + side
            for index, control in enumerate(spline.extra_targets, start=1):
                result[source_leaf(control)] = 'IKExtra' + label + str(index) + '_' + side
            for index, control in enumerate(spline.sub_targets, start=1):
                result[source_leaf(control)] = 'IKSub' + label + str(index) + '_' + side
            for index, control in enumerate(spline.hybrid_controls, start=1):
                result[source_leaf(control)] = 'IKhybrid' + label + str(index) + '_' + side
            for index, control in enumerate(spline.hybrid_extras, start=1):
                result[source_leaf(control)] = 'IKhybridExtra' + label + str(index) + '_' + side
        channels = {row.key: row for row in saved.channels}
        for row in saved.channels:
            if not row.key.startswith('generic.fk.'):
                continue
            stem, *tail = row.key[len('generic.fk.'):].split('.')
            if not stem.endswith('FK') or not tail:
                continue
            if tail[0] in ('extra', 'sub'):
                prefix = 'FKExtra' if tail[0] == 'extra' else 'FKSub'
                result[source_leaf(row.node)] = prefix + stem[:-2]
        for limb in saved.source_limbs:
            result[source_leaf(limb.ik_control)] = 'IK' + limb.label + '_' + limb.side
            result[source_leaf(limb.pole_control)] = 'Pole' + limb.label + '_' + limb.side
            if getattr(limb, 'toe_control', None) and limb.toe_source:
                body = next((row.body for row in limb.joints
                             if source_leaf(row.fk_driver) == source_leaf(limb.toe_source)), None)
                if body is not None:
                    result[source_leaf(limb.toe_control)] = 'IK' + source_leaf(body)
            for index, hybrid in enumerate(getattr(limb, 'hybrid_controls', ()), start=1):
                result[source_leaf(hybrid.control)] = 'IKhybrid' + limb.label + str(index) + '_' + limb.side
            roll_prefix = 'AdvPy_' + limb.label + '_Foot_Roll'
            for control in limb.reset_controls:
                name = source_leaf(control)
                if name.startswith(roll_prefix):
                    result[name] = 'Roll' + name[len(roll_prefix):]
                local_prefix = 'AdvPy_' + limb.label + 'IKLocal'
                if name == local_prefix + '_' + limb.side:
                    result[name] = 'IKLocal' + limb.label + '_' + limb.side
                if name == local_prefix + 'Extra_' + limb.side:
                    result[name] = 'IKLocalExtra' + limb.label + '_' + limb.side
                if name == 'AdvPy_' + limb.label + 'IKExtra_' + limb.side:
                    result[name] = 'IKExtra' + limb.label + '_' + limb.side
                if name == 'AdvPy_' + limb.label + 'IKSub_' + limb.side:
                    result[name] = 'IKSub' + limb.label + '_' + limb.side
                if name == 'AdvPy_' + limb.label + 'PVExtra_' + limb.side:
                    result[name] = 'PoleExtra' + limb.label + '_' + limb.side
            if getattr(limb, 'toe_control', None):
                source = result.get(source_leaf(limb.toe_control))
                if source:
                    for control in limb.reset_controls:
                        name = source_leaf(control)
                        if name == source_leaf(limb.toe_control).replace('IK_', 'IKExtra_', 1):
                            result[name] = 'IKExtra' + source[2:]
                        if name == source_leaf(limb.toe_control).replace('IK_', 'IKSub_', 1):
                            result[name] = 'IKSub' + source[2:]
            mode = channels.get(limb.blend_key)
            if mode is not None and mode.attribute == 'FKIKBlend':
                result[source_leaf(mode.node)] = 'FKIK' + limb.label + '_' + limb.side
    return result
