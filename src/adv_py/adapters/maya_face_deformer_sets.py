"""Native asDeformer preference scope for the original legacy Face sets."""
from contextlib import contextmanager


def original_deformer_set(commands, deformer):
    """Resolve the native geometry set, excluding ownership/selection sets."""
    raw = getattr(commands, 'raw', commands)
    plugs = raw.listConnections(deformer + '.message', source=False,
                                destination=True, type='objectSet', plugs=True) or []
    sets = tuple(dict.fromkeys(plug.rsplit('.', 1)[0] for plug in plugs
                              if plug.rsplit('.', 1)[-1].split('[', 1)[0] == 'usedBy'))
    if len(sets) != 1:
        raise ValueError('变形器缺少唯一原生影响集合：' + deformer)
    return sets[0]


@contextmanager
def original_face_deformer_sets(cmds):
    """Force legacy sets even in a fresh standalone Maya preference session.

    An absent optionVar is not evidence that component tags are disabled.
    Maya 2024 may default to tags until the preference is explicitly set.
    Restore both its value and its original existence, including on failure.
    """
    raw = getattr(cmds, 'raw', cmds)
    option = 'deformationUseComponentTags'
    existed = bool(raw.optionVar(exists=option))
    previous = int(raw.optionVar(query=option)) if existed else None
    try:
        raw.optionVar(intValue=(option, 0))
        yield
    finally:
        if existed:
            raw.optionVar(intValue=(option, previous))
        else:
            raw.optionVar(remove=option)
