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
