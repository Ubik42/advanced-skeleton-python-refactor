"""Original ControlMeshes influence-to-control dispatch and registered FK identity."""
import re
from .maya_original_control_identity import command_registration, fk_bindings

class SourceGeometryControlMapping:
    def __init__(self,host):
        self.host=host;self.c=host.cmds;self.bindings={}
        saved=command_registration(self.c,host.namespace)
        self.bindings={joint:host._name(control) for joint,control in fk_bindings(saved).items()}

    def fk(self,joint):
        leaf=self.host._leaf(joint);candidate=self.host._name('FK'+leaf)
        if self.c.objExists(candidate):return candidate
        return self.bindings.get(leaf)

    def face_control(self,joint):
        leaf=self.host._leaf(joint);name=leaf.replace('Joint','',1)
        match=re.fullmatch(r'(upper|lower)(LipJoint|LidMain|LidOuter)(\d+)(_.)',leaf)
        if match:
            upper,kind,number,side=match.groups();lid='Lip' if kind=='LipJoint' else ('LidOuter' if kind=='LidOuter' else 'Lid')
            pattern=upper+('LipJoint' if kind=='LipJoint' else 'LidMain')+'*'+side
            total=len(self.c.ls(self.host._name(pattern),type='joint') or [])
            if total:
                fraction=int(number)/total
                if lid=='Lip':
                    letter='' if fraction<.26 or fraction>=1. else ('B' if fraction>=.75 else 'A')
                    if fraction<.26:side='_M'
                    name=upper+lid+letter+side
                else:
                    location='Inner' if fraction<.4 else ('' if fraction<.6 else 'Outer')
                    if fraction<.2 or fraction>.8:upper='';location=location.lower()
                    if fraction==.8:location=''
                    name=upper+location+lid+side
        return self.host._name(name)

    def anchor(self,joint,*,cut_up):
        c=self.c;leaf=self.host._leaf(joint);control=self.face_control(joint);face_set=self.host._name('FaceControlSet')
        fk=self.fk(joint)
        if leaf in ('upperFaceJoint_M','middleFaceJoint_M','lowerFaceJoint_M'):return self.fk('Head_M')
        if fk and 'Slider' not in leaf and (not re.search(r'Part\d',leaf) or cut_up):return fk
        if re.match(r'(Eye|Iris|Pupil)Joint_',leaf):return self.host._name(leaf.replace('Joint','',1))
        if c.objExists(control) and c.objExists(face_set) and c.sets(control,isMember=face_set):
            return self.fk('Head_M') if cut_up else control
        current=joint
        for _ in range(99):
            parents=c.listRelatives(current,parent=True,fullPath=True) or []
            if not parents:break
            current=parents[0];parent_leaf=self.host._leaf(current);fk=self.fk(current)
            if fk and not re.search(r'Part\d',parent_leaf):return fk
            if cut_up and re.search(r'Part\d',parent_leaf):return current
        return None
