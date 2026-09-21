"""Owned orientation offsets, weighted by the existing FK/IK blend."""
from dataclasses import dataclass
from math import pi

from adv_py.core.character_registry import CharacterChannel, CharacterRegistryError


@dataclass(frozen=True)
class LimbOrientationBinding:
    limb: str
    side: str
    segment: str
    body: str
    settings: str
    blend: str
    constraint: str
    node: str

    def attribute(self,axis): return f'{self.segment}MatchOffset{axis}_{self.side}'
    def key(self,axis): return f'{self.limb}.ikOrientation.{self.side}.{self.segment}.rotate{axis}'


def bindings(registration):
    channels={c.key:c for c in registration.channels}
    body={j.path.rsplit('|',1)[-1]:j.path for j in registration.body}
    result=[]
    for limb,parts in (('arm',('Shoulder','Elbow')),('leg',('Hip','Knee'))):
        for side in ('R','L'):
            ch=channels[f'{limb}.settings.{limb}IkFk_{side}']
            for segment,part in zip(('upper','lower'),parts):
                result.append(LimbOrientationBinding(limb,side,segment,body[f'{part}_{side}'],ch.node,
                    ch.node+'.'+ch.attribute,f'AdvPy_{part}IKFKBlend_{side}',f'AdvPy_{limb.title()}{segment.title()}IKOrientation_{side}'))
    return tuple(result)


def orientation_channels(registration):
    return tuple(CharacterChannel(b.key(axis),b.settings,b.attribute(axis)) for b in bindings(registration) for axis in 'XYZ')


def preflight_orientation_install(host,registration):
    c=host._cmds
    if any('.ikOrientation.' in ch.key for ch in registration.channels):
        audit_orientation(host,registration)
        return
    for b in bindings(registration):
        if c.nodeType(b.constraint)!='orientConstraint':
            raise CharacterRegistryError('四肢朝向输出不是预期约束')
        names=[b.node]+[b.node+direction+axis for direction in ('In','Out') for axis in 'XYZ']
        if any(c.objExists(n) for n in names):
            raise CharacterRegistryError('四肢朝向补偿名称已占用')
        for axis in 'XYZ':
            plug=b.constraint+'.offset'+axis
            if c.objExists(b.settings+'.'+b.attribute(axis)) or c.getAttr(plug,lock=True) or c.listConnections(plug,s=True,d=False) or abs(c.getAttr(plug))>1e-9:
                raise CharacterRegistryError('四肢朝向偏移已有数据或被锁定')


def install_orientation(host,registration):
    host._require_transaction()
    preflight_orientation_install(host,registration)
    if any('.ikOrientation.' in ch.key for ch in registration.channels): return
    c=host._cmds;host._transaction_changed=True
    for b in bindings(registration):
        c.createNode('multiplyDivide',name=b.node,skipSelect=True)
        c.addAttr(b.node,longName='advPyOrientationOwner',dataType='string')
        c.setAttr(b.node+'.advPyOrientationOwner','adv_py.limb_orientation.v1',type='string',lock=True)
        c.setAttr(b.node+'.operation',1,lock=True)
        for axis in 'XYZ':
            c.addAttr(b.settings,longName=b.attribute(axis),attributeType='doubleAngle',keyable=True)
            for direction,factor in (('In',180/pi),('Out',pi/180)):
                name=b.node+direction+axis
                c.createNode('unitConversion',name=name,skipSelect=True)
                c.setAttr(name+'.conversionFactor',factor,lock=True)
            c.connectAttr(b.settings+'.'+b.attribute(axis),b.node+'In'+axis+'.input')
            c.connectAttr(b.node+'In'+axis+'.output',b.node+'.input1'+axis)
            c.connectAttr(b.blend,b.node+'.input2'+axis)
            c.connectAttr(b.node+'.output'+axis,b.node+'Out'+axis+'.input')
            c.connectAttr(b.node+'Out'+axis+'.output',b.constraint+'.offset'+axis)


def audit_orientation(host,registration):
    c=host._cmds
    present=tuple(ch for ch in registration.channels if '.ikOrientation.' in ch.key)
    if not present: return
    if present!=orientation_channels(registration):
        raise CharacterRegistryError('四肢朝向通道集合不完整')
    def connected(source,target):
        if not c.isConnected(source,target): raise CharacterRegistryError('四肢朝向补偿接线被替换')
    def outputs(plug,expected):
        actual=c.listConnections(plug,s=False,d=True,plugs=True) or []
        if {host._canonical_plug(p) for p in actual}!={host._canonical_plug(p) for p in expected}:
            raise CharacterRegistryError('四肢朝向补偿存在外部消费')
    for b in bindings(registration):
        if (not c.objExists(b.node) or c.nodeType(b.node)!='multiplyDivide'
                or c.referenceQuery(b.node,isNodeReferenced=True)
                or not c.objExists(b.node+'.advPyOrientationOwner')
                or c.getAttr(b.node+'.advPyOrientationOwner')!='adv_py.limb_orientation.v1'
                or c.getAttr(b.node+'.operation')!=1 or c.listConnections(b.node+'.operation',s=True,d=False)):
            raise CharacterRegistryError('四肢朝向补偿节点归属无效')
        for axis in 'XYZ':
            source=b.settings+'.'+b.attribute(axis)
            for direction,factor in (('In',180/pi),('Out',pi/180)):
                node=b.node+direction+axis
                if (not c.objExists(node) or c.nodeType(node)!='unitConversion'
                        or abs(c.getAttr(node+'.conversionFactor')-factor)>1e-12
                        or c.listConnections(node+'.conversionFactor',s=True,d=False)
                        or c.referenceQuery(node,isNodeReferenced=True)):
                    raise CharacterRegistryError('四肢朝向单位转换被替换')
            connected(source,b.node+'In'+axis+'.input')
            connected(b.node+'In'+axis+'.output',b.node+'.input1'+axis)
            connected(b.blend,b.node+'.input2'+axis)
            connected(b.node+'.output'+axis,b.node+'Out'+axis+'.input')
            connected(b.node+'Out'+axis+'.output',b.constraint+'.offset'+axis)
            outputs(source,[b.node+'In'+axis+'.input'])
            outputs(b.node+'In'+axis+'.output',[b.node+'.input1'+axis])
            outputs(b.node+'.output'+axis,[b.node+'Out'+axis+'.input'])
            outputs(b.node+'Out'+axis+'.output',[b.constraint+'.offset'+axis])


def match_orientation(host,registration,limb,side,before):
    from math import degrees
    from maya.api import OpenMaya as om
    wanted=dict(before.body_frames)
    for b in bindings(registration):
        if (b.limb,b.side)!=(limb,side): continue
        current=om.MTransformationMatrix(om.MMatrix(host._spine_world_frame(b.body)[0])).rotation(asQuaternion=True)
        target=om.MTransformationMatrix(om.MMatrix(wanted[b.body.rsplit('|',1)[-1]])).rotation(asQuaternion=True)
        rotation=(target*current.inverse()).asEulerRotation()
        for axis,value in zip('XYZ',(rotation.x,rotation.y,rotation.z)):
            host._cmds.setAttr(b.settings+'.'+b.attribute(axis),degrees(value))


def begin_orientation_match(host,limb,side):
    """Optional upgrade shared by static and animated matching."""
    c=host._cmds
    if not c.objExists(f'AdvPy_{limb.title()}Settings.upperMatchOffsetX_{side}'):
        return None
    registration=host.read_character_registration()
    channels=tuple(ch for ch in registration.channels if ch.key.startswith(f'{limb}.ikOrientation.{side}.'))
    if len(channels)!=6 or any(not c.getAttr(ch.node+'.'+ch.attribute,settable=True) for ch in channels):
        raise CharacterRegistryError('四肢朝向补偿通道不可静态写入')
    before=host.capture_character_pose(registration)
    host._transaction_changed=True
    for ch in channels:c.setAttr(ch.node+'.'+ch.attribute,0.)
    return registration,before


def finish_orientation_match(host,limb,side,state):
    if state is not None:
        registration,before=state
        match_orientation(host,registration,limb,side,before)
