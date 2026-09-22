import unittest
from contextlib import contextmanager

from adv_py.application import BindSkin
from adv_py.core import (
    SkinBindInputState,
    SkinBindMethod,
    SkinBindSnapshot,
    SkinBindValidationError,
    SkinWeightNormalization,
    plan_skin_bind,
)


class FakeSkinBindHost:
    def __init__(self, *, input_state=None, collision=False, faulty_result=False):
        self.input_state = input_state or SkinBindInputState(
            "|BodyMesh",
            ("|BodyMesh|BodyMeshShape",),
            24,
            ("|JointA", "|JointB"),
            (),
        )
        self.collision = collision
        self.faulty_result = faulty_result
        self.skin = None
        self.transaction_count = 0

    def find_name_collisions(self, name):
        return (name,) if self.collision else ()

    def capture_skin_bind_input(self, plan):
        del plan
        return self.input_state

    @contextmanager
    def transaction(self, label):
        del label
        before = self.skin
        self.transaction_count += 1
        try:
            yield
        except Exception:
            self.skin = before
            raise

    def create_skin_bind(self, plan):
        self.skin = SkinBindSnapshot(
            plan.skin_name,
            (plan.mesh_path,),
            plan.influence_paths,
            plan.maximum_influences,
            plan.maintain_maximum_influences,
            plan.bind_method,
            plan.normalization,
        )

    def capture_skin_bind(self, plan):
        del plan
        if self.faulty_result:
            return SkinBindSnapshot(
                self.skin.skin_name,
                self.skin.geometry_paths,
                self.skin.influence_paths[:-1],
                self.skin.maximum_influences,
                self.skin.maintain_maximum_influences,
                self.skin.bind_method,
                self.skin.normalization,
            )
        return self.skin


class SkinBindTests(unittest.TestCase):
    def test_plans_explicit_portable_bind_semantics(self):
        plan = plan_skin_bind("|BodyMesh", ("|JointA", "|JointB"), maximum_influences=2)
        self.assertEqual(plan.mesh_path, "|BodyMesh")
        self.assertEqual(plan.bind_method, SkinBindMethod.CLOSEST_DISTANCE)
        self.assertEqual(plan.normalization, SkinWeightNormalization.INTERACTIVE)
        relaxed = plan_skin_bind("|BodyMesh", ("|JointA", "|JointB"),
            maximum_influences=2, maintain_maximum_influences=False)
        self.assertFalse(relaxed.maintain_maximum_influences)

    def test_rejects_duplicate_influences_and_invalid_limit(self):
        with self.assertRaises(SkinBindValidationError):
            plan_skin_bind("|BodyMesh", ("|JointA", "|JointA"))
        with self.assertRaises(SkinBindValidationError):
            plan_skin_bind("|BodyMesh", ("|JointA",), maximum_influences=0)
        with self.assertRaises(SkinBindValidationError):
            plan_skin_bind("|BodyMesh", ("|JointA",),
                           maintain_maximum_influences=0)

    def test_preflight_blocks_existing_skin_without_transaction(self):
        state = SkinBindInputState(
            "|BodyMesh",
            ("|BodyMesh|BodyMeshShape",),
            24,
            ("|JointA", "|JointB"),
            ("oldSkin",),
        )
        host = FakeSkinBindHost(input_state=state)
        with self.assertRaisesRegex(ValueError, "已有 skinCluster"):
            BindSkin(host).apply("|BodyMesh", ("|JointA", "|JointB"), maximum_influences=2)
        self.assertEqual(host.transaction_count, 0)
        self.assertIsNone(host.skin)

    def test_binds_once_and_rolls_back_faulty_result(self):
        host = FakeSkinBindHost()
        result = BindSkin(host).apply("|BodyMesh", ("|JointA", "|JointB"), maximum_influences=2)
        self.assertEqual(result.snapshot.skin_name, "AdvPy_BodySkin")
        self.assertEqual(host.transaction_count, 1)

        faulty = FakeSkinBindHost(faulty_result=True)
        with self.assertRaisesRegex(RuntimeError, "复检失败"):
            BindSkin(faulty).apply("|BodyMesh", ("|JointA", "|JointB"), maximum_influences=2)
        self.assertIsNone(faulty.skin)


if __name__ == "__main__":
    unittest.main()
