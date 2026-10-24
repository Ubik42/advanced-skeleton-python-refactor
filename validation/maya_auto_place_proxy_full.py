"""Whole source/Python biped scanning on a connected five-digit proxy input.

Proxy parity is distinct from original default-model acceptance.
"""
from pathlib import Path


def main(*,standalone=False,quit_on_finish=True):
    import maya_auto_place_full_trace as trace
    import maya_original_fit_auto_place_sample as sample
    from maya_auto_place_arm_current import fixture
    original=sample.fixture
    original_output=trace.OUT
    original_kind=trace.INPUT_KIND
    sample.fixture=lambda:fixture(full_body=True)
    trace.OUT=Path(__file__).resolve().parents[1]/'validation/results/auto-place-proxy-full'
    trace.INPUT_KIND='connected_voxel_five_digit_biped_proxy'
    try:return trace.main(standalone=standalone,quit_on_finish=quit_on_finish)
    finally:
        sample.fixture=original
        trace.OUT=original_output
        trace.INPUT_KIND=original_kind
