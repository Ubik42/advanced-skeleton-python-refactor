"""Immutable face asset versions and corruption detection."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from adv_py.application import FaceAssetLibrary
from adv_py.core import (FaceAssetMergeConflict, FaceMeshSnapshot,
    FaceShapeKind, FaceTarget, face_target_asset_from_meshes,
    merge_face_target_assets)


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

    def test_three_way_merge_records_and_verifies_lineage(self):
        base = example_asset()
        left = replace(base, deltas=base.deltas + ((2, 0., .1, 0.),))
        right = replace(base, deltas=base.deltas + ((3, 0., 0., .2),))
        expected = merge_face_target_assets(base, left, right)
        self.assertEqual(tuple(row[0] for row in expected.deltas), (1, 2, 3))
        with TemporaryDirectory() as directory:
            library = FaceAssetLibrary(Path(directory) / "faces")
            for release, asset in (("1.0.0", base), ("1.1.0", left),
                                   ("1.2.0", right)):
                library.add(asset, release)
            merged = library.merge("smile_R", "1.0.0", "1.1.0",
                                   "1.2.0", "2.0.0")
            self.assertEqual(library.resolve("smile_R", "2.0.0"), expected)
            self.assertEqual([row[0] for row in merged.parents],
                             ["base", "left", "right"])
            self.assertEqual(library.merge("smile_R", "1.0.0", "1.1.0",
                                           "1.2.0", "2.0.0"), merged)
            reference = library.refs / "smile_R" / "1.1.0.json"
            reference.write_text("corrupt", encoding="utf-8")
            self.assertFalse(next(row for row in library.list()
                                  if row.release == "2.0.0").valid)
            with self.assertRaises(ValueError):
                library.resolve("smile_R", "2.0.0")

    def test_three_way_merge_rejects_conflicts_and_other_neutral(self):
        base = example_asset()
        left = replace(base, deltas=((1, .3, 0., .5),))
        right = replace(base, deltas=((1, .4, 0., .5),))
        with self.assertRaises(FaceAssetMergeConflict) as caught:
            merge_face_target_assets(base, left, right)
        self.assertEqual(caught.exception.vertices, (1,))
        with self.assertRaises(ValueError):
            merge_face_target_assets(base, left,
                replace(right, neutral_position_digest="b" * 64))
        with TemporaryDirectory() as directory:
            library = FaceAssetLibrary(Path(directory) / "faces")
            for release, asset in (("1.0.0", base), ("1.1.0", left),
                                   ("1.2.0", right)):
                library.add(asset, release)
            with self.assertRaises(FaceAssetMergeConflict):
                library.merge("smile_R", "1.0.0", "1.1.0", "1.2.0", "2.0.0")
            self.assertFalse((library.refs / "smile_R" / "2.0.0.json").exists())

    def test_three_way_merge_handles_removal_and_identical_edit(self):
        base = replace(example_asset(), deltas=((1, .25, 0., .5),
                                                 (2, 0., .2, 0.)))
        left = replace(base, deltas=((2, 0., .3, 0.),))
        right = replace(base, deltas=((1, .25, 0., .5),
                                      (2, 0., .3, 0.), (3, 0., 0., .2)))
        result = merge_face_target_assets(base, left, right)
        self.assertEqual(result.deltas, ((2, 0., .3, 0.),
                                         (3, 0., 0., .2)))
        with self.assertRaises(FaceAssetMergeConflict) as caught:
            merge_face_target_assets(base, left,
                replace(right, deltas=((1, .4, 0., .5),
                                       (2, 0., .3, 0.), (3, 0., 0., .2))))
        self.assertEqual(caught.exception.vertices, (1,))


if __name__ == "__main__":
    unittest.main()
