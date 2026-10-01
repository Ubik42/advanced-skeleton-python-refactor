"""Native asDeformer preference scope for the original legacy Face sets."""
from contextlib import contextmanager


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
