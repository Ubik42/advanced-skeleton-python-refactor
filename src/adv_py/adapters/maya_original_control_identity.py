"""Expose original ADV roles for the Python graph's existing control names.

Source branches use FK/IK/Pole and a terminal side suffix. Resolving those
roles at the host boundary avoids interpreting Python implementation names
as custom controls or center controls.
"""
from adv_py.core.character_registry import REGISTRY_NAME, decode_registration


def leaf(address):
    return address.rsplit('|', 1)[-1].rsplit(':', 1)[-1]


def registration(host):
    return command_registration(host._cmds)


def command_registration(commands, namespace=''):
    """Read the same identity through either raw or character-scoped commands."""
    prefix = namespace.strip(':')
    plug = (prefix + ':' if prefix else '') + REGISTRY_NAME + '.advPyRegistryDocument'
    return decode_registration(commands.getAttr(plug)) if commands.objExists(plug) else None


def fk_bindings(saved):
    from adv_py.core.source_control_identity import source_fk_bindings
    return {joint: leaf(control) for joint, control in source_fk_bindings(saved)}


def control_roles(saved):
    from adv_py.core.source_control_identity import source_control_roles
    return source_control_roles(saved)


def source_control_name(host, control):
    name = leaf(control)
    return control_roles(registration(host)).get(name, name)


def original_custom_orient_node(host, control):
    """Find the original frame for an actual Python control or saved role."""
    c = host._cmds
    control = control.split('.', 1)[0]
    role = source_control_name(host, control)
    actual = leaf(control)
    candidates = tuple(dict.fromkeys(('CustomOrient' + role, 'CustomOrient' + actual)))
    nodes = tuple(dict.fromkeys(path for candidate in candidates
                               for path in c.ls(candidate, long=True) or []))
    if len(nodes) > 1:
        raise ValueError('原版自定义朝向层不唯一：' + role)
    return nodes[0] if nodes else None


def source_control_from_role(host, role):
    """Address an original FK/IK/Pole role in this existing Python Body."""
    name = leaf(role)
    if host._cmds.objExists(role):
        return role
    matches = [control for control, source in control_roles(registration(host)).items()
               if source == name]
    if len(matches) > 1:
        raise ValueError('原版控制器角色不唯一：' + name)
    return matches[0] if matches else role


def source_fk_joint(host, control):
    name = leaf(control)
    for joint, fk in fk_bindings(registration(host)).items():
        if fk == name:
            return joint
    return name[2:] if name.startswith('FK') else name


def source_fk_control(host, joint):
    name = leaf(joint)
    native = 'FK' + name
    if host._cmds.objExists(native):
        return native
    return fk_bindings(registration(host)).get(name, name)


def source_mirror_control(host, control, target_side):
    if target_side not in ('R', 'L'):
        raise ValueError('驱动镜像侧别需要 R 或 L')
    name = leaf(control)
    saved = registration(host)
    roles = control_roles(saved)
    source = roles.get(name, name)
    if name not in roles:
        # MEL substitute changes the first occurrence, even on a custom
        # control with a side token in the middle of its authored name.
        side = '_L' if source.endswith('_L') else '_R'
        return name.replace(side, '_' + target_side, 1)
    if not source.endswith(('_R', '_L')):
        return name
    destination = source[:-1] + target_side
    candidates = [node for node, role in roles.items() if role == destination]
    if len(candidates) > 1:
        raise ValueError('驱动镜像角色不唯一：' + destination)
    return candidates[0] if candidates else destination


def source_main(host):
    c = host._cmds
    for name in ('Main', 'AdvPy_Global'):
        nodes = c.ls(name, long=True, type='transform') or []
        if len(nodes) > 1:
            raise ValueError('Main 控制器不唯一：' + name)
        if nodes:
            return nodes[0]
    raise ValueError('缺少 Main 控制器')


def original_character_height(commands, namespace=''):
    """asgetCharHeight (55630): existing Main.height, otherwise zero.

    AdvPy_Global is the Python graph's Main role. An existing Main without
    height remains an error, as in MEL; no geometry bounds are substituted.
    Raw command callers supply a namespace, scoped command callers do not.
    """
    prefix = namespace.strip(':')
    prefix = prefix + ':' if prefix else ''
    for role in ('Main', 'AdvPy_Global'):
        node = prefix + role
        if commands.objExists(node):
            return float(commands.getAttr(node + '.height'))
    return 0.0
