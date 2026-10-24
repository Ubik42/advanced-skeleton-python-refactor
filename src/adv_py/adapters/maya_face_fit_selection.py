"""asGetFaceFitSelection / OtherObject, ADV 6.925 MEL 41359–41460."""
from adv_py.core.fit_settings import FitSkeletonValidationError
from adv_py.core.original_face_fitting_update import original_face_fit_reselect_node


class MayaFaceFitSelectionMixin:
    def _reselect_original_lip_main_for_sampling(self):
        c = self._cmds
        fit = self._fit(required=True)
        has_non_sym = c.objExists(fit + '.NonSym')
        side = c.getAttr(fit + '.NonSymSide') if has_non_sym else ''
        holder = original_face_fit_reselect_node('Lip', 'Main', has_non_sym=has_non_sym, side=side)
        if c.objExists(holder) and c.objExists(holder + '.selection'):
            tokens = (c.getAttr(holder + '.selection') or '').split()
            c.select(tokens, replace=True) if tokens else c.select(clear=True)

    def sample_face_fit_vertices(self, object_name, geometry):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, 'raw', c)
        selected = tuple(raw.ls(selection=True) or [])
        if c.objExists('asGetFaceFitSelectionOtherObject'):
            geometry = selected[0]
        if '.' in geometry:
            geometry = (raw.ls(self.scene_address(geometry), objectsOnly=True) or [None])[0]
        shapes = c.listRelatives(geometry, shapes=True, noIntermediate=True, fullPath=True, type='mesh') or []
        if not shapes and c.nodeType(geometry) == 'mesh':
            shapes = [geometry]
        if len(shapes) != 1:
            raise FitSkeletonValidationError('Face 采样几何体需要唯一 Mesh Shape')
        local_shapes = ([] if '.' in object_name else c.listRelatives(object_name, shapes=True, fullPath=True) or [])
        kind = 'locator' if '.' in object_name else (c.objectType(local_shapes[0]) if local_shapes else '')
        sampler = 'closestSamplerFitSelection2'
        if c.objExists(sampler):
            c.delete(sampler)
        c.createNode('closestPointOnMesh', name=sampler)
        raw.connectAttr(self.scene_address(shapes[0]) + '.outMesh', self.scene_address(sampler) + '.inMesh', force=True)
        result = []

        def sample(point):
            c.setAttr(sampler + '.inPosition', *point, type='float3')
            result.append(geometry + f'.vtx[{int(c.getAttr(sampler + ".result.closestVertexIndex"))}]')

        try:
            curves = []
            if kind == 'locator':
                sample(c.xform(object_name, query=True, worldSpace=True, translation=True))
            elif kind == 'mesh':
                extrusion = object_name + 'PolyExtrudeFacet'
                if c.objExists(extrusion):
                    c.setAttr(extrusion + '.nodeState', 1)
                try:
                    for index in range(int(c.polyEvaluate(object_name, vertex=True))):
                        sample(c.xform(object_name + f'.vtx[{index}]', query=True, worldSpace=True, translation=True))
                finally:
                    if c.objExists(extrusion):
                        c.setAttr(extrusion + '.nodeState', 0)
            elif not local_shapes:
                # Native sampling examines only direct children with shapes.
                for child in c.listRelatives(object_name, children=True) or []:
                    child_shapes = c.listRelatives(child, shapes=True) or []
                    if 'Profile' not in child and child_shapes:
                        curves.append(child)
            else:
                curves.append(object_name)
            for curve in curves:
                count = int(c.getAttr(curve + '.spans')) + int(c.getAttr(curve + '.degree'))
                if 'Lip' in curve:
                    self._reselect_original_lip_main_for_sampling()
                for index in range(count):
                    sample(c.xform(curve + f'.cv[{index}]', query=True, worldSpace=True, translation=True))
        finally:
            if c.objExists(sampler):
                c.delete(sampler)
            raw.select(selected, replace=True) if selected else raw.select(clear=True)
        # Repeated nearest vertices and authored child/CV order are significant.
        return tuple(result)

    def sample_other_face_fit_vertices(self, object_name, other_object, side=''):
        # Native side argument is unused.
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, 'raw', c)
        selected = tuple(raw.ls(selection=True) or [])
        marker = c.createNode('transform', name='asGetFaceFitSelectionOtherObject')
        try:
            c.select(other_object, replace=True)
            return self.sample_face_fit_vertices(object_name, other_object)
        finally:
            if c.objExists(marker):
                c.delete(marker)
            raw.select(selected, replace=True) if selected else raw.select(clear=True)
