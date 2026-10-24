"""Native Offset Face import/update, MEL 49526–49868, no ADV evaluation."""
from adv_py.core.original_offset_face import (
    OriginalOffsetFaceImportOptions, original_offset_face_geometry,
    original_offset_face_name_swap, original_offset_face_head_choices,
    original_offset_face_landmarks,
)
from .maya_face_original_build import MayaOriginalFaceBuildHost
from .maya_original_skin_history import related_skin_cluster, new_original_skin_clusters
from .maya_original_locked_skin_copy import copy_original_skin_weights_obey_locks
from .maya_original_transform_channels import align_original_transform


class MayaOriginalOffsetFaceHost(MayaOriginalFaceBuildHost):
    @property
    def _offset_face_raw(self):
        return getattr(self._cmds, 'raw', self._cmds)

    def original_offset_face_import_choices(self):
        c = self._offset_face_raw
        existing = tuple(c.ls('OffsetFace', recursive=True) or [])
        paths = original_offset_face_head_choices(c.ls(long=True, type='joint') or [],
                                                  has_imported_face=bool(existing))
        return ('FaceLeft' if existing else 'FaceRight',
                tuple((c.ls(path) or [path])[0] for path in paths), bool(existing))

    def _original_offset_face_frame(self, landmarks):
        c = self._offset_face_raw
        if c.objExists('offsetFaceNodes'):
            c.delete('offsetFaceNodes')
        holder = c.createNode('transform', name='offsetFaceNodes')
        center = c.spaceLocator(name='offsetFaceCenter')[0]
        center = c.parent(center, holder)[0]
        locators = {name: c.duplicate(center, name=name)[0] for name in (
            'offsetFaceMaxY', 'offsetFaceMaxZ', 'offsetFaceMinZ')}
        for name, ordinal in (('offsetFaceMaxY', landmarks.max_y),
                              ('offsetFaceMaxZ', landmarks.max_z), ('offsetFaceMinZ', landmarks.min_z)):
            position = c.xform(landmarks.vertices[ordinal], query=True, worldSpace=True, translation=True)
            c.xform(locators[name], worldSpace=True, translation=position)
        c.delete(c.pointConstraint(locators['offsetFaceMaxZ'], locators['offsetFaceMinZ'], center))
        c.delete(c.aimConstraint(locators['offsetFaceMaxZ'], center, offset=(0,0,0), weight=1,
            aimVector=(0,0,1), upVector=(0,1,0), worldUpType='object',
            worldUpObject=locators['offsetFaceMaxY']))
        c.setAttr(center+'.rx', 0)
        reversed_node = c.spaceLocator(name='offsetFaceReversed')[0]
        reversed_node = c.parent(reversed_node, center)[0]
        for channel in ('tx', 'ry', 'rz'):
            c.setAttr(center+'.'+channel, 0)
        reversed_node = c.parent(reversed_node, holder)[0]
        position = c.getAttr(reversed_node+'.t')[0]
        rotation = c.getAttr(reversed_node+'.r')[0]
        c.delete(holder)
        return position, rotation

    def _delete_offset_face_body(self):
        c = self._cmds
        raw = self._offset_face_raw
        if not c.objExists('FitSkeleton'):
            return
        if c.objExists('FaceGroup'):
            if raw.confirmDialog(title='Confirm', message='This will also delete the FaceSetup',
                    button=['Ok', 'Cancel'], defaultButton='Ok') != 'Ok':
                return  # Native caller still deletes FitSkeleton after return.
            face = self.plan_delete_face_advanced()
            if face is not None:
                self.delete_face_advanced(face)
        body = self.plan_delete_body_advanced(face_will_be_deleted=True)
        if body is not None and body.group is not None:
            self.delete_body_advanced(body)

    def create_original_offset_face(self):
        self._require_transaction()
        raw = self._offset_face_raw
        selected = tuple(raw.ls(selection=True) or [])
        vertices = tuple(node for node in selected if '.vtx' in node)
        # Validate the original unflattened selection before sampling it.
        landmarks = original_offset_face_landmarks(selected, ((0,0,0),)*len(vertices))
        raw.select(vertices, replace=True)
        if raw.file(query=True, modified=True):
            if raw.confirmDialog(title='Warning',
                    message='This operation will make a new Maya-file.\n\nUnsaved changes to current file will be lost',
                    button=['Continue', 'Cancel'], defaultButton='Cancel', dismissString='Cancel') != 'Continue':
                return None
        positions = tuple(raw.xform(node, query=True, worldSpace=True, translation=True) for node in vertices)
        landmarks = original_offset_face_landmarks(selected, positions)
        self._transaction_changed = True
        position, rotation = self._original_offset_face_frame(landmarks)
        directory = raw.workspace(query=True, active=True)+'/'+raw.workspace(query=True, fileRuleEntry='scene')
        files = raw.fileDialog2(fileFilter='*.ma', dialogStyle=2, startingDirectory=directory) or []
        if not files or not files[0]:
            raw.select(vertices, replace=True)
            return None
        file = files[0]
        c = self._cmds
        if c.objExists('OffsetFace'):
            c.delete('OffsetFace')
        offset = c.createNode('transform', name='OffsetFace')
        c.addAttr(offset, longName='baseVtxNrs', dataType='string')
        c.setAttr(offset+'.baseVtxNrs', landmarks.base_vertex_indices, type='string')
        keep = False
        if c.objExists('FaceFitSkeleton'):
            choice = raw.confirmDialog(title='Keep ?',
                message='FaceFitSkeleton Already exists\n\nKeep current FaceSetup ?',
                button=['Yes', 'No', 'Cancel'], defaultButton='No', dismissString='Cancel')
            if choice == 'Cancel':
                return None
            keep = choice == 'Yes'
            if choice == 'No':
                face = self.plan_delete_face_advanced()
                if face is not None:
                    self.delete_face_advanced(face)
                if c.objExists('FaceFitSkeleton'):
                    c.delete('FaceFitSkeleton')
        if c.objExists('FitSkeleton'):
            self._delete_offset_face_body()
            if c.objExists('FitSkeleton'):
                c.delete('FitSkeleton')
        if not keep:
            raw.select(raw.ls(type='mesh') or [], replace=True)
            raw.pickWalk(direction='up')
            raw.delete(constructionHistory=True)
            c.select(clear=True)
            c.joint(name='Head_M')
            c.joint(name='OffsetFaceJoint')
            raw.select((self.scene_address('OffsetFaceJoint'), *(raw.ls(type='mesh') or [])), replace=True)
            new_original_skin_clusters(commands=raw, maximum_influences=3)
            c.xform('OffsetFaceJoint', worldSpace=True, translation=position, rotation=rotation)
            raw.select(raw.ls(type='mesh') or [], replace=True)
            raw.pickWalk(direction='up')
            raw.delete(constructionHistory=True)
            # Native asAlign uses parent/reset/restore, including the joint's
            # generated parent frame. Euler world copies change that behavior.
            offset = align_original_transform(c, offset, 'OffsetFaceJoint', True, True)
            c.delete('OffsetFaceJoint')
            raw.select((self.scene_address('Head_M'), *(raw.ls(type='mesh') or [])), replace=True)
            new_original_skin_clusters(commands=raw, maximum_influences=3)
        # Source only renames the current scene; it does not save/export it.
        raw.file(rename=file)
        c.parent(offset, 'Head_M')
        raw.select(clear=True)
        raw.dgdirty(allPlugs=True)
        raw.refresh()
        raw.confirmDialog(title='New File', message='You are now in this MayaFile:\n\n'+file+
            '\n\nYou can now start FaceSetup', button=['Ok'], defaultButton='Ok')
        return {'file': file, 'saved': False, 'keep_existing': keep,
                'base_vertices': landmarks.base_vertex_indices}

    def _write_offset_face_settings(self, file, options):
        c = self._offset_face_raw
        if c.objExists('OffsetFaceImportSettings'):
            c.delete('OffsetFaceImportSettings')
        node = c.createNode('transform', name='OffsetFaceImportSettings')
        for attribute, value in (('nameSpace', options.namespace), ('headJoint', options.head_joint),
                ('nameSwapA', options.search), ('nameSwapB', options.replacement), ('file', file)):
            c.addAttr(node, longName=attribute, dataType='string')
            c.setAttr(node+'.'+attribute, value, type='string')
        c.addAttr(node, longName='nameSwap', attributeType='bool',
                  defaultValue=options.name_swap, keyable=False)
        c.select(options.head_joint, replace=True)
        return node

    def _offset_face_geometry(self, namespace):
        c = self._offset_face_raw
        fit = namespace+':FaceFitSkeleton'
        return original_offset_face_geometry(c.getAttr(fit+'.Face'), c.getAttr(fit+'.AllHead'))

    def _offset_face_lock(self, skin, head=None, *, lock=1):
        c = self._offset_face_raw
        for influence in c.listConnections(skin+'.matrix') or []:
            c.setAttr(influence+'.liw', lock)
        if head:
            c.setAttr(head+'.liw', 0)

    def import_original_offset_face(self, file, options, *, first_face=None, settings=None):
        self._require_transaction()
        if not isinstance(options, OriginalOffsetFaceImportOptions):
            raise ValueError('Offset Face 导入选项类型无效')
        c = self._offset_face_raw
        namespace, head = options.namespace, options.head_joint
        if c.namespace(exists=namespace):
            raise ValueError('Offset Face namespace 已存在：'+namespace)
        if not c.objExists(head) or c.nodeType(head) != 'joint':
            raise ValueError('Offset Face 目标 Head 关节不存在：'+head)
        existing = tuple(c.ls('OffsetFace', recursive=True) or [])
        if first_face is None:
            first_face = not existing
        self._transaction_changed = True
        settings = settings or self._write_offset_face_settings(file, options)
        c.file(file, i=True, namespace=namespace)
        for name in ('FaceGroup', 'OffsetFace', 'FaceDeformationSystem'):
            if not c.objExists(namespace+':'+name):
                raise ValueError(namespace+':'+name+' Not found')
        settings = c.rename(settings, namespace+':OffsetFaceImportSettings')
        c.parent(settings, namespace+':FaceGroup')
        matrix = c.getAttr(namespace+':OffsetFace.inverseMatrix')
        c.xform(namespace+':Head_M', matrix=matrix)
        if first_face:
            c.addAttr(namespace+':OffsetFace', longName='isFirstOffsetFace',
                      attributeType='bool', defaultValue=True, keyable=False)
        else:
            first = ''
            for node in existing:
                if c.attributeQuery('isFirstOffsetFace', node=node, exists=True):
                    first = node  # Native last marker wins.
            first_namespace = first.split(':')[0]
            first_head = c.getAttr(first_namespace+':OffsetFaceImportSettings.headJoint')
            if head == 'Head_L':
                position = c.xform(first_namespace+':Head_M', query=True, worldSpace=True, translation=True)
                c.xform(namespace+':Head_M', worldSpace=True,
                        translation=(-position[0], position[1], position[2]))
            else:
                temporary = c.createNode('transform', name='tempXformOffset')
                c.parent(temporary, first_head)
                c.setAttr(temporary+'.t', 0, 0, 0, type='float3')
                child = c.createNode('transform', name='tempXform', parent=head)
                child = c.parent(child, temporary)[0]
                position = c.getAttr(child+'.t')[0]
                c.getAttr(child+'.r')  # Native samples rotation but only adds translation.
                c.xform(namespace+':Head_M', relative=True, translation=position)
                c.delete(temporary)
        try:
            c.parent(namespace+':OffsetFace', namespace+':FaceGroup')
        except RuntimeError:
            pass  # Native catchQuiet is limited to this parent operation.
        c.parent(namespace+':Head_M', head)
        c.setAttr(head+'.drawStyle', 2)
        if c.objExists('|Group'):
            c.parent(namespace+':FaceGroup', '|Group')
        geometry = self._offset_face_geometry(namespace)
        c.select(clear=True)
        for original in geometry:
            target = original
            swapped = original_offset_face_name_swap(original, options)
            if swapped != original:
                if c.objExists(swapped):
                    target = swapped
                else:
                    c.warning('Tried to nameSwap "'+original+'" to "'+swapped+'", but that object is not found')
            c.select(target, replace=True)
            skin = related_skin_cluster(target)
            self._offset_face_lock(skin, head)
            influences = []
            for joint in c.listRelatives(namespace+':FaceJoint_M', allDescendents=True, type='joint') or []:
                if c.listConnections(joint+'.worldMatrix', source=False, destination=True):
                    influences.append(joint)
            for pose in c.ls(type='dagPose') or []:
                if pose.startswith(namespace):
                    c.delete(pose)
            # Native evaluates the accumulated -ai list in one skin edit.
            c.skinCluster(skin, edit=True, lockWeights=False, weight=0,
                          **({'addInfluence': influences} if influences else {}))
            c.select((namespace+':'+original, target), replace=True)
            copy_original_skin_weights_obey_locks(commands=c)
        children = c.listRelatives(namespace+':FaceFitSkeleton', children=True) or []
        if children:
            c.delete(children)
        nodes = c.ls(namespace+':*', namespace+':*:*', recursive=True) or []
        c.select(nodes, replace=True) if nodes else c.select(clear=True)
        c.select(namespace+':FaceAllSet', deselect=True)
        retained = c.listRelatives(namespace+':FaceGroup', allDescendents=True, fullPath=True) or []
        c.select((*retained, namespace+':FaceGroup'), deselect=True)
        c.select((namespace+':Head_M', namespace+':OffsetFace'), deselect=True)
        references = c.ls(type='reference') or []
        if references:
            c.select(references, deselect=True)
        if c.ls(selection=True):
            c.delete()
        for node in c.ls(selection=True, objectsOnly=True) or []:
            if c.objExists(node):
                c.delete(node)
        # Native unlocks the original AllHead names, even after name-swap.
        for original in geometry:
            if c.objExists(original):
                self._offset_face_lock(related_skin_cluster(original), lock=0)
        c.select(clear=True)
        return {'namespace': namespace, 'head_joint': head, 'geometry': geometry,
                'file': file, 'first_face': bool(first_face)}

    def read_original_offset_face_updates(self):
        c = self._offset_face_raw
        settings = list(c.ls('OffsetFaceImportSettings', recursive=True) or [])
        if not settings:
            raise ValueError('No Imported Faces Found in this scene')
        # Match native insertion order, rather than sorting by names.
        for index in range(len(settings)):
            node = settings[index]
            offset = node.replace('OffsetFaceImportSettings', 'OffsetFace', 1)
            if c.attributeQuery('isFirstOffsetFace', node=offset, exists=True):
                settings.remove(node)
                settings.insert(0, node)
        result = []
        for node in settings:
            values = {key: c.getAttr(node+'.'+key) for key in (
                'file', 'nameSpace', 'headJoint', 'nameSwap', 'nameSwapA', 'nameSwapB')}
            options = OriginalOffsetFaceImportOptions(values['nameSpace'], values['headJoint'],
                bool(values['nameSwap']), values['nameSwapA'], values['nameSwapB'])
            result.append((node, values['file'], options))
        return tuple(result)

    def confirm_original_offset_face_update(self, rows):
        return self._offset_face_raw.confirmDialog(title='Continue ?',
            message='Found '+str(len(rows))+' Imported Faces.\n\nUpdate ?',
            button=['Continue', 'Cancel'], defaultButton='Cancel', dismissString='Cancel') == 'Continue'

    def update_original_offset_faces(self, rows):
        self._require_transaction()
        c = self._offset_face_raw
        self._transaction_changed = True
        if c.objExists('OffsetFaceBatchImport'):
            c.delete('OffsetFaceBatchImport')
        batch = c.createNode('transform', name='OffsetFaceBatchImport')
        c.addAttr(batch, longName='faceNr', attributeType='long', defaultValue=0)
        result = []
        for index, (settings, file, options) in enumerate(rows):
            namespace = options.namespace
            c.setAttr(batch+'.faceNr', index+1)
            geometry = self._offset_face_geometry(namespace)
            for mesh in geometry:
                self._offset_face_lock(related_skin_cluster(mesh), options.head_joint)
            settings = c.parent(settings, world=True)[0]
            settings = c.rename(settings, 'OffsetFaceImportSettings')
            for pattern in (namespace+':*', namespace+':*:*'):
                nodes = c.ls(pattern, recursive=True) or []
                if nodes:
                    c.delete(nodes)
            for child in c.namespaceInfo(namespace, listOnlyNamespaces=True) or []:
                c.namespace(removeNamespace=child)
            if c.namespace(exists=namespace):
                c.namespace(removeNamespace=namespace)
            for mesh in geometry:
                c.select(mesh, replace=True)
                c.skinPercent(related_skin_cluster(mesh), normalize=True)
            c.refresh()
            result.append(self.import_original_offset_face(file, options,
                first_face=index == 0, settings=settings))
        c.delete(batch)
        return tuple(result)
