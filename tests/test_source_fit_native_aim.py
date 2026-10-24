"""Native command ordering and DAG identity; no simulated rotation accuracy."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from adv_py.adapters.maya_source_fit_aim import aim_joint
from adv_py.adapters.maya_source_fit_orientation import update_orientations
from adv_py.core.fit_orientation import FitOrientationSnapshot,FitOrientationAxisConfiguration
from adv_py.core.fit_container import FitUpAxis
from adv_py.core.fit_ik import fit_joint_ik_info
from test_source_fit_pole_vectors import arm_hierarchy


class DagCommands:
    """Preserve reparent identities and positions, record actual command flags."""
    def __init__(self,hierarchy):
        self.nodes={}
        self.calls=[]
        self.incoming={}
        self.locks={}
        self.next_id=0
        self.add('|FitSkeleton','transform',(0.,0.,0.))
        for node in hierarchy.joints:self.add(node.path,'joint',node.world_position)

    def add(self,path,kind,position):
        self.next_id+=1
        parent_path=path.rsplit('|',1)[0]
        parent=self.resolve(parent_path) if parent_path else None
        identity='node-'+str(self.next_id)
        self.nodes[identity]=dict(leaf=path.rsplit('|',1)[-1],parent=parent,kind=kind,
            position=tuple(position),attrs={'rotate':(0.,0.,0.),'jointOrient':(0.,0.,0.)})
        return identity

    def path(self,identity):
        node=self.nodes[identity]
        return (self.path(node['parent']) if node['parent'] else '')+'|'+node['leaf']

    def resolve(self,address):
        matches=[identity for identity,node in self.nodes.items()
                 if address in (identity,self.path(identity),node['leaf'])]
        if len(matches)!=1:raise RuntimeError('Not unique: '+str(address))
        return matches[0]

    def ls(self,address,**flags):
        try:identity=self.resolve(address)
        except RuntimeError:return []
        return [identity if flags.get('uuid') else self.path(identity)]

    def objExists(self,address):
        node,separator,attribute=address.partition('.')
        try:identity=self.resolve(node)
        except RuntimeError:return False
        return not separator or attribute in self.nodes[identity]['attrs']

    def attributeQuery(self,attribute,*,node,**flags):
        return attribute in self.nodes[self.resolve(node)]['attrs']

    def getAttr(self,plug,**flags):
        address,attribute=plug.split('.',1)
        identity=self.resolve(address)
        node=self.nodes[identity]
        if flags.get('lock'):return self.locks.get((identity,attribute),False)
        if attribute=='translate':
            parent=self.nodes[node['parent']]['position'] if node['parent'] else (0.,0.,0.)
            return [tuple(a-b for a,b in zip(node['position'],parent))]
        value=node['attrs'].get(attribute,0.)
        return [value] if isinstance(value,tuple) else value

    def setAttr(self,plug,*values,**flags):
        address,attribute=plug.split('.',1)
        identity=self.resolve(address)
        if 'lock' in flags:self.locks[identity,attribute]=flags['lock']
        if values:
            self.nodes[identity]['attrs'][attribute]=tuple(values) if len(values)>1 else values[0]
        self.calls.append(('set',identity,attribute,values,flags))

    def addAttr(self,address,**flags):self.nodes[self.resolve(address)]['attrs'][flags['longName']]=0

    def listRelatives(self,address,**flags):
        identity=self.resolve(address)
        if flags.get('parent'):
            parent=self.nodes[identity]['parent']
            return [self.path(parent)] if parent else []
        result=[node for node,values in self.nodes.items() if values['parent']==identity]
        if flags.get('allDescendents'):
            result=[node for node in self.nodes if self.path(node).startswith(self.path(identity)+'|')]
        if flags.get('type'):
            result=[node for node in result if self.nodes[node]['kind']==flags['type']
                    or flags['type']=='transform' and self.nodes[node]['kind']=='joint']
        return [self.path(node) for node in result]

    def createNode(self,kind,**flags):
        parent=self.path(self.resolve(flags['parent'])) if flags.get('parent') else ''
        leaf=flags.get('name','transform'+str(self.next_id+1))
        position=self.nodes[self.resolve(parent)]['position'] if parent else (0.,0.,0.)
        identity=self.add(parent+'|'+leaf,kind,position)
        self.calls.append(('create',identity,kind))
        return self.path(identity)

    def parent(self,addresses,parent=None,**flags):
        if isinstance(addresses,str):addresses=(addresses,)
        identities=tuple(self.resolve(address) for address in addresses)
        target=None if flags.get('world') else self.resolve(parent)
        for identity in identities:
            self.nodes[identity]['parent']=target
            self.calls.append(('parent',identity,target))
        return [self.path(identity) for identity in identities]

    def xform(self,address,**flags):
        identity=self.resolve(address)
        if flags.get('query'):return self.nodes[identity]['position']
        self.nodes[identity]['position']=tuple(flags['translation'])
        self.calls.append(('position',identity,tuple(flags['translation'])))

    def move(self,*values,**flags):
        address=values[-1]
        node,_,attribute=address.partition('.')
        self.calls.append(('move',self.resolve(node),attribute,tuple(values[:-1]),flags))

    def listConnections(self,plug,**flags):
        node,attribute=plug.split('.',1)
        source=self.incoming.get((self.resolve(node),attribute))
        return [source] if source else []

    def disconnectAttr(self,source,destination):
        node,attribute=destination.split('.',1)
        identity=self.resolve(node)
        self.incoming.pop((identity,attribute))
        self.calls.append(('disconnect',identity,attribute))

    def connectAttr(self,source,destination,**flags):
        node,attribute=destination.split('.',1)
        identity=self.resolve(node)
        self.incoming[identity,attribute]=source
        self.calls.append(('connect',identity,attribute,source,flags))

    def aimConstraint(self,*addresses,**flags):
        receiver=self.resolve(addresses[-1])
        targets=tuple(self.resolve(node) for node in addresses[:-1])
        if 'worldUpObject' in flags:flags['worldUpObject']=self.resolve(flags['worldUpObject'])
        self.calls.append(('aim',receiver,targets,flags,
            {identity:node['parent'] for identity,node in self.nodes.items()}))
        constraint=self.createNode('aimConstraint',parent=self.path(receiver),name='aim'+str(self.next_id))
        return [constraint]

    def delete(self,*addresses):
        if len(addresses)==1 and isinstance(addresses[0],(list,tuple)):addresses=tuple(addresses[0])
        roots=[self.resolve(address) for address in addresses]
        paths=[self.path(identity) for identity in roots]
        remove=[identity for identity in self.nodes if any(
            self.path(identity)==path or self.path(identity).startswith(path+'|') for path in paths)]
        for identity in remove:self.nodes.pop(identity)

    def makeIdentity(self,address,**flags):self.calls.append(('freeze',self.resolve(address),flags))
    def reorder(self,address,**flags):self.calls.append(('reorder',self.resolve(address),flags))
    def warning(self,message):self.calls.append(('warning',message))


class SourceFitNativeAimTests(unittest.TestCase):
    def setup_aim(self):
        hierarchy,labels=arm_hierarchy()
        commands=DagCommands(hierarchy)
        host=SimpleNamespace(_cmds=commands,_require_transaction=lambda:None)
        snapshot=FitOrientationSnapshot(hierarchy,FitUpAxis.Y,(),labels=tuple(labels.items()))
        return host,commands,snapshot

    def test_native_straight_rp_aim_precedes_pivot_correction_and_freeze(self):
        host,c,snapshot=self.setup_aim()
        _,shoulder,elbow,wrist=snapshot.hierarchy.joints
        info=fit_joint_ik_info(snapshot.hierarchy,dict(snapshot.labels),shoulder.path)
        parent_id=c.resolve(shoulder.path);child_id=c.resolve(elbow.path)
        wrist_id=c.resolve(wrist.path)
        sibling=c.add(shoulder.path+'|Accessory','joint',(8.,13.,2.))
        c.locks[parent_id,'rx']=True;c.locks[child_id,'tx']=True
        driver=c.add('|SDK','animCurveUA',(0.,0.,0.))
        c.incoming[parent_id,'rz']='SDK.output'
        aim_joint(host,shoulder.path,elbow.path,snapshot,info,dict(primary='X',secondary='Y'))
        events=[call[0] for call in c.calls]
        self.assertLess(events.index('aim'),events.index('move'))
        self.assertLess(events.index('move'),events.index('freeze'))
        self.assertLess(events.index('freeze'),events.index('connect'))
        aim=next(call for call in c.calls if call[0]=='aim')
        self.assertEqual(aim[3]['worldUpType'],'object')
        self.assertEqual(c.resolve(aim[3]['worldUpObject']),wrist_id)
        self.assertIsNone(aim[4][parent_id]);self.assertIsNone(aim[4][child_id])
        self.assertNotEqual(aim[4][sibling],parent_id)
        move=next(call for call in c.calls if call[0]=='move')
        self.assertEqual(move[1:4],(child_id,'rotatePivot',(0.,0.,shoulder.world_position[1]/-100.)))
        self.assertEqual(c.nodes[child_id]['parent'],parent_id)
        self.assertEqual(c.nodes[sibling]['parent'],parent_id)
        self.assertEqual(c.incoming[parent_id,'rz'],'|SDK.output')
        self.assertTrue(c.locks[parent_id,'rx']);self.assertTrue(c.locks[child_id,'tx'])
        self.assertEqual(set(c.nodes),{c.resolve(node.path) for node in snapshot.hierarchy.joints}|{c.resolve('|FitSkeleton'),sibling,driver})

    def test_centered_middle_aim_reads_start_objectrotation_and_resets_terminal(self):
        host,c,snapshot=self.setup_aim()
        _,shoulder,elbow,wrist=snapshot.hierarchy.joints
        c.nodes[c.resolve(shoulder.path)]['position']=(0.,15.,0.)
        info=fit_joint_ik_info(snapshot.hierarchy,dict(snapshot.labels),elbow.path)
        aim_joint(host,elbow.path,wrist.path,snapshot,info,dict(primary='X',secondary='Y'))
        position=next(call for call in c.calls if call[0]=='position')
        self.assertEqual(position[2],(0.,*elbow.world_position[1:]))
        aim=next(call for call in c.calls if call[0]=='aim')
        self.assertEqual(aim[3]['worldUpType'],'objectrotation')
        self.assertEqual(c.resolve(aim[3]['worldUpObject']),c.resolve(shoulder.path))
        wrist_id=c.resolve(wrist.path)
        terminal_sets=[call[2] for call in c.calls if call[0]=='set' and call[1]==wrist_id and call[3]]
        self.assertEqual(terminal_sets,['jointOrient','rotate'])

    def test_native_dispatch_bypasses_parallel_solver_and_preserves_order(self):
        host,c,snapshot=self.setup_aim()
        host.capture_fit_orientation=lambda container:snapshot
        native=[]
        host.aim_source_fit_joint=lambda parent,child,current,info,state:native.append((parent,child,state))
        with patch('adv_py.adapters.maya_source_fit_orientation.OrientFitJoints',side_effect=AssertionError('parallel planner')):
            update_orientations(host,(snapshot.hierarchy.joints[-1].path,))
        _,shoulder,elbow,wrist=snapshot.hierarchy.joints
        self.assertEqual([(parent,child) for parent,child,_ in native],[(shoulder.path,elbow.path),(elbow.path,wrist.path)])
        # The endpoint dispatch calls the start procedure first. MEL locals
        # belong to separate invocations, even when their axis values agree.
        self.assertIsNot(native[0][2],native[1][2])
        self.assertEqual(native[0][2],native[1][2])


if __name__=='__main__':unittest.main()
