import unittest
from contextlib import contextmanager

from adv_py.application import EnsureFitSkeletonSettings
from adv_py.core import (
    FitSkeletonField,
    FitSkeletonSetting,
    FitSkeletonSettings,
    FitSkeletonValidationError,
    default_fit_skeleton_settings,
)


class FakeFitSkeletonSettingsHost:
    def __init__(self, settings):
        self.settings = settings
        self.transaction_count = 0
        self.add_count = 0

    def read_fit_skeleton_settings(self, container_name):
        del container_name
        return self.settings

    @contextmanager
    def transaction(self, label):
        del label
        before = self.settings
        self.transaction_count += 1
        try:
            yield
        except Exception:
            self.settings = before
            raise

    def add_fit_skeleton_setting(self, container, setting):
        self.add_count += 1
        self.settings = FitSkeletonSettings(
            container=container,
            settings=self.settings.settings + (setting,),
        )


class FitSettingsTests(unittest.TestCase):
    def test_complete_settings_are_a_no_op(self) -> None:
        settings = default_fit_skeleton_settings("|FitSkeleton")
        host = FakeFitSkeletonSettingsHost(settings)

        result = EnsureFitSkeletonSettings(host).apply()

        self.assertEqual(result.verified, settings)
        self.assertFalse(result.plan.additions)
        self.assertEqual(host.transaction_count, 0)

    def test_adds_only_missing_settings_and_preserves_existing_values(self) -> None:
        before = FitSkeletonSettings(
            container="|FitSkeleton",
            settings=(
                FitSkeletonSetting(FitSkeletonField.VIS_GEOMETRY, True),
                FitSkeletonSetting(FitSkeletonField.VIS_GAP, 0.4),
                FitSkeletonSetting(
                    FitSkeletonField.PRE_REBUILD_SCRIPT,
                    "user supplied text",
                ),
            ),
        )
        host = FakeFitSkeletonSettingsHost(before)
        use_case = EnsureFitSkeletonSettings(host)

        preview = use_case.plan(vis_gap_default=0.6)
        result = use_case.apply(vis_gap_default=0.6)

        self.assertEqual(len(preview.additions), len(FitSkeletonField) - 3)
        self.assertEqual(result.verified.value(FitSkeletonField.VIS_GAP), 0.4)
        self.assertEqual(
            result.verified.value(FitSkeletonField.PRE_REBUILD_SCRIPT),
            "user supplied text",
        )
        self.assertEqual(host.transaction_count, 1)

    def test_invalid_existing_value_is_rejected_before_transaction(self) -> None:
        settings = FitSkeletonSettings(
            container="|FitSkeleton",
            settings=(FitSkeletonSetting(FitSkeletonField.VIS_GAP, 1.5),),
        )
        host = FakeFitSkeletonSettingsHost(settings)

        with self.assertRaisesRegex(FitSkeletonValidationError, "预检失败"):
            EnsureFitSkeletonSettings(host).apply()

        self.assertEqual(host.transaction_count, 0)
        self.assertEqual(host.add_count, 0)

    def test_failed_post_verification_rolls_back(self) -> None:
        before = FitSkeletonSettings(container="|FitSkeleton", settings=())

        class FaultyHost(FakeFitSkeletonSettingsHost):
            def add_fit_skeleton_setting(self, container, setting):
                self.add_count += 1

        host = FaultyHost(before)
        with self.assertRaisesRegex(RuntimeError, "复检失败"):
            EnsureFitSkeletonSettings(host).apply()

        self.assertEqual(host.settings, before)
        self.assertEqual(host.transaction_count, 1)


if __name__ == "__main__":
    unittest.main()
