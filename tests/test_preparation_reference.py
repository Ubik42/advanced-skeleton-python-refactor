import tempfile
import unittest
from pathlib import Path

from adv_py.application.preparation_reference import (
    ModelReferenceResult, ReferencePreparationModel,
)


class PreparationReferenceTests(unittest.TestCase):
    def test_existing_maya_source_reaches_host(self):
        class Host:
            def reference_model(self, source):
                return ModelReferenceResult(source, "model", "modelRN",
                                            ("|model:Body",))

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "body.ma"
            source.write_text("// Maya ASCII")
            result = ReferencePreparationModel(Host()).execute(source)
            self.assertEqual(result.source, source.resolve())
            self.assertEqual(result.top_nodes, ("|model:Body",))

    def test_non_scene_file_is_rejected_before_host(self):
        class Host:
            def reference_model(self, source):
                raise AssertionError("invalid source reached Maya host")

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "body.txt"
            source.write_text("not a Maya scene")
            with self.assertRaisesRegex(ValueError, "Maya"):
                ReferencePreparationModel(Host()).execute(source)


if __name__ == "__main__":
    unittest.main()
