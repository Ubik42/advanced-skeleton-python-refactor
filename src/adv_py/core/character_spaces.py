"""Semantic channel contract shared by space events and portable animation."""
from .character_registry import CharacterChannel, CharacterRegistryError


def space_mode_channel(spec):
    return CharacterChannel(f'space.{spec.key}.mode', spec.global_source,
                            f'spaceMode_{spec.key}', 0., 1.)


def space_proxy_path(spec, index, mode):
    return spec.source(mode, index) + f'|AdvPy_SpaceProxy_{spec.key}_{index}_{mode}'


def space_channels(spec):
    result = [space_mode_channel(spec)]
    for index, _ in enumerate(spec.targets):
        for mode in ('body', 'global'):
            for attribute in spec.attributes:
                result.append(CharacterChannel(f'space.{spec.key}.{index}.{mode}.{attribute}',
                    space_proxy_path(spec, index, mode), attribute))
    return tuple(result)


def has_animated_spaces(registration):
    return any(ch.key.startswith('space.') for ch in registration.channels)


def validate_space_values(channels, spaces):
    values = dict(channels)
    modes = {key: values[f'space.{key}.mode'] for key, _ in spaces
             if f'space.{key}.mode' in values}
    if not modes:
        return False
    if len(modes) != len(spaces) or any(modes[key] != (0. if mode == 'body' else 1.)
                                     for key, mode in spaces):
        raise CharacterRegistryError('空间模式通道必须完整，且与离散空间状态一致')
    return True


def character_channel_tangent(key):
    # Native booleans and the source noFlipAxis enum must hold their value
    # until the next key; interpolating portable samples would invent states
    # which Maya's source attributes cannot represent.
    discrete = {'autoVis', 'FKVis', 'IKVis', 'firstJointFixed', 'noFlipAxis'}
    return 'step' if key.startswith('space.') or key.rsplit('.', 1)[-1] in discrete else 'linear'
