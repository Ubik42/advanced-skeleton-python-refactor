import unittest

from adv_py.application.preparation_objects import (
    RecordPreparationObjects, ReselectPreparationObjects,
)
from adv_py.core.preparation_objects import (
    PreparationObjectRole as Role, validate_preparation_objects,
)


class PreparationObjectsTests(unittest.TestCase):
    def test_eye_requires_one_model_and_skin_accepts_many(self):
        objects = ("|model:Body", "|model:Coat")
        self.assertEqual(validate_preparation_objects(Role.SKIN, objects), objects)
        with self.assertRaisesRegex(ValueError, "一个眼球"):
            validate_preparation_objects(Role.RIGHT_EYE, objects)

    def test_record_reads_back_and_reselects(self):
        class Host:
            def __init__(self):
                self.saved = ()
                self.selected = ()

            def selected_meshes(self):
                return ("|model:Body", "|model:Coat")

            def write_objects(self, role, objects):
                self.saved = objects

            def read_objects(self, role):
                return self.saved

            def select_objects(self, objects):
                self.selected = objects

        host = Host()
        self.assertEqual(len(RecordPreparationObjects(host).execute(Role.SKIN)), 2)
        self.assertEqual(ReselectPreparationObjects(host).execute(Role.SKIN),
                         host.selected)


if __name__ == "__main__":
    unittest.main()
