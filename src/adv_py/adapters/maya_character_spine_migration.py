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

    def write_registered_spine_ik_take(self, take):
        self._require_transaction()
        target = take.target_registration
        self.prepare_resampled_character_target(target,take.frames,take.frames[0])
        channels = {ch.key:ch for ch in target.channels}
        c = self._cmds
        self._transaction_changed = True
        for frame, values in zip(take.frames,take.channels):
            for key,value in values:
                ch = channels.get(key)
                if ch is not None:
                    c.setKeyframe(ch.node,attribute=ch.attribute,time=frame,
                                  value=value,inTangentType='linear',
                                  outTangentType='linear')

    def original_skin_handoff_host(self):
        return MayaOriginalSpinePromotionHost()

    def mark_original_skin_mutation(self):
        self._require_transaction()
        self._transaction_changed = True
