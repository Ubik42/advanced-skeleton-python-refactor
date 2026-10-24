"""Native FitMode watchers are bounded, scene-bound and character-owned."""
from contextlib import contextmanager
from dataclasses import replace
import unittest

from adv_py.adapters import maya_source_fit_mode as module
from adv_py.core.fit_container import FitUpAxis
from adv_py.core.fit_hierarchy import FitHierarchyNode, FitHierarchySnapshot
from adv_py.core.fit_metadata import FitJointField, FitJointMetadata
from adv_py.core.fit_orientation import FitOrientationSnapshot
from adv_py.core.source_fit_mode import source_fit_mode_aim_parent, source_fit_mode_selection


ROOT = '|FitSkeleton|Root'
SPINE = ROOT+'|Spine'
TIP = SPINE+'|Tip'


def snapshot():
    nodes = tuple(FitHierarchyNode(path, path.rsplit('|',1)[-1], parent,
                                  (0.,y,0.), (0.,y,0.))
                  for path, parent, y in ((ROOT,'|FitSkeleton',0.),(SPINE,ROOT,10.),(TIP,SPINE,17.)))
    return FitOrientationSnapshot(FitHierarchySnapshot('|FitSkeleton', nodes), FitUpAxis.Y, (),
                                  tuple(FitJointMetadata(node.path) for node in nodes))


class Commands:
    def __init__(self):
        self.jobs = {}
        self.next_job = 1
        self.huds = set()
        self.selection = [SPINE]
        self.axes = {ROOT: False, SPINE: True}
        self.killed = []
        self.fail_hud = False

    def ls(self, **options):
        return self.selection[:]

    def objExists(self, node):
        return True

    def getAttr(self, plug):
        return self.axes[plug.rsplit('.',1)[0]]

    def setAttr(self, plug, value):
        self.axes[plug.rsplit('.',1)[0]] = value

    def select(self, nodes=None, **options):
        self.selection = list(nodes or ())

    def scriptJob(self, **options):
        if 'exists' in options:
            return options['exists'] in self.jobs
        if 'kill' in options:
            self.killed.append(options['kill'])
            del self.jobs[options['kill']]
            return
        identifier = self.next_job
        self.next_job += 1
        self.jobs[identifier] = options
        return identifier

    def headsUpDisplay(self, name, **options):
        if 'exists' in options:
            return name in self.huds
        if 'remove' in options:
            self.huds.remove(name)
            return
        if self.fail_hud:
            raise RuntimeError('HUD block occupied')
        self.huds.add(name)


class Host:
    namespace = None

    def __init__(self, commands):
        self._cmds = commands
        self.manual_updates = 0

    @contextmanager
    def transaction(self, label):
        yield

    def capture_fit_orientation(self, *args):
        return snapshot()

    def scene_address(self, address):
        return 'character:'+address

    def manual_update_fit(self):
        self.manual_updates += 1


class SourceFitModeTests(unittest.TestCase):
    def tearDown(self):
        module._SESSIONS.clear()

    def test_selected_spine_watches_parent_and_preferred_child_in_native_order(self):
        plan = source_fit_mode_selection(snapshot(), (SPINE,))
        self.assertEqual(plan.parent_axes, (ROOT,))
        self.assertEqual(plan.aiming_children, (SPINE,TIP))
        self.assertEqual(plan.transform_watch, SPINE)

    def test_root_selection_aims_its_child_without_showing_a_container_axis(self):
        plan = source_fit_mode_selection(snapshot(), (ROOT,))
        self.assertEqual(plan.parent_axes, ())
        self.assertEqual(plan.aiming_children, (SPINE,))
        self.assertEqual(plan.transform_watch, ROOT)

    def test_only_first_selected_joint_is_watched_even_when_later_joint_has_twist(self):
        before = snapshot()
        before = replace(before, metadata=tuple(replace(row,
            present_fields=frozenset((FitJointField.TWIST_JOINTS,))) if row.joint==TIP else row
            for row in before.metadata))
        plan = source_fit_mode_selection(before, (SPINE,TIP))
        self.assertEqual(plan.twist_watch, SPINE)
        self.assertEqual(plan.aiming_children, (SPINE,TIP,TIP))

    def test_unknown_selection_cannot_watch_another_character(self):
        plan = source_fit_mode_selection(snapshot(), ('|Other|Root',))
        self.assertEqual(plan.selected, ())
        self.assertIsNone(plan.transform_watch)

    def test_duplicate_cup_branch_is_skipped_but_original_cup_can_aim(self):
        before = snapshot()
        cup = replace(before.hierarchy.joints[1], short_name='Cup1')
        changed = replace(before, hierarchy=replace(before.hierarchy,
            joints=(before.hierarchy.joints[0],cup,before.hierarchy.joints[2])))
        self.assertIsNone(source_fit_mode_aim_parent(changed,TIP))
        cup = replace(cup,short_name='Cup')
        changed = replace(changed,hierarchy=replace(changed.hierarchy,
            joints=(changed.hierarchy.joints[0],cup,changed.hierarchy.joints[2])))
        self.assertEqual(source_fit_mode_aim_parent(changed,TIP),SPINE)

    def test_toggle_creates_two_scene_jobs_and_reuses_session_on_next_click(self):
        commands = Commands()
        host = Host(commands)
        self.assertTrue(module.toggle(host))
        self.assertEqual(host.manual_updates,1)
        self.assertEqual(len(commands.jobs),2)
        self.assertTrue(all(options['killWithScene'] and options['compressUndo']
                            for options in commands.jobs.values()))
        self.assertEqual(commands.selection,[SPINE])
        self.assertFalse(module.toggle(Host(commands)))
        self.assertEqual(commands.jobs,{})
        self.assertEqual(commands.huds,set())

    def test_selection_watchers_are_replaced_instead_of_accumulating(self):
        commands = Commands()
        host = Host(commands)
        module.toggle(host)
        session = module._SESSIONS['']
        session.selection_changed()
        self.assertTrue(commands.axes[ROOT])
        self.assertEqual(len(commands.jobs),4)
        old = tuple(session.selected_jobs)
        session.selection_changed()
        self.assertEqual(len(commands.jobs),4)
        self.assertTrue(set(old).issubset(commands.killed))
        self.assertEqual(session.temporary_axes,[ROOT])
        module.toggle(host)
        self.assertFalse(commands.axes[ROOT])
        self.assertTrue(commands.axes[SPINE])

    def test_scene_killed_jobs_are_not_mistaken_for_a_live_session(self):
        commands = Commands()
        host = Host(commands)
        module.toggle(host)
        commands.jobs.clear()
        self.assertTrue(module.toggle(host))
        self.assertEqual(host.manual_updates,2)
        self.assertEqual(len(commands.jobs),2)

    def test_start_failure_cleans_created_jobs_and_does_not_leave_a_session(self):
        commands = Commands()
        commands.fail_hud = True
        with self.assertRaises(RuntimeError):
            module.toggle(Host(commands))
        self.assertEqual(commands.jobs,{})
        self.assertEqual(module._SESSIONS,{})
        self.assertEqual(commands.selection,[SPINE])

    def test_existing_hud_is_preserved_when_mode_cannot_start(self):
        commands = Commands()
        commands.huds.add('HUDFitMode')
        with self.assertRaises(ValueError):
            module.toggle(Host(commands))
        self.assertEqual(commands.huds,{'HUDFitMode'})
        self.assertEqual(commands.jobs,{})

    def test_build_stop_kills_only_owned_jobs_and_keeps_native_axis_display(self):
        commands = Commands()
        host = Host(commands)
        module.toggle(host)
        session = module._SESSIONS['']
        session.selection_changed()
        unrelated = commands.scriptJob(event=['Other',lambda:None])
        module.stop(host)
        self.assertEqual(set(commands.jobs),{unrelated})
        self.assertTrue(commands.axes[ROOT])

    def test_callback_reentrancy_does_not_install_or_execute_more_jobs(self):
        commands = Commands()
        session = module._FitModeSession(Host(commands),updating=True)
        session.selection_changed()
        session.update_joints((SPINE,))
        self.assertEqual(commands.jobs,{})

    def test_geometry_import_suspends_jobs_and_resumes_after_the_transaction(self):
        commands = Commands()
        host = Host(commands)
        module.toggle(host)
        original = module._SESSIONS['']
        with module.suspend_for_geometry(host,resume=True):
            self.assertEqual(commands.jobs,{})
            self.assertNotIn('',module._SESSIONS)
        self.assertIsNot(module._SESSIONS[''],original)
        self.assertEqual(len(commands.jobs),2)
        self.assertEqual(host.manual_updates,2)

    def test_geometry_hide_or_failure_leaves_mode_stopped_as_source_early_return(self):
        for failure in (False,True):
            commands = Commands()
            host = Host(commands)
            module.toggle(host)
            try:
                with module.suspend_for_geometry(host,resume=failure):
                    if failure:raise RuntimeError('asset import failed')
            except RuntimeError:
                pass
            self.assertEqual(commands.jobs,{})
            self.assertNotIn('',module._SESSIONS)


if __name__ == '__main__':
    unittest.main()
