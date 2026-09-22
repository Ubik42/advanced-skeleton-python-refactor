"""Immutable face asset versions and corruption detection."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from adv_py.application import FaceAssetLibrary
from adv_py.core import (FaceMeshSnapshot, FaceShapeKind, FaceTarget,
    face_target_asset_from_meshes)


def example_asset():
    neutral = FaceMeshSnapshot("|Neutral", 4, "a" * 64,
        ((0., 0., 0.), (1., 0., 0.), (1., 1., 0.), (0., 1., 0.)))
    sculpt = FaceMeshSnapshot("|Smile", 4, "a" * 64,
        ((0., 0., 0.), (1.25, 0., .5), (1., 1., 0.), (0., 1., 0.)))
    return face_target_asset_from_meshes(neutral,
        FaceTarget("smile_R", FaceShapeKind.EXPRESSION, "|Smile"), sculpt)


class FaceAssetLibraryTests(unittest.TestCase):
    def test_versions_are_immutable_and_resolvable(self):
        first = example_asset()
        second = replace(first, deltas=((1, .5, 0., .5),))
        with TemporaryDirectory() as directory:
            library = FaceAssetLibrary(Path(directory) / "faces")
            a = library.add(first, "1.0.0")
            library.add(second, "1.1.0")
            self.assertEqual(library.add(first, "1.0.0"), a)
            self.assertEqual(library.resolve("smile_R", "1.0.0"), first)
            self.assertEqual(library.resolve("smile_R", "1.1.0"), second)
            self.assertEqual(len(library.list()), 2)
            with self.assertRaises(FileExistsError):
                library.add(second, "1.0.0")
            self.assertEqual(library.resolve("smile_R", "1.0.0"), first)
            with self.assertRaises(ValueError):
                library.add(first, "../2.0.0")

    def test_corrupt_object_is_reported_and_rejected(self):
        with TemporaryDirectory() as directory:
            library = FaceAssetLibrary(Path(directory) / "faces")
            entry = library.add(example_asset(), "1.0.0")
            path = library.objects / (entry.object_sha256 + ".json")
            path.write_text(path.read_text(encoding="utf-8") + "tamper",
                            encoding="utf-8")
            self.assertFalse(library.list()[0].valid)
            with self.assertRaises(ValueError):
                library.resolve("smile_R", "1.0.0")


if __name__ == "__main__":
    unittest.main()
