"""Body snapshots separate the native owned Face branch from foreign joints."""
import unittest
from types import SimpleNamespace as NS
from adv_py.adapters.maya_face_body_roles import face_body_joint_paths

HEAD = '|Root|Head'
FACE = HEAD + '|FaceJoint_M'
EYE = FACE + '|Eye_R'
FOREIGN = HEAD + '|ExtraJoint'


class Commands:
    def __init__(self, members, parent=HEAD):
        self.members = members
        self.parent = parent

    def ls(self, name, **flags):
        return [FACE] if name == 'FaceJoint_M' else [HEAD]

    def objExists(self, name):
        return name in ('FaceAllSet', 'FaceFitSkeleton.HeadJoint')

    def listRelatives(self, name, **flags):
        return [self.parent]

    def getAttr(self, name):
        return HEAD

    def sets(self, path, **flags):
        return path in self.members


class FaceBodyRolesTests(unittest.TestCase):
    def test_owned_face_is_separate_and_foreign_body_joint_stays(self):
        host = NS(_cmds=Commands({FACE, EYE}))
        paths = [HEAD, FACE, EYE, FOREIGN]
        excluded = face_body_joint_paths(host, paths)
        self.assertEqual(excluded, frozenset((FACE, EYE)))
        self.assertIn(FOREIGN, set(paths) - excluded)

    def test_unowned_joint_below_face_is_rejected(self):
        host = NS(_cmds=Commands({FACE}))
        with self.assertRaises(ValueError):
            face_body_joint_paths(host, [HEAD, FACE, EYE])

    def test_moved_face_does_not_hide_body_topology_change(self):
        host = NS(_cmds=Commands({FACE, EYE}, parent='|OtherHead'))
        self.assertEqual(face_body_joint_paths(host, [HEAD, FACE, EYE]), frozenset())
