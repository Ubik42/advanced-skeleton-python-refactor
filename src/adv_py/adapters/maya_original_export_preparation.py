"""Native export preparations, without invoking ADV MEL business procedures."""
from fnmatch import fnmatchcase
from dataclasses import replace

from adv_py.core.original_roblox_export import plan_roblox_head_export
from adv_py.core.character_registry import REGISTRY_NAME, encode_registration
from adv_py.core.source_limb_animation import retain_source_limb_body_rows
from .maya_driving_systems import MayaDrivingSystemsHost
from .maya_original_control_identity import registration, leaf
from .maya_game_registration import _write_members, scene_ids, remember_generated_nodes
from .maya_driving_registration import _write_string


class MayaOriginalExportPreparationHost(MayaDrivingSystemsHost):
    def _unique(self, name, node_type):
        # Resolve through the host's namespace-aware command facade, just as
        # the subsequent export operation does. This host does not inherit
        # the custom-controller adapter's similarly named helper.
        matches = self._cmds.ls(name, long=True, type=node_type) or []
        if len(matches) != 1:
            raise ValueError('导出来源节点不存在或名称不唯一：' + name)
        return matches[0]

    def preflight_export_preparation(self, operation):
        c = self._cmds
        if operation == 'delete_unused_end_joints':
            self._unique('DeformationSystem', 'transform')
            if c.objExists('root.skinTransferred'):
                raise ValueError('蒙皮已转移到 Unreal Skeleton，不能删除原版末端关节')
        elif operation == 'rebuild_dag_pose':
            if not c.objExists('|root'):
                self._unique('Root_M', 'joint')
            self._unique('DeformationSystem', 'transform')

    def _remember_export_preparation(self, before, added=(), *, retired=(), deleted_cache_targets=()):
        if before is None:
            return
        c = self._cmds
        removed = {node.path for node in before.nodes if not c.objExists(node.path)}
        from .maya_game_scaling_state import remember_removed_joints
        remember_removed_joints(self, removed)
        body = tuple(joint for joint in before.body if c.objExists(joint.path))
        channels = tuple(channel for channel in before.channels if c.objExists(channel.node + '.' + channel.attribute))
        user_plugs = {channel.node + '.' + channel.attribute for channel in channels}
        from .maya_original_quick_ik_state import audit as audit_quick_ik
        from .maya_source_name_matcher_session import allowed_input, audit as audit_mocap
        from .maya_source_native_animation import audit as audit_native
        animation_edges = audit_quick_ik(self) | audit_mocap(self) | audit_native(self)
        # Registry members are transform/joint identities. Native dagPose and
        # animation DG nodes are retained in AllSet/FaceAllSet instead.
        added = tuple(path for path in added if c.nodeType(path) in ('transform', 'joint'))
        paths = tuple(dict.fromkeys((*[node.path for node in before.nodes if node.path not in removed], *added)))
        nodes = tuple(replace(node, inputs=tuple((attr, source) for attr, source in node.inputs
            if not (node.path + '.' + attr in user_plugs and (
                self._character_direct_animation(source) or
                allowed_input(self, animation_edges, node.uuid, attr, source)))))
            for node in (self.capture_character_registration_node(path) for path in paths))
        spaces = replace(before.spaces, spaces=tuple(spec for spec in before.spaces.spaces
            if all(c.objExists(node) for node in (*spec.targets, *spec.sources))))
        retired_paths = {row.path for row in (*before.retired_body, *retired)}
        limbs = retain_source_limb_body_rows(before.source_limbs,
                                             (joint.path for joint in body),
                                             retired_body_paths=retired_paths)
        channel_pairs = {(channel.node, channel.attribute) for channel in channels}
        limbs = tuple(replace(binding, reset_attributes=tuple(
            item for item in binding.reset_attributes
            if (binding.ik_control, item[0]) in channel_pairs)) for binding in limbs)
        if retired:
            from adv_py.core.character_body_retirement import retire_body_correspondence
            updated = retire_body_correspondence(before,retired,nodes,channels)
            updated = replace(updated,spaces=spaces,source_limbs=limbs)
        else:
            updated = replace(before, body=body, channels=channels, nodes=nodes,
                              spaces=spaces, source_limbs=limbs)
        if deleted_cache_targets:
            raw=getattr(c,'raw',c)
            if any(raw.ls(identity,long=True) for identity in deleted_cache_targets):
                raise ValueError('原版清理后缓存目标身份仍然存在，不能丢弃记录')
            from adv_py.core.character_body_retirement import forget_deleted_retirement_inputs
            updated=forget_deleted_retirement_inputs(updated,deleted_cache_targets)
        if len(body) != len(before.body):
            for owner in (before.body_root, before.container):
                plug = owner + '.advPyBodyJointCount'
                if c.objExists(plug):
                    c.setAttr(plug, lock=False)
                    c.setAttr(plug, len(body), lock=True)
        _write_members(self, nodes)
        _write_string(c, REGISTRY_NAME + '.advPyRegistryDocument', encode_registration(updated))

    def prepare_original_export(self, operation):
        self._require_transaction()
        c = self._cmds
        if operation == 'rebuild_dag_pose' and not self.confirm_original_control_build_pose():
            return None
        before = registration(self)
        if before is not None:
            # Freeze provenance only from the actual, fully validated original
            # graph. A modified node must not be legitimized by deleting it.
            before=self.read_character_registration()
        self._transaction_changed = True
        if operation == 'delete_unused_end_joints':
            candidates = []
            native_candidates = []
            # Preserve MEL's actual deletion addresses and traversal. Full
            # paths are separately resolved for portable registration only.
            for joint in c.listRelatives('DeformationSystem', allDescendents=True, type='joint') or []:
                fit = leaf(joint)[:-2]
                if not c.objExists(fit) or c.listRelatives(fit, allDescendents=True, type='joint'):
                    continue
                if c.objExists(fit + '.control') and c.getAttr(fit + '.control'):
                    continue
                matches=c.ls(joint,long=True,type='joint') or []
                if len(matches)!=1:
                    raise ValueError('原版末端清理关节不存在或名称不唯一：'+joint)
                candidates.append(matches[0])
                native_candidates.append(joint)
            captured = ()
            if before is not None:
                from .maya_character_body_retirement import capture
                registered = {joint.path for joint in before.body}
                captured = capture(self,before,tuple(path for path in candidates if path in registered))
            for joint in native_candidates:
                c.delete(joint)
            retired = ()
            if captured:
                from .maya_character_body_retirement import finish
                retired = finish(self,captured)
            self._remember_export_preparation(before,retired=retired)
            return tuple(candidates)
        if operation == 'delete_static_channels':
            from .maya_static_animation_boundary import capture,finish
            animation=capture(self)
            selected = c.ls(selection=True, long=True) or []
            c.delete(selected, staticChannels=True, unitlessAnimationCurves=False,
                     hierarchy='none', controlPoints=False, shape=True)
            finish(self,animation)
            self._remember_export_preparation(before)
            return tuple(selected)
        if operation == 'rebuild_dag_pose':
            ids = scene_ids(self)
            deleted_pose_ids=[]
            for pose in c.ls(type='dagPose') or []:
                if not fnmatchcase(leaf(pose), '*uildPose*'):
                    deleted_pose_ids.extend(c.ls(pose,uuid=True) or ())
                    c.delete(pose)
            root = '|root' if c.objExists('|root') else 'Root_M'
            c.select(root, hierarchy=True, replace=True)
            constraints = c.ls('*Constraint*', selection=True) or []
            if constraints:
                c.select(constraints, deselect=True)
            c.select('DeformationSystem', add=True)
            pose = c.dagPose(save=True, selection=True, bindPose=True, name='bindPose')
            c.select(clear=True)
            added = remember_generated_nodes(self, ids)
            self._remember_export_preparation(before, added,
                deleted_cache_targets=tuple(deleted_pose_ids))
            return pose
        raise ValueError('未知原版导出准备操作')

    def preflight_roblox_dynamic_head(self, geometry):
        self._unique('ctrlRobloxHead_M', 'transform')
        c = getattr(self._cmds, 'raw', self._cmds)
        if not geometry or len(c.ls(geometry, long=True) or []) != 1:
            raise ValueError('请选择 Face 输入中的真实几何对象')

    def prepare_roblox_dynamic_head(self, geometry):
        self._require_transaction()
        c = self._cmds
        raw = getattr(c, 'raw', c)
        self._transaction_changed = True
        c.currentTime(0)
        curves = c.listConnections('ctrlRobloxHead_M', source=True,
                                   destination=False, type='animCurve') or []
        if curves:
            c.delete(curves)
        # Face input geometry may be a user's model in a separate namespace.
        # Its address is explicit; never reinterpret it as a rig-owned name.
        for attr in raw.listAttr(geometry, userDefined=True) or []:
            if fnmatchcase(attr, 'Frame[0-9]*'):
                raw.deleteAttr(geometry + '.' + attr)
        if not raw.attributeQuery('RootFaceJoint', node=geometry, exists=True):
            raw.addAttr(geometry, longName='RootFaceJoint', dataType='string')
        raw.setAttr(geometry + '.RootFaceJoint', 'FaceJoint_M', type='string')
        plan = plan_roblox_head_export(c.listAttr('ctrlRobloxHead_M', userDefined=True, scalar=True) or [])
        raw.addAttr(geometry, longName='Frame0', dataType='string')
        raw.setAttr(geometry + '.Frame0', 'Neutral', type='string')
        # Keep all three keys for each channel, including the last zero key
        # beyond the playback end. The native timeline deliberately ends at N.
        for index, frame in enumerate(plan.frames[1:]):
            for key in plan.keys[index * 3:index * 3 + 3]:
                c.setKeyframe('ctrlRobloxHead_M.' + key.channel, value=key.value, time=key.frame)
            raw.addAttr(geometry, longName=frame.attribute, dataType='string')
            raw.setAttr(geometry + '.' + frame.attribute, frame.label, type='string')
        c.playbackOptions(minTime=0, animationStartTime=0,
                          animationEndTime=plan.playback_end, maxTime=plan.playback_end)
        c.select('ctrlRobloxHead_M', replace=True)
        c.currentTime(plan.current_frame)
        if c.objExists('FaceAllSet'):
            generated = c.listConnections('ctrlRobloxHead_M', source=True,
                                           destination=False, type='animCurve') or []
            if generated:
                c.sets(generated, add='FaceAllSet')
        return plan
