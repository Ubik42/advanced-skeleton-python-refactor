"""Translate registered Python control identities at the BodyRig read boundary.

Attribute values, file names and JSON records remain literal. The source
catalogue sees its native FK/IK/Pole roles, without renaming scene objects.
"""
from contextlib import contextmanager

from .maya_namespace import _NODE_ARGS, _NODE_RESULTS
from .maya_original_control_identity import control_roles, registration, leaf


def body_rig_roles(saved):
    roles = control_roles(saved)
    if saved is not None:
        for spline in (saved.spine, *saved.additional_spines):
            mode = getattr(spline, 'source_mode', None)
            if mode is None:
                continue
            stem, side = mode.token.rsplit('_', 1)
            roles[leaf(mode.control)] = mode.name
            for index, control in enumerate(spline.targets, 1):
                roles[leaf(control)] = 'IK' + stem + str(index) + '_' + side
            for index, control in enumerate(spline.hybrid_controls, 1):
                roles[leaf(control)] = 'IKhybrid' + stem + str(index) + '_' + side
    return roles


class BodyRigRoleCommands:
    def __init__(self, commands, roles):
        self.commands = commands
        self.roles = dict(roles)
        self.actual = {}
        for physical, role in self.roles.items():
            if role in self.actual and self.actual[role] != physical:
                raise ValueError('BodyRig 原版控制器角色不唯一：' + role)
            self.actual[role] = physical

    @property
    def raw(self):
        return getattr(self.commands, 'raw', self.commands)

    def _map(self, value, reverse=False):
        if isinstance(value, (list, tuple)):
            return type(value)(self._map(item, reverse) for item in value)
        if not isinstance(value, str):
            return value
        names = self.roles if reverse else self.actual
        node, separator, attribute = value.partition('.')
        parts = node.split('|')
        for index, part in enumerate(parts):
            namespace, colon, name = part.rpartition(':')
            if not colon:
                name = part
            translated = names.get(name)
            if translated is None:
                for prefix in ('SDK', 'CustomOrient', 'CustomOrientReverse', 'bw'):
                    if name.startswith(prefix):
                        body = name[len(prefix):]
                        for original in sorted(names, key=len, reverse=True):
                            if body == original or body.startswith(original + '_'):
                                translated = prefix + names[original] + body[len(original):]
                                break
                    if translated is not None:
                        break
            if translated is None and name.endswith('Shape') and name[:-5] in names:
                translated = names[name[:-5]] + 'Shape'
            if translated is not None:
                # A native role already present in the same character keeps
                # the source's precedence over legacy Python control names.
                if not reverse and self.commands.objExists(part):
                    translated = name
                parts[index] = namespace + ':' + translated if colon else translated
        return '|'.join(parts) + (separator + attribute if separator else '')

    def __getattr__(self, name):
        command = getattr(self.commands, name)
        if not callable(command):
            return command
        def call(*args, **kwargs):
            args, kwargs = list(args), dict(kwargs)
            if name == 'setAttr':
                if args:
                    args[0] = self._map(args[0])
            elif name not in ('createNode', 'shadingNode', 'attributeQuery') and name in _NODE_ARGS | {'select', 'listAttr'}:
                args = [self._map(value) for value in args]
            for flag in ('name', 'n', 'parent', 'p', 'node'):
                if name == 'addAttr' and flag in ('parent', 'p'):
                    continue
                if isinstance(kwargs.get(flag), str):
                    kwargs[flag] = self._map(kwargs[flag])
            if name == 'sets':
                for flag in ('isMember', 'im', 'add', 'addElement', 'forceElement'):
                    if flag in kwargs:
                        kwargs[flag] = self._map(kwargs[flag])
            result = command(*args, **kwargs)
            node_result = name in _NODE_RESULTS or name == 'ls'
            if name == 'connectionInfo' and any(kwargs.get(flag) for flag in (
                    'sourceFromDestination', 'sfd', 'destinationFromSource', 'dfs')):
                node_result = True
            if kwargs.get('uuid') or (kwargs.get('query', kwargs.get('q', False))
                    and any(kwargs.get(flag) for flag in ('weightAliasList', 'wal'))):
                node_result = False
            return self._map(result, reverse=True) if node_result else result
        return call


@contextmanager
def body_rig_role_scope(host):
    previous = host._cmds
    roles = body_rig_roles(registration(host))
    for physical, role in tuple(roles.items()):
        if not previous.objExists(physical):
            continue
        shapes = previous.listRelatives(physical, shapes=True, noIntermediate=True) or []
        if len(shapes) == 1:
            roles[leaf(shapes[0])] = role + 'Shape'
    host._cmds = BodyRigRoleCommands(previous, roles)
    try:
        yield
    finally:
        host._cmds = previous
