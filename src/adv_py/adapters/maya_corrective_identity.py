"""Resolve source FK roles through the Python Body's existing registration."""
from adv_py.core.character_registry import REGISTRY_NAME, decode_registration


class MayaCorrectiveIdentityMixin:
    def original_corrective_body_registration(self):
        c=self._cmds
        plug=REGISTRY_NAME+".advPyRegistryDocument"
        return decode_registration(c.getAttr(plug)) if c.objExists(plug) else None

    def original_corrective_fk_bindings(self):
        """Return source joint -> actual primary FK, excluding Extra layers."""
        registration=self.original_corrective_body_registration()
        if registration is None:
            return {}
        bindings={}
        for channel in registration.channels:
            if not channel.key.startswith("generic.fk.") or ".extra." in channel.key:
                continue
            role=channel.key[len("generic.fk."):].split(".",1)[0]
            if role.endswith("FK"):
                bindings[role[:-2]]=self._original_restore_leaf(channel.node)
        for spline in (registration.spine,*registration.additional_spines):
            if spline is not None:
                for joint,control in zip(spline.body_joints,spline.fk_controls):
                    bindings[self._original_restore_leaf(joint)]=self._original_restore_leaf(control)
        return bindings

    def original_corrective_fk_for_joint(self, joint):
        original="FK"+joint
        if self._cmds.objExists(original):
            return original
        return self.original_corrective_fk_bindings().get(joint,joint)

    def original_corrective_joint_for_fk(self, control):
        leaf=self._original_restore_leaf(control)
        for joint,fk in self.original_corrective_fk_bindings().items():
            if fk==leaf:
                return joint
        if leaf.startswith("FK") and self._cmds.objExists(leaf[2:]):
            return leaf[2:]
        return leaf

    def original_corrective_primary_fk(self, control):
        """Apply source FK/Extra/Root filtering to the registered Body roles."""
        leaf=self._original_restore_leaf(control)
        c=self._cmds
        if leaf.startswith("FK") and not leaf.startswith(("FKExtra","FKRoot")):
            return bool(c.objExists("ControlSet") and c.sets(control,isMember="ControlSet"))
        if c.objExists(control+".advPyNoControl") and c.getAttr(control+".advPyNoControl"):
            return False
        bindings=self.original_corrective_fk_bindings()
        return any(fk==leaf and not joint.startswith("Root") for joint,fk in bindings.items())

    def original_corrective_pose_controls(self):
        c=self._cmds
        controls=[]
        for name in ("ControlSet","FaceControlSet"):
            if c.objExists(name):
                controls.extend(c.sets(name,query=True) or [])
        # The Python Body registers primary and Extra as distinct channels;
        # legacy ControlSet scenes can contain only the Extra transforms.
        registration=self.original_corrective_body_registration()
        if registration is not None:
            controls.extend(channel.node for channel in registration.channels)
        return tuple(dict.fromkeys(controls))

    def set_original_corrective_fk(self, control):
        """asCBDCreateTestAnim switches only the selected FK's limb."""
        c=self._cmds
        switch=self.find_original_fkik_control(control)
        if switch and c.objExists(switch+".FKIKBlend"):
            c.setAttr(switch+".FKIKBlend",0)
            return
        registration=self.original_corrective_body_registration()
        if registration is None:
            return
        leaf=self._original_restore_leaf(control)
        joint=self.original_corrective_joint_for_fk(control)
        channels={channel.key:channel for channel in registration.channels}
        for limb in registration.source_limbs:
            if any(self._original_restore_leaf(row.control)==leaf
                   or self._original_restore_leaf(row.body)==joint for row in limb.joints):
                channel=channels[limb.blend_key]
                c.setAttr(channel.node+"."+channel.attribute,0)
                return

    def set_original_corrective_all_fk(self):
        c=self._cmds
        for control in c.sets("ControlSet",query=True) or []:
            if c.objExists(control+".FKIKBlend"):
                c.setAttr(control+".FKIKBlend",0)
        registration=self.original_corrective_body_registration()
        if registration is not None:
            channels={channel.key:channel for channel in registration.channels}
            for limb in registration.source_limbs:
                channel=channels[limb.blend_key]
                c.setAttr(channel.node+"."+channel.attribute,0)
