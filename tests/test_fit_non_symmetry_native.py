"""Native NonSymmetry toggle order, authored attributes and deletion scope."""
from contextlib import contextmanager
from types import SimpleNamespace
import unittest

from adv_py.adapters.maya_fit_non_symmetry import MayaFitNonSymmetryMixin
from adv_py.core.fit_hierarchy import FitHierarchyNode, FitHierarchySnapshot
from adv_py.core.fit_non_symmetry import plan_fit_non_symmetry


def snapshot(points):
    return FitHierarchySnapshot('|FitSkeleton', tuple(
        FitHierarchyNode(path, path.rsplit('|', 1)[-1], parent,
                         point, point) for path, parent, point in points))


class Commands:
    def __init__(self):
        self.attrs = {}
        self.generated = []
        self.descendants = []
        self.calls = []

    def ls(self, pattern, **options):
        return ['|FitSkeleton|Root'] if pattern == 'Root' else self.generated

    def attributeQuery(self, attribute, *, node, **options):
        return (node, attribute) in self.attrs

    def addAttr(self, node, **options):
        self.calls.append(('addAttr', node, options))
        self.attrs[node, options['longName']] = options['defaultValue']

    def referenceQuery(self, *args, **options):
        return False

    def listRelatives(self, node, **options):
        return self.descendants

    def delete(self, nodes):
        self.calls.append(('delete', tuple(nodes)))
        self.descendants = [node for node in self.descendants if node not in nodes]

    def deleteAttr(self, plug):
        self.calls.append(('deleteAttr', plug))
        del self.attrs[tuple(plug.rsplit('.', 1))]

    def select(self, **options):
        self.calls.append(('select', options))


class Host(MayaFitNonSymmetryMixin):
    def __init__(self, commands, hierarchy=None):
        self._cmds = commands
        self.hierarchy = hierarchy
        self._transaction_changed = False
        self.updates = 0

    def _resolve_transform(self, *args):
        return '|FitSkeleton'

    @contextmanager
    def transaction(self, label):
        yield

    def capture_fit_hierarchy(self, *args):
        return self.hierarchy

    def _non_symmetry_manual_update(self):
        self.updates += 1


class FitNonSymmetryNativeTests(unittest.TestCase):
    def test_authored_no_mirror_false_and_left_true_are_preserved(self):
        commands = Commands()
        commands.attrs = {('|Root|Hip', 'noMirror'): False,
                          ('|Root|Hip', 'noMirrorLeft'): True}
        Host(commands)._non_symmetry_write_root_attributes('|Root|Hip')
        self.assertEqual(commands.attrs[('|Root|Hip', 'noMirror')], False)
        self.assertEqual(commands.attrs[('|Root|Hip', 'noMirrorLeft')], True)
        self.assertEqual(commands.calls, [])

    def test_existing_no_mirror_does_not_add_a_missing_left_attribute(self):
        commands = Commands()
        commands.attrs['|Hip', 'noMirror'] = False
        Host(commands)._non_symmetry_write_root_attributes('|Hip')
        self.assertNotIn(('|Hip', 'noMirrorLeft'), commands.attrs)

    def test_new_attributes_use_native_defaults_and_keyability(self):
        commands = Commands()
        Host(commands)._non_symmetry_write_root_attributes('|Hip')
        self.assertEqual(commands.attrs, {('|Hip', 'noMirror'): True,
                                          ('|Hip', 'noMirrorLeft'): False})
        self.assertTrue(all(call[2]['keyable'] for call in commands.calls))

    def test_detached_generated_joint_deletion_returns_before_manual_update(self):
        commands = Commands()
        commands.generated = ['|NonSymmetryFitJoints|Hip_NonSymmetry']
        commands.descendants = ['|FitSkeleton|Root|Hip']
        commands.attrs = {('|FitSkeleton|Root', 'noMirror'): True,
                          ('|FitSkeleton|Root|Hip', 'noMirror'): False,
                          ('|FitSkeleton|Root|Hip', 'noMirrorLeft'): True}
        host = Host(commands)
        self.assertEqual(host.toggle_fit_non_symmetry_joints(), tuple(commands.generated))
        self.assertEqual(host.updates, 0)
        self.assertEqual(commands.attrs, {('|FitSkeleton|Root', 'noMirror'): True})
        self.assertTrue(host._transaction_changed)
        self.assertFalse(any(call[0] == 'select' for call in commands.calls))

    def test_no_side_branches_still_runs_both_manual_updates_and_clears_selection(self):
        hierarchy = snapshot((('|FitSkeleton|Root', '|FitSkeleton', (0., 17., 0.)),))
        commands = Commands()
        host = Host(commands, hierarchy)
        self.assertEqual(host.toggle_fit_non_symmetry_joints(), ())
        self.assertEqual(host.updates, 2)
        self.assertEqual(commands.calls, [('select', {'clear': True})])

    def test_native_descendant_order_and_scaled_boundary(self):
        root = '|FitSkeleton|Root'
        hierarchy = snapshot(((root, '|FitSkeleton', (.02, 10., 0.)),
                              (root+'|Center', root, (.0, 12., 0.)),
                              (root+'|Center|A', root+'|Center', (.01, 15., 0.)),
                              (root+'|Center|B', root+'|Center', (.010001, 15., 0.)),
                              (root+'|Center|C', root+'|Center', (-1., 15., 0.))))
        paths = tuple(joint.path for joint in reversed(hierarchy.joints[1:]))
        plan = plan_fit_non_symmetry(hierarchy, scale=1., ordered_paths=paths)
        self.assertEqual(plan.branch_roots, (root+'|Center|C', root+'|Center|B'))
        self.assertEqual(plan.center_tolerance, .01)

    def test_invalid_native_traversal_is_rejected(self):
        hierarchy = snapshot((('|FitSkeleton|Root', '|FitSkeleton', (0., 0., 0.)),))
        for paths in (('|Missing',), ('|FitSkeleton|Root', '|FitSkeleton|Root')):
            with self.assertRaises(ValueError):
                plan_fit_non_symmetry(hierarchy, scale=1., ordered_paths=paths)

    def test_deletion_uses_character_command_boundary_instead_of_raw_maya(self):
        class Raw:
            def __getattr__(self, name):
                raise AssertionError('operation escaped character scope: '+name)
        commands = Commands()
        commands.raw = Raw()
        commands.generated = ['|Detached|Hip_NonSymmetry']
        commands.descendants = ['|FitSkeleton|Root|Hip']
        commands.attrs = {('|FitSkeleton|Root|Hip','noMirror'):True}
        self.assertEqual(Host(commands).toggle_fit_non_symmetry_joints(), tuple(commands.generated))
        self.assertEqual(commands.attrs,{})

    def test_mirror_mutation_is_marked_before_maya_can_partially_fail(self):
        root = '|FitSkeleton|Root'
        branch = root+'|Hip'
        hierarchy = snapshot(((root,'|FitSkeleton',(0.,17.176163,0.)),
                              (branch,root,(1.,12.,0.))))
        class MirrorCommands(Commands):
            def listRelatives(self, node, **options):
                return [branch] if node == 'Root' else []
            def objExists(self, node): return False
            def mirrorJoint(self, node, **options):
                self.assertion()
                raise RuntimeError('Maya failed after creating a mirrored joint')
        commands = MirrorCommands()
        host = Host(commands,hierarchy)
        host.scene_address = lambda value:value
        commands.assertion = lambda:self.assertTrue(host._transaction_changed)
        with self.assertRaises(RuntimeError): host.toggle_fit_non_symmetry_joints()
        self.assertEqual(host.updates,1)


if __name__ == '__main__':
    unittest.main()
