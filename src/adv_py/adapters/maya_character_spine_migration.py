"""One Maya host for registered cross-spine animation and Skin migration."""
from .maya_body import MayaBodyBuildHost
from .maya_face import MayaFaceHost
from .maya_mocap_control import MayaMocapControlHost
from .maya_spine_original_promotion import MayaOriginalSpinePromotionHost


def _body_markers(matrix):
    origin=tuple(float(v) for v in matrix[12:15])
    return (origin,)+tuple(tuple(origin[i]+float(matrix[offset+i])
                                  for i in range(3)) for offset in (0,4,8))


class MayaCharacterSpineMigrationHost(MayaMocapControlHost, MayaFaceHost):
    def read_source_character_registration(self, namespace):
        return MayaBodyBuildHost(namespace=namespace).read_character_registration()


class MayaOriginalSkinSpineMigrationHost(MayaMocapControlHost):
    """One transaction boundary for original Skin and replacement controls."""

    def promoted_original_spine_ik_host(self, namespace):
        return MayaOriginalSkinSpineMigrationHost(namespace=namespace)

    def read_source_character_registration(self, namespace):
        return MayaBodyBuildHost(namespace=namespace).read_character_registration()

    def capture_registered_spine_mode_curve(self, source_namespace, registration):
        source=MayaBodyBuildHost(namespace=source_namespace)
        channel=next(ch for ch in registration.channels
                     if ch.key=='spine.spline.spineIkFk')
        plug=channel.node+'.'+channel.attribute
        driver=source._cmds.connectionInfo(plug,sourceFromDestination=True)
        if not driver or not source._character_direct_animation(driver):
            return None
        curve=driver.rsplit('.',1)[0]
        c=source._cmds
        return (tuple(float(v) for v in c.keyframe(curve,q=True,timeChange=True) or ()),
                tuple(float(v) for v in c.keyframe(curve,q=True,valueChange=True) or ()),
                tuple(c.keyTangent(curve,q=True,outTangentType=True) or ()))

    def match_registered_spine_fk_take(self, take, source_namespace):
        from math import sqrt
        from adv_py.core.character_registry import CharacterRegistryError

        self._require_transaction()
        target=self.install_character_spline_animation(take.target_registration)
        _,samples=self.capture_resampled_character_source(
            source_namespace,take.target_registration,take.fk_source_frames)
        c=self._cmds
        self._transaction_changed=True
        with self._character_sampling_time(preserve_modified=False) as seek:
            for frame,(_,pose) in zip(take.fk_frames,samples):
                seek(frame)
                for control,joint in zip(target.spine.fk_controls[1:],
                                         target.spine.body_joints[1:]):
                    name=joint.rsplit('|',1)[-1].rsplit(':',1)[-1]
                    matrix=pose[name]
                    root=self._spine_world_frame(target.spine.root_path)[0]
                    scale=sqrt(sum(value*value for value in root[:3]))
                    if scale<=1e-8:
                        raise CharacterRegistryError('混合脊柱 FK 机制组缩放无效')
                    for axis,offset in zip('XYZ',(0,4,8)):
                        c.setAttr(control+'.matchScale'+axis,
                            sqrt(sum(value*value for value in matrix[offset:offset+3]))/scale)
                    self._spine_set_world_rotation(control,matrix)
                    c.xform(control,worldSpace=True,translation=matrix[12:15])
                    for kind in ('rotate','translate','matchScale'):
                        for axis in 'XYZ':
                            c.setKeyframe(control,attribute=kind+axis,time=frame,
                                          inTangentType='linear',outTangentType='linear')
                for joint in target.spine.body_joints:
                    name=joint.rsplit('|',1)[-1].rsplit(':',1)[-1]
                    actual=self._spine_world_frame(joint)[0]
                    if max(abs(a-b) for a,b in zip(actual,pose[name]))>1e-4:
                        raise CharacterRegistryError('混合脊柱 FK 身体姿态不一致：'
                                                     +name+' frame='+str(frame))

    def _spine_mesh_points(self, mesh_path):
        from maya import cmds
        from maya.api import OpenMaya as om

        shapes = cmds.listRelatives(mesh_path, shapes=True,
                                    noIntermediate=True, fullPath=True) or []
        if len(shapes) != 1 or cmds.nodeType(shapes[0]) != 'mesh':
            raise ValueError('IK 迁移要求唯一的原多边形网格形状：'+mesh_path)
        selection = om.MSelectionList()
        selection.add(shapes[0])
        points = om.MFnMesh(selection.getDagPath(0)).getPoints(om.MSpace.kWorld)
        return tuple((float(p.x),float(p.y),float(p.z)) for p in points)

    def capture_registered_spine_mesh_take(self, meshes, frames):
        result = [[] for _ in meshes]
        with self._character_sampling_time() as seek:
            for frame in frames:
                seek(frame)
                for rows, mesh in zip(result, meshes):
                    rows.append(self._spine_mesh_points(mesh))
        return tuple(tuple(rows) for rows in result)

    def capture_registered_spine_ik_take(self, source_namespace, registration,
                                          meshes, body_names, frames):
        source = MayaBodyBuildHost(namespace=source_namespace)
        channels = []
        mesh_rows = [[] for _ in meshes]
        body_rows=[]
        body_paths={row.path.rsplit('|',1)[-1].rsplit(':',1)[-1]:row.path
                    for row in registration.body}
        with source._character_sampling_time() as seek:
            for frame in frames:
                seek(frame)
                channels.append(tuple((ch.key,float(source._cmds.getAttr(
                    ch.node+'.'+ch.attribute))) for ch in registration.channels))
                body_rows.append(tuple((name,_body_markers(source._cmds.xform(
                    body_paths[name],query=True,worldSpace=True,matrix=True)))
                    for name in body_names))
                for rows, mesh in zip(mesh_rows,meshes):
                    rows.append(self._spine_mesh_points(mesh))
        return (tuple(channels),tuple(tuple(rows) for rows in mesh_rows),
                tuple(body_rows))

    def capture_registered_spine_body_take(self, registration, body_names, frames):
        body_paths={row.path.rsplit('|',1)[-1].rsplit(':',1)[-1]:row.path
                    for row in registration.body}
        result=[]
        with self._character_sampling_time() as seek:
            for frame in frames:
                seek(frame)
                result.append(tuple((name,_body_markers(self._cmds.xform(
                    body_paths[name],query=True,worldSpace=True,matrix=True)))
                    for name in body_names))
        return tuple(result)

    def write_registered_spine_ik_take(self, take, source_namespace):
        from maya import cmds as raw
        from adv_py.core.character_registry import CharacterRegistryError
        from .maya_character_preservation import capture_curve
        from dataclasses import fields

        self._require_transaction()
        target = take.target_registration
        self.prepare_resampled_character_target(target,take.frames,take.frames[0])
        channels = {ch.key:ch for ch in target.channels}
        source = MayaBodyBuildHost(namespace=source_namespace)
        self._transaction_changed = True
        first = dict(take.channels[0])
        for source_channel in take.source_registration.channels:
            target_channel = channels[source_channel.key]
            source_plug = source.scene_address(source_channel.node)+'.'+source_channel.attribute
            target_plug = self.scene_address(target_channel.node)+'.'+target_channel.attribute
            source_output = raw.connectionInfo(source_plug,sourceFromDestination=True)
            target_output = raw.connectionInfo(target_plug,sourceFromDestination=True)
            if source_output and not source._character_direct_animation(
                    source._cmds.connectionInfo(source_channel.node+'.'
                        +source_channel.attribute,sourceFromDestination=True)):
                raise CharacterRegistryError('IK 来源控制包含非原生时间曲线：'
                                             +source_channel.key)
            if not source_output:
                for frame in take.frames:
                    self._cmds.setKeyframe(target_channel.node,
                        attribute=target_channel.attribute,time=frame,
                        value=first[source_channel.key],
                        inTangentType='linear',outTangentType='linear')
                continue
            source_curve = source_output.rsplit('.',1)[0]
            if not target_output:
                raise CharacterRegistryError('IK 目标动画通道未建立独占曲线：'
                                             +source_channel.key)
            if raw.copyKey(source_plug) != 1:
                raise CharacterRegistryError('IK 来源动画曲线复制失败：'
                                             +source_channel.key)
            raw.pasteKey(target_plug,option='replaceCompletely')
            target_curve = raw.connectionInfo(target_plug,
                                              sourceFromDestination=True).rsplit('.',1)[0]
            for attribute in ('preInfinity','postInfinity'):
                raw.setAttr(target_curve+'.'+attribute,
                            raw.getAttr(source_curve+'.'+attribute))
            before = capture_curve(source,source_curve)
            after = capture_curve(self,target_curve)
            ignored={'node','uuid','input','outputs'}
            if not before.weighted:
                ignored.update(('in_weights','out_weights'))
            properties = tuple(field for field in fields(type(before))
                if field.name not in ignored)
            if (not self._character_direct_animation(
                    self._cmds.connectionInfo(target_channel.node+'.'
                        +target_channel.attribute,sourceFromDestination=True))
                    or any(getattr(before,field.name)!=getattr(after,field.name)
                           for field in properties)):
                raise CharacterRegistryError('IK 目标动画曲线未完整保留：'
                                             +source_channel.key)
        with self._character_sampling_time(preserve_modified=False) as seek:
            for frame, values in zip(take.frames,take.channels):
                seek(frame)
                for key,wanted in values:
                    channel=channels[key]
                    actual=float(self._cmds.getAttr(channel.node+'.'+channel.attribute))
                    if abs(actual-wanted)>1e-6:
                        raise CharacterRegistryError('IK 控制曲线复制后数值不一致：'
                                                     +key+' frame='+str(frame))

    def original_skin_handoff_host(self):
        return MayaOriginalSpinePromotionHost()

    def mark_original_skin_mutation(self):
        self._require_transaction()
        self._transaction_changed = True
