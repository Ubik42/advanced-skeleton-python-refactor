import unittest
from contextlib import contextmanager

from adv_py.application import CreateFitSkeleton
from adv_py.core import (
    LOCKED_FIT_CHANNELS,
    FitContainerDisplayStyle,
    FitContainerShape,
    FitContainerSpec,
    FitContainerState,
    FitSkeletonSettings,
    FitSkeletonValidationError,
    FitUpAxis,
)


class FakeFitContainerHost:
    def __init__(self, collisions=()):
        self.collisions = tuple(collisions)
        self.created = False
        self.settings = None
        self.transaction_count = 0

    def scene_up_axis(self):
        return FitUpAxis.Z

    def find_name_collisions(self, name):
        del name
        return self.collisions

    @contextmanager
    def transaction(self, label):
        del label
        before = (self.created, self.settings)
        self.transaction_count += 1
        try:
            yield
        except Exception:
            self.created, self.settings = before
            raise

    def create_fit_container(self, spec):
        self.created = True
        self.spec = spec
        return f"|{spec.name}"

    def inspect_fit_container(self, name):
        del name
        diameter = self.spec.display_radius * 2.0
        return FitContainerState(
            path=f"|{self.spec.name}",
            short_name=self.spec.name,
            shape=FitContainerShape.RING,
            display_style=FitContainerDisplayStyle.FIT,
            locked_channels=LOCKED_FIT_CHANNELS,
            local_translation=(0.0, 0.0, 0.0),
            local_rotation=(0.0, 0.0, 0.0),
            bounding_size=(diameter, diameter, 0.0),
        )

    def add_fit_skeleton_setting(self, container, setting):
        current = () if self.settings is None else self.settings.settings
        self.settings = FitSkeletonSettings(container, current + (setting,))

    def read_fit_skeleton_settings(self, container_name):
        del container_name
        return self.settings


class FitContainerTests(unittest.TestCase):
    def test_rejects_invalid_creation_spec(self) -> None:
        with self.assertRaises(FitSkeletonValidationError):
            FitContainerSpec(name="bad|name")
        with self.assertRaises(FitSkeletonValidationError):
            FitContainerSpec(display_radius=0)

    def test_plan_uses_scene_axis_without_mutating(self) -> None:
        host = FakeFitContainerHost()

        plan = CreateFitSkeleton(host).plan("FitSkeleton", display_radius=2.5)

        self.assertTrue(plan.ready)
        self.assertEqual(plan.spec.up_axis, FitUpAxis.Z)
        self.assertFalse(host.created)
        self.assertEqual(host.transaction_count, 0)

    def test_collision_is_rejected_without_transaction(self) -> None:
        host = FakeFitContainerHost(("|Group|FitSkeleton",))
        use_case = CreateFitSkeleton(host)

        with self.assertRaisesRegex(FitSkeletonValidationError, "未被修改"):
            use_case.apply()

        self.assertFalse(host.created)
        self.assertEqual(host.transaction_count, 0)

    def test_creates_container_and_complete_settings_in_one_transaction(self) -> None:
        host = FakeFitContainerHost()

        result = CreateFitSkeleton(host).apply(
            "FitSkeleton",
            display_radius=2.5,
            vis_gap_default=0.6,
        )

        self.assertTrue(host.created)
        self.assertEqual(result.state.path, "|FitSkeleton")
        self.assertEqual(len(result.settings.settings), 21)
        self.assertEqual(host.transaction_count, 1)

    def test_failed_verification_rolls_back_creation(self) -> None:
        class FaultyHost(FakeFitContainerHost):
            def inspect_fit_container(self, name):
                state = super().inspect_fit_container(name)
                return FitContainerState(
                    path=state.path,
                    short_name=state.short_name,
                    shape=None,
                    display_style=state.display_style,
                    locked_channels=state.locked_channels,
                    local_translation=state.local_translation,
                    local_rotation=state.local_rotation,
                    bounding_size=state.bounding_size,
                )

        host = FaultyHost()
        with self.assertRaisesRegex(RuntimeError, "复检失败"):
            CreateFitSkeleton(host).apply()

        self.assertFalse(host.created)
        self.assertIsNone(host.settings)


if __name__ == "__main__":
    unittest.main()
