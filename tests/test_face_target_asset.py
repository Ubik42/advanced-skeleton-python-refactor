"""Portable sculpt target geometry and file integrity."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from adv_py.application import load_face_target_asset, save_face_target_asset
from adv_py.core import (FaceMeshSnapshot, FaceShapeKind, FaceTarget,
    face_target_asset_from_json, face_target_asset_from_meshes,
    face_target_asset_to_json)


class FaceTargetAssetTests(unittest.TestCase):
    def meshes(self):
        neutral = FaceMeshSnapshot("|Neutral", 4, "a" * 64,
            ((0., 0., 0.), (1., 0., 0.), (1., 1., 0.), (0., 1., 0.)))
        sculpt = FaceMeshSnapshot("|Smile", 4, "a" * 64,
            ((0., 0., 0.), (1.25, 0., .5), (1., 1., 0.), (0., 1., 0.)))
        return neutral, sculpt

    def test_sparse_roundtrip_and_file_no_overwrite(self):
        neutral, sculpt = self.meshes()
        asset = face_target_asset_from_meshes(neutral,
            FaceTarget("smile_R", FaceShapeKind.EXPRESSION, "|Smile"), sculpt)
        self.assertEqual(asset.deltas, ((1, .25, 0., .5),))
        self.assertEqual(asset.points_for(neutral), sculpt.points)
        self.assertEqual(face_target_asset_from_json(face_target_asset_to_json(asset)),
                         asset)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "smile.json"
            save_face_target_asset(asset, path)
            self.assertEqual(load_face_target_asset(path), asset)
            with self.assertRaises(FileExistsError):
                save_face_target_asset(asset, path)

    def test_digest_and_neutral_mismatch_rejected(self):
        neutral, sculpt = self.meshes()
        asset = face_target_asset_from_meshes(neutral,
            FaceTarget("smile_R", FaceShapeKind.EXPRESSION, "|Smile"), sculpt)
        document = json.loads(face_target_asset_to_json(asset))
        document["payload"]["deltas"][0][1] = 2.
        with self.assertRaises(ValueError):
            face_target_asset_from_json(json.dumps(document))
        changed = FaceMeshSnapshot("|Neutral", 4, "a" * 64,
            ((0., 0., 0.), (2., 0., 0.), (1., 1., 0.), (0., 1., 0.)))
        with self.assertRaises(ValueError):
            asset.points_for(changed)


if __name__ == "__main__":
    unittest.main()
