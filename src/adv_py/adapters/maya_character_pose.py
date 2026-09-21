from contextlib import contextmanager

from adv_py.core.character_pose import CharacterPose
from adv_py.core.character_registry import CharacterRegistryError


class MayaCharacterPoseMixin:
    def preflight_character_pose(self,registration):
        c=self._cmds
        self._validate_character_registration(registration)
        if c.ls(type="animLayer") or c.currentUnit(q=True,angle=True)!="deg" or c.currentUnit(q=True,linear=True)!="cm":
            raise CharacterRegistryError("静态全身姿态要求 cm / degree，且无动画层")
        if not c.undoInfo(q=True,state=True):
            raise CharacterRegistryError("静态全身姿态要求 Undo 开启")
        for channel in registration.channels:
            plug=channel.node+"."+channel.attribute
            if c.getAttr(plug,lock=True) or c.listConnections(plug,s=True,d=False) or not c.getAttr(plug,settable=True):
                raise CharacterRegistryError("静态姿态通道锁定、动画或外部输入："+channel.key)
        for spec in registration.spaces.spaces:
            self.preflight_control_space_switch(spec)

    def capture_character_pose(self,registration):
        c=self._cmds
        return CharacterPose(registration.compatibility_digest,
            tuple((ch.key,float(c.getAttr(ch.node+"."+ch.attribute))) for ch in registration.channels),
            tuple((s.key,self.capture_control_space_mode(s)) for s in registration.spaces.spaces),
            tuple((s.key+"."+str(i),self._spine_world_frame(target)[0]) for s in registration.spaces.spaces for i,target in enumerate(s.targets)),
            tuple((j.path.rsplit("|",1)[-1],self._spine_world_frame(j.path)[0]) for j in registration.body))

    def write_character_pose(self,registration,pose):
        self._require_transaction()
        self.preflight_character_pose(registration)
        c=self._cmds
        selection=c.ls(sl=True,long=True) or []
        modes=dict(pose.spaces)
        frames=dict(pose.space_frames)
        self._transaction_changed=True
        try:
            # All controls first establish Global and torso sources. Space target
            # frames then establish the actual stored offsets, even if mode agrees.
            for channel,(_,value) in zip(registration.channels,pose.channels):
                c.setAttr(channel.node+"."+channel.attribute,value)
            for spec in registration.spaces.spaces:
                c.delete(spec.constraint_names)
                for i,(target,name) in enumerate(zip(spec.targets,spec.constraint_names)):
                    matrix=frames[spec.key+"."+str(i)]
                    if not spec.rotation_only:
                        c.xform(target,worldSpace=True,translation=matrix[12:15])
                    self._spine_set_world_rotation(target,matrix)
                    self._create_control_space_constraint(spec,target,name,modes[spec.key])
        finally:
            c.select(selection,replace=True) if selection else c.select(clear=True)

    def preflight_character_keyframe(self,registration):
        c=self._cmds
        self._validate_character_registration(registration)
        if c.ls(type="animLayer") or c.currentUnit(q=True,angle=True)!="deg" or c.currentUnit(q=True,linear=True)!="cm" or not c.undoInfo(q=True,state=True):
            raise CharacterRegistryError("全身写键要求 cm / degree、Undo 开启且无动画层")
        for channel in registration.channels:
            plug=channel.node+"."+channel.attribute
            if c.getAttr(plug,lock=True) or not c.getAttr(plug,keyable=True):
                raise CharacterRegistryError("全身写键目标锁定或不可写键："+channel.key)
            source=c.connectionInfo(plug,sourceFromDestination=True)
            if source:
                if not self._character_direct_animation(source):
                    raise CharacterRegistryError("写键目标有不支持的外部输入")
                curve=source.rsplit(".",1)[0]
                if c.referenceQuery(curve,isNodeReferenced=True) or any(c.lockNode(curve,q=True,lock=True) or []):
                    raise CharacterRegistryError("动画曲线被引用或锁定")
                outputs=c.listConnections(curve+".output",s=False,d=True,plugs=True) or []
                if len(outputs)!=1:
                    raise CharacterRegistryError("动画曲线存在外部共享输出")
        for spec in registration.spaces.spaces:
            self.preflight_control_space_switch(spec)

    def capture_character_key_state(self,registration):
        c=self._cmds
        rows=[]
        for channel in registration.channels:
            plug=channel.node+"."+channel.attribute
            source=c.connectionInfo(plug,sourceFromDestination=True)
            rows.append((channel.key,source,tuple(c.keyframe(plug,q=True,timeChange=True) or []),
                         tuple(c.keyframe(plug,q=True,valueChange=True) or [])))
        return (float(c.currentTime(q=True)),tuple(rows))

    def key_character_pose(self,registration,pose):
        self._require_transaction()
        self.preflight_character_keyframe(registration)
        c=self._cmds
        frame=c.currentTime(q=True)
        self._transaction_changed=True
        for channel,(_,value) in zip(registration.channels,pose.channels):
            c.setKeyframe(channel.node,attribute=channel.attribute,time=frame,value=value,
                          inTangentType="linear",outTangentType="linear")
        c.currentTime(frame,edit=True,update=True)

    def character_time_unit(self):
        return self._cmds.currentUnit(q=True,time=True)

    @contextmanager
    def _character_sampling_time(self, *, preserve_modified=True):
        c=self._cmds
        original=c.currentTime(q=True)
        modified=c.file(q=True,modified=True)
        def seek(frame):
            undo=c.undoInfo(q=True,state=True)
            c.undoInfo(stateWithoutFlush=False)
            try:
                c.currentTime(frame,edit=True,update=True)
            finally:
                c.undoInfo(stateWithoutFlush=undo)
        try:
            yield seek
        finally:
            seek(original)
            # Maya marks time changes as file edits even after restoring time.
            # Sampling owns time only; the caller verifies the rig/curve snapshot.
            if preserve_modified and not modified:
                c.file(modified=False)

    def sample_character_animation(self,registration,frames):
        with self._character_sampling_time() as seek:
            samples=[]
            for frame in frames:
                seek(frame)
                samples.append((float(frame),self.capture_character_pose(registration)))
            return tuple(samples)

    def write_character_animation(self,registration,samples):
        self._require_transaction()
        self.preflight_character_keyframe(registration)
        self._transaction_changed=True
        c=self._cmds
        # Explicit key times do not require scene-time changes while writing.
        for frame,pose in samples:
            for channel,(_,value) in zip(registration.channels,pose.channels):
                c.setKeyframe(channel.node,attribute=channel.attribute,time=frame,value=value,
                              inTangentType="linear",outTangentType="linear")
        with self._character_sampling_time() as seek:
            seek(c.currentTime(q=True))

    def match_character_spine_samples(self,registration,frames,mode):
        self._require_transaction()
        self.preflight_character_keyframe(registration)
        c=self._cmds
        samples=[]
        original_frames=dict(self.sample_character_animation(registration,frames))
        self.ensure_precise_body_spine_solver(registration.spine)
        with self._character_sampling_time(preserve_modified=False) as seek:
            for frame in frames:
                seek(frame)
                before=self.capture_character_pose(registration)
                values=[(ch.node+'.'+ch.attribute,value) for ch,(_,value) in zip(registration.channels,before.channels)]
                connections=[]
                self._transaction_changed=True
                try:
                    # Curves stay intact. Temporarily expose scalar controls to
                    # the existing static solver, then reconnect the same plugs.
                    for plug,value in values:
                        source=c.connectionInfo(plug,sourceFromDestination=True)
                        if source:
                            c.disconnectAttr(source,plug)
                            connections.append((source,plug))
                        c.setAttr(plug,value)
                    value=self.preflight_body_spine_match(registration.spine,mode)
                    if value!=(1. if mode=='ik' else 0.):
                        self.match_body_spine(registration.spine,mode)
                    after=self.capture_character_pose(registration)
                    reference=original_frames[float(frame)]
                    error=max(abs(a-b) for (_,left),(_,right) in zip(reference.body_frames,after.body_frames) for a,b in zip(left,right))
                    if error>1e-4:
                        joint=max(zip(reference.body_frames,after.body_frames),key=lambda pair:max(abs(a-b) for a,b in zip(pair[0][1],pair[1][1])))[0][0]
                        raise RuntimeError(f"脊柱动画匹配改变了全身世界姿态：frame={frame}, joint={joint}, error={error}")
                    samples.append((float(frame),after))
                finally:
                    for plug,value in values:
                        # A partial disconnect failure may leave other channels connected.
                        if not c.connectionInfo(plug,sourceFromDestination=True):
                            c.setAttr(plug,value)
                    for source,plug in connections:
                        c.connectAttr(source,plug)
                seek(frame)
        return tuple(samples)
