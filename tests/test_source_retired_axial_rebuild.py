"""Export-cleaned Head remains authored Fit correspondence for rebuilding."""
from types import SimpleNamespace
import unittest

from adv_py.application.character_rebuild import _rebuild_axial_description
from adv_py.core.body_spline import BodySplinePlan
from adv_py.core.character_registry import CharacterBindJoint
from adv_py.core.character_body_retirement import CharacterRetiredBodyJoint


class SourceRetiredAxialRebuildTests(unittest.TestCase):
    def test_retired_head_reconstructs_the_complete_neck_chain_before_cleanup(self):
        identity=(1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.)
        paths=('|Root_M','|Root_M|Chest_M','|Root_M|Chest_M|Neck_M',
               '|Root_M|Chest_M|Neck_M|Head_M')
        body=tuple(CharacterBindJoint(path,paths[index-1] if index else None,identity)
            for index,path in enumerate(paths))
        spine=BodySplinePlan.__new__(BodySplinePlan)
        object.__setattr__(spine,'body_joints',paths[:2])
        retired=CharacterRetiredBodyJoint(paths[-1],'deleted-head',paths[-2],identity,0,3)
        registration=SimpleNamespace(body=body[:-1],retired_body=(retired,),spine=spine)
        description=_rebuild_axial_description(registration)
        self.assertEqual(description.spine,('Root_M','Chest_M'))
        self.assertEqual(description.neck,('Neck_M','Head_M'))
        self.assertEqual(len(registration.body),3)


if __name__=='__main__':unittest.main()
