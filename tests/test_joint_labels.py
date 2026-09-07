import unittest
from contextlib import contextmanager
from copy import deepcopy

from adv_py.application import EditJointLabels
from adv_py.core import JointLabel, JointLabelValidationError


class FakeJointLabelHost:
    def __init__(self) -> None:
        self.labels = {"|Root": None, "|Root|Spine": None}

    def resolve_joints(self, names):
        missing = [name for name in names if name not in self.labels]
        if missing:
            raise JointLabelValidationError(f"关节不存在：{missing[0]}")
        return tuple(names)

    @contextmanager
    def transaction(self, label):
        del label
        before = deepcopy(self.labels)
        try:
            yield
        except Exception:
            self.labels = before
            raise

    def set_joint_label(self, joint, label):
        self.labels[joint] = label

    def clear_joint_label(self, joint):
        self.labels[joint] = None

    def read_joint_label(self, joint):
        return self.labels[joint]


class JointLabelTests(unittest.TestCase):
    def test_applies_reads_and_clears_explicit_joint_labels(self) -> None:
        host = FakeJointLabelHost()
        labels = EditJointLabels(host)

        result = labels.apply(("|Root", "|Root|Spine"), " Chest ")

        self.assertEqual(result.label, JointLabel("Chest"))
        self.assertEqual(labels.read("|Root"), JointLabel("Chest"))
        labels.clear(("|Root",))
        self.assertIsNone(labels.read("|Root"))

    def test_rejects_invalid_input_before_mutation(self) -> None:
        host = FakeJointLabelHost()
        labels = EditJointLabels(host)

        with self.assertRaisesRegex(JointLabelValidationError, "不存在"):
            labels.apply(("|Missing",), "Hip")

        self.assertEqual(host.labels, {"|Root": None, "|Root|Spine": None})


if __name__ == "__main__":
    unittest.main()
