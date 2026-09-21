import unittest
from dataclasses import replace
import json

from adv_py.core.character_registry import *
from adv_py.core.body_spine import BodySpinePlan
from adv_py.core.body_control_spaces import BodyControlSpacesPlan, BodyControlSpaceSpec
from adv_py.core.body_limb_mechanisms import BodyLimbMechanismJointSpec,BodyLimbMechanismRole
from adv_py.core.fit_symmetry import FitBuildSide


def registration_fixture():
    identity=(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1)
    body=[]
    parent=None
    for i in range(30):
        node=(parent or "")+"|J"+str(i)
        body.append(CharacterBindJoint(node,parent,identity))
        parent=node
    drivers=tuple(BodyLimbMechanismJointSpec(BodyLimbMechanismRole.FK if i<3 else BodyLimbMechanismRole.IK,
        FitBuildSide.MIDDLE,body[i%3].path,"|Driver"+str(i),"Driver"+str(i),"|Mechanisms",(0,0,i),((1,0,0),(0,1,0),(0,0,1))) for i in range(6))
    spine=BodySpinePlan("|Mechanisms",drivers,"|Pelvis",("|FK0","|FK1","|FK2"),tuple(j.path for j in body[:3]),"|IKOffset","|IK","|PoleOffset","|Pole",(0,1,0),"|Waist","|Chest",(1,1))
    spaces=BodyControlSpacesPlan(body[0].path,tuple(BodyControlSpaceSpec(k,("|Target"+str(i),) if k=="head" else ("|Target"+str(i),"|Pole"+str(i)),body[0].path,"|Global",k=="head","body") for i,k in enumerate(("head","hand_R","hand_L","foot_R","foot_L"))))
    paths={j.path for j in body}|{"|FitSkeleton","|Global","|Mechanisms","|Pelvis","|FK0","|FK1","|FK2","|IKOffset","|IK","|PoleOffset","|Pole","|Waist","|Chest"}|{j.path for j in drivers}|{p for s in spaces.spaces for p in s.targets}
    nodes=tuple(CharacterNode(p,str(i),"joint" if p in {j.path for j in body} else "transform",None) for i,p in enumerate(sorted(paths)))
    return CharacterRegistration(body[0].path,"|FitSkeleton",(CharacterChannel("global.translateX","|Global","translateX"),),tuple(body),nodes,spine,spaces)


class CharacterRegistryTests(unittest.TestCase):
    def test_roundtrip_and_stable_compatibility(self):
        registration=registration_fixture()
        decoded=decode_registration(encode_registration(registration))
        self.assertEqual(decoded,registration)
        self.assertEqual(decoded.compatibility_digest,registration.compatibility_digest)
        self.assertEqual(replace(registration,nodes=tuple(replace(n,uuid=n.uuid+"a") for n in registration.nodes)).compatibility_digest,registration.compatibility_digest)

    def test_document_rejects_unknown_corrupt_duplicate_nonfinite(self):
        text=encode_registration(registration_fixture())
        for update in ({"version":2},{"version":True},{"digest":"bad"},{"extra":1}):
            doc=json.loads(text);doc.update(update)
            with self.assertRaises(CharacterRegistryError): decode_registration(json.dumps(doc))
        for raw in ('{"x":1,"x":2}','{"x":NaN}'):
            with self.assertRaises(CharacterRegistryError): safe_json(raw)

    def test_semantic_failures_even_with_recomputed_digest(self):
        original=json.loads(encode_registration(registration_fixture()))
        def mutate(fn):
            doc=json.loads(json.dumps(original));fn(doc["payload"]);doc["digest"]=digest(doc["payload"])
            with self.assertRaises(CharacterRegistryError): decode_registration(json.dumps(doc))
        mutate(lambda p:p["channels"].append(p["channels"][0]))
        mutate(lambda p:p["body"].pop())
        mutate(lambda p:p["spine"]["lengths"].__setitem__(0,-1))
        mutate(lambda p:p["nodes"].pop())
        mutate(lambda p:p.__setitem__("container","|N:FitSkeleton"))
        mutate(lambda p:p["spaces"]["spaces"][0].__setitem__("rotation_only",False))


if __name__=="__main__": unittest.main()
