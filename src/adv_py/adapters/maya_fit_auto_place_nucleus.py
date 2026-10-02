"""Keep the source stock nCloth pass inside its character's temporary solver."""
from contextlib import contextmanager, nullcontext
import json


@contextmanager
def temporary_nucleus(host):
    """Maya's stock createNCloth otherwise reuses the user's active nucleus.

    The original single-character operation renames and then deletes that
    solver. For a namespaced Python character, explicitly select a fresh
    stock NSystem before creating any cloth, and restore the global active
    solver setting afterward. Solver defaults and all cloth flags remain the
    stock/source values.
    """
    from maya import mel
    c=host._cmds
    raw=getattr(c,'raw',c)
    # Re-sourcing that file reinitializes its global to _not_set. Only load
    # it when its procedure is absent, so an existing active solver survives.
    if not mel.eval('exists "setActiveNucleusNode";'):
        mel.eval('source "getActiveNucleusNode.mel";')
    previous=mel.eval('global string $gActiveNucleusNode; $gActiveNucleusNode = $gActiveNucleusNode;')
    selection=raw.ls(selection=True,long=True) or []
    try:
        raw.select(clear=True)
        with c._creation_namespace() if hasattr(c,'_creation_namespace') else nullcontext():
            nucleus=mel.eval('setActiveNucleusNode ""; getActiveNucleusNode(0, 1);')
        identity=getattr(c,'identity',None)
        if not nucleus or not raw.objExists(nucleus):
            raise RuntimeError('Fit 展指未生成临时 Nucleus')
        if identity and not identity.owns(nucleus):
            raise RuntimeError('Fit 展指的 Nucleus 不属于当前角色')
        yield nucleus
    finally:
        mel.eval('setActiveNucleusNode '+json.dumps(previous or '')+';')
        available=[node for node in selection if raw.objExists(node)]
        raw.select(available,replace=True) if available else raw.select(clear=True)
