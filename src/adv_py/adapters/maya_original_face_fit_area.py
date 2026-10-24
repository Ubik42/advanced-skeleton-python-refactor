"""Native ForeHead / Inner Fit areas, ADV 6.925 MEL 30437–30526."""


class MayaOriginalFaceFitAreaMixin:
    def create_original_face_fit_inner_area(self, section, suffix, mesh, geo, scale, selection):
        self._require_transaction()
        if section not in ('EyeLid', 'Lip', 'ForeHead'):
            raise ValueError('原版 Inner 区域类型无效')
        c = self._cmds
        raw = getattr(c, 'raw', c)
        self._transaction_changed = True
        part = '' if section == 'ForeHead' else 'Inner'
        shader = 'asGreenSG' if section == 'ForeHead' else 'asRedSG'
        if section == 'ForeHead':
            c.sets('ForeHeadCylinder' + suffix, edit=True, forceElement=shader)
            self.reselect_original_face_fit('EyeLid', 'Outer')
            grow_start = 'EyeBrowInner' + suffix
        else:
            curves = tuple('upper' + section + layer + 'Curve' + suffix
                           for layer in ('Outer', 'Main', 'Inner'))
            c.loft(*curves, name='tempLoft', constructionHistory=False, uniform=True,
                   close=False, autoReverse=True, degree=3, sectionSpans=2,
                   reverseSurfaceNormals=True, polygon=0)
            main = curves[1]
            middle = int(c.getAttr(main + '.spans')) // 2
            grow_start = main + f'.cv[{middle}]'
            self.reselect_original_face_fit(section, 'Outer')
        c.select(selection, add=True)
        current = raw.ls(selection=True) or []
        raw.select(raw.polyListComponentConversion(current, toVertex=True), replace=True)
        border = tuple(raw.ls(selection=True, flatten=True) or [])
        sampler = 'closestSampler'
        if c.objExists(sampler):
            c.delete(sampler)
        c.createNode('closestPointOnMesh', name=sampler)
        shapes = c.listRelatives(mesh, shapes=True, noIntermediate=True,
                                 type='mesh', fullPath=True) or []
        shape = shapes[0] if shapes else mesh
        raw.connectAttr(self.scene_address(shape) + '.outMesh',
                        self.scene_address(sampler) + '.inMesh')
        point = c.xform(grow_start, query=True, worldSpace=True, translation=True)
        c.setAttr(sampler + '.inPosition', *point, type='float3')
        if c.objExists('tempLoft'):
            c.delete('tempLoft')
        seed = int(c.getAttr(sampler + '.result.closestVertexIndex'))
        raw.select(self.scene_address(mesh) + f'.vtx[{seed}]', replace=True)
        previous_count = 0
        for _ in range(199):
            raw.polySelectConstraint(pp=1, type=0x0001)
            if border:
                raw.select(border, deselect=True)
            current_count = len(raw.ls(selection=True, flatten=True) or [])
            if current_count == previous_count:
                break
            previous_count = current_count
        c.delete(sampler)
        current = raw.ls(selection=True) or []
        raw.select(raw.polyListComponentConversion(current, toFace=True), replace=True)
        faces = tuple(raw.ls(selection=True, flatten=True) or [])
        name = section + part + 'AreaMesh' + suffix
        c.polyCube(name=name, width=1, height=1, depth=1, subdivisionsX=1,
                   subdivisionsY=1, subdivisionsZ=1, axis=(0, 1, 0),
                   createUVs=4, constructionHistory=False)
        c.sets(name, edit=True, forceElement=shader)
        target_shape = c.listRelatives(name, shapes=True, type='mesh', fullPath=True)[0]
        source_plug = self.scene_address(shape) + '.outMesh'
        destination_plug = self.scene_address(target_shape) + '.inMesh'
        raw.connectAttr(source_plug, destination_plug)
        c.refresh()
        raw.disconnectAttr(source_plug, destination_plug)
        c.parent(name, geo)
        destination = self.scene_address(name)
        source = faces[0].split('.', 1)[0] if faces else self.scene_address(mesh)
        cast = tuple(face.replace(source, destination, 1) for face in faces)
        raw.select(destination + '.f[0:999999]', replace=True)
        if cast:
            raw.select(cast, deselect=True)
        raw.delete()
        # Supplemental Python selection record does not alter native geometry.
        c.addAttr(name, longName='selection', dataType='string')
        c.setAttr(name + '.selection', ' '.join(faces), type='string')
        preview = section + part + 'AreaMeshExtrude' + suffix
        c.duplicate(name, name=preview)
        c.setAttr(name + '.v', 0)
        c.select(preview, replace=True)
        nodes = c.polyExtrudeFacet(constructionHistory=True, localTranslateZ=scale / 500.,
            keepFacesTogether=True, divisions=1, twist=0, taper=1,
            offset=0, thickness=0, smoothingAngle=30)
        c.rename(nodes[0], section + part + 'AreaMeshPolyExtrudeFacet' + suffix)
        for local_shape in c.listRelatives(preview, shapes=True) or []:
            if c.getAttr(local_shape + '.intermediateObject'):
                c.rename(local_shape, preview + 'OrigShape')
        c.refresh()
        return (c.ls(name, long=True) or [name])[0], (c.ls(preview, long=True) or [preview])[0]
