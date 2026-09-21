import json
from pathlib import Path
import tempfile
import unittest

from adv_py.application import InspectMocapBodyMapping,load_mocap_mapping_preset,save_mocap_mapping_preset
from adv_py.core import (MocapMappingPreset,MocapMappingValidationError,
                         encode_mocap_mapping_preset,decode_mocap_mapping_preset)
from test_mocap_mapping import FakeMappingHost,valid_mappings


class MocapPresetTests(unittest.TestCase):
    def test_round_trip_into_existing_mapping_inspection(self):
        preset=MocapMappingPreset('Take A human',valid_mappings(),3)
        self.assertEqual(decode_mocap_mapping_preset(encode_mocap_mapping_preset(preset)),preset)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'human.json'
            self.assertEqual(save_mocap_mapping_preset(preset,path),path)
            loaded=load_mocap_mapping_preset(path)
            self.assertEqual(loaded,preset)
            plan=InspectMocapBodyMapping(FakeMappingHost()).execute('|TakeA:Hips',loaded.mappings,
                           expected_body_joint_count=loaded.expected_body_joint_count).require_valid()
            self.assertEqual(len(plan.entries),3)
            with self.assertRaises(FileExistsError):save_mocap_mapping_preset(preset,path)

    def test_rejects_tampering_and_ambiguous_mappings(self):
        preset=MocapMappingPreset('Take A human',valid_mappings(),3)
        raw=json.loads(encode_mocap_mapping_preset(preset))
        raw['mappings'][0]['target_name']='Head_M'
        with self.assertRaises(MocapMappingValidationError):
            decode_mocap_mapping_preset(json.dumps(raw))
        raw=json.loads(encode_mocap_mapping_preset(preset))
        raw['unexpected']=1
        with self.assertRaisesRegex(MocapMappingValidationError,'字段'):
            decode_mocap_mapping_preset(json.dumps(raw))
        with self.assertRaisesRegex(MocapMappingValidationError,'重复'):
            MocapMappingPreset('duplicate',(valid_mappings()[0],valid_mappings()[0]),3)
