"""Native Fit live-frame order and per-parent center snap dispatch."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from adv_py.adapters.maya_source_fit_orientation import update_orientations
from adv_py.core.fit_orientation import (
    FitOrientationAxisConfiguration, FitOrientationSnapshot,
)
from adv_py.core.fit_container import FitUpAxis
from test_source_fit_pole_vectors import arm_hierarchy


class Commands:
    def __init__(self, hierarchy):
        self.hierarchy = hierarchy
        self.moves = []

    def ls(self, node, **kwargs):return [node]

    def listRelatives(self, parent, **kwargs):
        return [node.path for node in reversed(self.hierarchy.joints)
                if node.path.startswith(parent+'|')]

    def xform(self, node, **kwargs):
        return next(item.world_position for item in self.hierarchy.joints if item.path==node)

    def move(self, *args, **kwargs):self.moves.append((args,kwargs))


class Host:
    def __init__(self, *, world_match=False):
        hierarchy,labels = arm_hierarchy()
        self._cmds = Commands(hierarchy)
        self.snapshot = FitOrientationSnapshot(hierarchy,FitUpAxis.Y,(),
            axis_configuration=FitOrientationAxisConfiguration(world_match=world_match),
            labels=tuple(labels.items()))
        self.generation = 0
        self.reads = []
        self.aims = []

    def _require_transaction(self):pass

    def capture_fit_orientation(self, container):
        self.reads.append(self.generation)
        return self.snapshot


class RecordingEditor:
    def __init__(self, host):self.host = host

    def plan(self, request, container):
        self.host.aims.append((request.joints[0],self.host.generation))
        return SimpleNamespace(changes=(True,),terminal_resets=())

    def apply_plan_in_transaction(self, plan):self.host.generation += 1


class SourceFitOrientationDispatchTests(unittest.TestCase):
    def test_manual_pass_calls_each_native_root_in_its_own_procedure(self):
        from adv_py.application.registered_body_build import _refresh_fit_orientations_before_body
        roots=('|FitSkeleton|Root','|FitSkeleton|Prop')
        calls=[]
        host=SimpleNamespace(_cmds=SimpleNamespace(listRelatives=lambda *args,**options:list(roots)),
            update_source_fit_orientations=lambda children,**options:calls.append((children,options)))
        _refresh_fit_orientations_before_body(host,'FitSkeleton')
        self.assertEqual(calls,[((root,),dict(container='FitSkeleton',recursive=True)) for root in roots])

    def dispatch(self, host, children, **options):
        with patch('adv_py.adapters.maya_source_fit_orientation.OrientFitJoints',RecordingEditor):
            update_orientations(host,children,**options)

    def test_editing_rp_end_orients_start_before_middle_and_reads_new_frame(self):
        host = Host()
        root,shoulder,elbow,wrist = host.snapshot.hierarchy.joints
        self.dispatch(host,(wrist.path,))
        self.assertEqual(host.aims,[(shoulder.path,0),(elbow.path,1)])

    def test_interactive_start_subcall_does_not_leak_procedure_locals_to_middle(self):
        host=Host()
        root,shoulder,elbow,wrist=host.snapshot.hierarchy.joints
        states=[]
        def native(parent,child,snapshot,info,state):
            states.append((parent,dict(state)))
            state.update(no_flip=True,world_forward_vector=(1.,0.,0.),primary='-Y')
            host.generation+=1
        host.aim_source_fit_joint=native
        result=update_orientations(host,(wrist.path,))
        self.assertEqual(result,(shoulder.path,elbow.path))
        self.assertEqual([row[1] for row in states],
            [dict(primary='X',secondary='Y'),dict(primary='X',secondary='Y')])

    def test_recursive_iterations_keep_locals_within_the_same_source_procedure(self):
        host=Host()
        root,shoulder,elbow,wrist=host.snapshot.hierarchy.joints
        states=[]
        def native(parent,child,snapshot,info,state):
            states.append((parent,dict(state)))
            state['no_flip']=True
        host.aim_source_fit_joint=native
        update_orientations(host,(root.path,),recursive=True)
        self.assertNotIn('no_flip',states[0][1])
        self.assertTrue(states[1][1]['no_flip'])

    def test_recursive_pass_uses_native_reversed_descendants_without_extra_start_pass(self):
        host = Host()
        root,shoulder,elbow,wrist = host.snapshot.hierarchy.joints
        self.dispatch(host,(root.path,),recursive=True)
        self.assertEqual(host.aims,[(shoulder.path,0),(elbow.path,1)])
        self.assertIn(1,host.reads)

    def test_world_match_interactive_request_recurses_only_from_first_child(self):
        host = Host(world_match=True)
        root,shoulder,elbow,wrist = host.snapshot.hierarchy.joints
        self.dispatch(host,(wrist.path,elbow.path))
        self.assertEqual(host.aims,[(elbow.path,0)])

    def test_center_snap_uses_parent_move_preserving_child_world_positions(self):
        host = Host()
        root,shoulder,elbow,wrist = host.snapshot.hierarchy.joints
        nodes = tuple(replace(node,world_position=(0.,*node.world_position[1:]))
                      if node.path == shoulder.path else node for node in host.snapshot.hierarchy.joints)
        host.snapshot = replace(host.snapshot,hierarchy=replace(host.snapshot.hierarchy,joints=nodes))
        host._cmds.hierarchy = host.snapshot.hierarchy
        self.dispatch(host,(wrist.path,),recursive=True)
        self.assertEqual(host._cmds.moves,[((0.,12.,1.,elbow.path),
            {'absolute':True,'worldSpace':True,'preserveChildPosition':True})])


if __name__ == '__main__':unittest.main()
