"""Original model-update repair operations; no new detection heuristics."""
from .maya_fit import MayaFitJointHost
from .maya_original_skin_history import original_skin_cluster


class MayaOriginalModelUpdatesHost(MayaFitJointHost):
    def fix_original_reference_shaders(self):
        """asReferenceGreenShaderFix, MEL 23006–23046, whole-scene behavior."""
        self._require_transaction()
        c = getattr(self._cmds, 'raw', self._cmds)
        engines = c.ls(type='shadingEngine') or []
        references = c.ls(type='reference') or []
        self._transaction_changed = True
        for reference in references:
            c.file(cleanReference=reference)
        repaired = []
        for engine in engines:
            members = c.sets(engine, query=True) or []
            c.select(members, replace=True) if members else c.select(clear=True)
            for item in c.ls(selection=True) or []:
                node, separator, component = item.partition('.')
                suffix = separator + component.split('.', 1)[0] if separator else ''
                if not c.getAttr(node + '.intermediateObject'):
                    continue
                for history in c.listHistory(item, future=True, interestLevel=1) or []:
                    if c.objectType(history) == 'mesh' and not c.getAttr(history + '.intermediateObject'):
                        destination = history + suffix
                        c.sets(destination, edit=True, forceElement=engine)
                        repaired.append((engine, destination))
        return tuple(repaired)

    def fix_original_origin_skin_vertices(self):
        """asScNanCheckAndFix, MEL 4543–4570.

        The original targets vertices at exactly the origin. It does not use
        Python isfinite checks, thresholds, or an invented NaN replacement.
        """
        self._require_transaction()
        c = getattr(self._cmds, 'raw', self._cmds)
        from maya import mel
        self._transaction_changed = True
        vertices = []
        for mesh in c.ls(type='mesh', noIntermediate=True) or []:
            if not original_skin_cluster(c, mesh):
                continue
            c.select(mesh, replace=True)
            try:
                c.polySelectConstraint(type=0x0001, distance=1, distancePoint=(0, 0, 0),
                                       distanceBound=(0, 0), mode=3)
                current = c.ls(selection=True) or []
            finally:
                c.polySelectConstraint(mode=0)
            if not current:
                continue
            c.select(current, replace=True)
            vertices.extend(current)
            mel.eval('weightHammerVerts;')
        c.select(vertices, replace=True) if vertices else c.select(clear=True)
        return tuple(vertices)
