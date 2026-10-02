"""Original mesh-history Skin cleanup, ADV 6.925 75524–75545/75582–75601."""
from __future__ import annotations

from .maya_original_skin_operations import _operation


class MayaSkinOptimizeHost:
    """Native source traversal; no weight snapshot or new pruning policy.

    The root character uses the original whole-scene mesh query. An explicit
    character namespace scopes that same query to the chosen character.
    Intermediate Shapes and repeated Skin/mesh history entries are intentional:
    MEL processes them in native ls/listHistory order as well.
    """
    def __init__(self, namespace=None, *, cmds=None, mel=None):
        if cmds is None:
            from maya import cmds
        if mel is None:
            from maya import mel
        self.cmds = cmds
        self.mel = mel
        self.namespace = (namespace or "").strip(":")

    def _mesh_skin_history(self):
        c = self.cmds
        meshes = (c.ls(self.namespace + ":*", type="mesh")
                  if self.namespace else c.ls(type="mesh")) or []
        for mesh in meshes:
            for node in c.listHistory(mesh, pruneDagObjects=True) or []:
                if c.objectType(node) == "skinCluster":
                    yield mesh, node

    def remove_unused(self):
        c = self.cmds
        selection = c.ls(selection=True) or []
        skins, removed = set(), 0
        with _operation(c, "Remove unused Skin influences"):
            for mesh, skin in self._mesh_skin_history():
                c.select(c.listRelatives(mesh, parent=True) or [], replace=True)
                before = len(c.listConnections(skin + ".matrix") or [])
                self.mel.eval("removeUnusedInfluences;")
                after = len(c.listConnections(skin + ".matrix") or [])
                removed += before - after
                skins.add(skin)
            c.select(selection, replace=True) if selection else c.select(clear=True)
        return len(skins), removed

    def prune_small_weights(self):
        c = self.cmds
        selection = c.ls(selection=True) or []
        meshes = set()
        with _operation(c, "Prune small Skin weights"):
            for mesh, skin in self._mesh_skin_history():
                c.select(c.listRelatives(mesh, parent=True) or [], replace=True)
                # No geometry argument: the source acts on Maya's actual
                # current selection and lets native locked weights survive.
                c.skinPercent(skin, pruneWeights=.01)
                meshes.add(mesh)
            c.select(selection, replace=True) if selection else c.select(clear=True)
        return len(meshes)
