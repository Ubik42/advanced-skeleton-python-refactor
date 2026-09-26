"""Validate post-build control-curve scale, auto-scale, and color workflows."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _close(left, right, tolerance=1e-6):
    return all(abs(a - b) <= tolerance for a, b in zip(left, right))


def _same_state(left, right):
    return (
        left.control == right.control
        and _close(left.world_matrix, right.world_matrix)
        and len(left.shapes) == len(right.shapes)
        and all(
            old.path == new.path
            and old.degree == new.degree
            and old.form == new.form
            and len(old.points) == len(new.points)
            and all(_close(a, b) for a, b in zip(old.points, new.points))
            for old, new in zip(left.shapes, right.shapes)
        )
    )


def _scaled(before, after, factor):
    return (
        before.control == after.control
        and _close(before.world_matrix, after.world_matrix)
        and len(before.shapes) == len(after.shapes)
        and all(
            old.path == new.path
            and old.degree == new.degree
            and old.form == new.form
            and len(old.points) == len(new.points)
            and all(
                _close(tuple(value * factor for value in old_point), new_point)
                for old_point, new_point in zip(old.points, new.points)
            )
            for old, new in zip(before.shapes, after.shapes)
        )
    )


def _same_color_state(left, right):
    return (
        left.control == right.control
        and left.semantic_keys == right.semantic_keys
        and len(left.shapes) == len(right.shapes)
        and all(
            old.path == new.path
            and old.override_enabled == new.override_enabled
            and old.rgb_enabled == new.rgb_enabled
            and _close(old.color, new.color)
            for old, new in zip(left.shapes, right.shapes)
        )
    )


def _same_color_states(left, right):
    return len(left) == len(right) and all(
        _same_color_state(a, b) for a, b in zip(left, right))


def _same_icon_geometry(source, target):
    return (
        len(source.shapes) == len(target.shapes)
        and all(
            old.degree == new.degree and old.form == new.form
            and len(old.points) == len(new.points)
            and all(_close(a, b) for a, b in zip(old.points, new.points))
            for old, new in zip(source.shapes, target.shapes)
        )
    )


def _shape_style(cmds, shape):
    return (
        bool(cmds.getAttr(shape + ".overrideEnabled")),
        bool(cmds.getAttr(shape + ".overrideRGBColors")),
        int(cmds.getAttr(shape + ".overrideColor")),
        tuple(float(value) for value in
              cmds.getAttr(shape + ".overrideColorRGB")[0]),
        float(cmds.getAttr(shape + ".lineWidth")),
    )


def main(report: Path) -> int:
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        from maya import cmds
        from adv_py.adapters import MayaBodyBuildHost
        from adv_py.application import (
            BuildSyntheticBodySourceFit, CreateFitSkeleton, ResolveBodyCharacter,
        )
        from adv_py.core import (
            control_curve_side, plan_control_curve_auto_scale,
            plan_control_curve_colors, plan_control_curve_mirror,
            ControlCurveMirrorPair,
        )
        from adv_py.product.maya_panel_controller import MayaPanelController

        report.parent.mkdir(parents=True, exist_ok=True)
        cmds.file(new=True, force=True)
        cmds.upAxis(axis="z", rotateView=False)
        cmds.undoInfo(state=True)
        host = MayaBodyBuildHost()
        container = CreateFitSkeleton(host).apply().state.path
        BuildSyntheticBodySourceFit(host).apply(container)
        controller = MayaPanelController()
        controller.body_build(":")

        resolver = ResolveBodyCharacter(host)
        character_name = resolver.discover()[0]
        registration = resolver.execute(character_name)
        candidates = tuple(dict.fromkeys(
            channel.node for channel in registration.channels))
        semantic_map = {}
        for channel in registration.channels:
            semantic_map.setdefault(channel.node, []).append(channel.key)
        semantics = tuple((control, tuple(keys))
                          for control, keys in semantic_map.items())
        before_all = host.capture_control_curves(candidates, strict=False)
        by_control = {state.control: state for state in before_all}
        mirror_sources = tuple(state for state in before_all
            if re.search(r"_R(?=\||$)", state.control)
            and re.sub(r"_R(?=\||$)", "_L", state.control) in by_control)
        mirror_source = mirror_sources[0]
        mirror_target = by_control[
            re.sub(r"_R(?=\||$)", "_L", mirror_source.control)]
        sculpt_shape = mirror_source.shapes[0]
        sculpt_point = list(sculpt_shape.points[0])
        sculpt_point[1] += .37
        cmds.xform(sculpt_shape.path + ".cv[0]", objectSpace=True,
                   translation=sculpt_point)
        before_all = host.capture_control_curves(candidates, strict=False)
        by_control = {state.control: state for state in before_all}
        mirror_source = by_control[mirror_source.control]
        mirror_target = by_control[mirror_target.control]
        target = before_all[0].control
        skin = cmds.polyCube(name="AutoScaleSkin", width=16., height=10.,
                             depth=40.)[0]
        cmds.setAttr(skin + ".translateZ", 20.)
        custom = cmds.curve(name="CustomControlIcon", degree=1,
            point=((-1., 0., 0.), (0., 1.5, 0.), (1., 0., 0.),
                   (0., -1.5, 0.), (-1., 0., 0.)))
        custom_ring = cmds.circle(name="CustomControlIconRing", normal=(0, 0, 1),
                                  radius=.55, sections=8, constructionHistory=False)[0]
        ring_shape = (cmds.listRelatives(
            custom_ring, shapes=True, fullPath=True, type="nurbsCurve") or [])[0]
        cmds.parent(ring_shape, custom, shape=True, relative=True)
        cmds.delete(custom_ring)
        custom = (cmds.ls(custom, long=True, type="transform") or [custom])[0]
        marker = cmds.createNode("transform", name="CurveScaleSelection",
                                 skipSelect=True)
        cmds.select(marker, replace=True)
        selection_before = tuple(cmds.ls(selection=True, long=True) or [])

        explicit_mirror_plan = plan_control_curve_mirror((
            ControlCurveMirrorPair(mirror_source, mirror_target),))
        explicit_mirror_count = controller.control_curves_mirror(
            ":", (mirror_source.control,), "R")
        explicit_mirror_after = host.capture_control_curves(
            (mirror_target.control,), strict=True)[0]
        explicit_mirror_applied = _same_state(
            explicit_mirror_after, explicit_mirror_plan.after[0])
        mirror_selection_preserved = tuple(
            cmds.ls(selection=True, long=True) or []) == selection_before
        cmds.undo()
        explicit_mirror_undo = _same_state(
            host.capture_control_curves(
                (mirror_target.control,), strict=True)[0], mirror_target)
        cmds.redo()
        explicit_mirror_redo = _same_state(
            host.capture_control_curves(
                (mirror_target.control,), strict=True)[0],
            explicit_mirror_plan.after[0])
        cmds.undo()

        mirror_pairs = tuple(ControlCurveMirrorPair(
            by_control[source.control],
            by_control[re.sub(r"_R(?=\||$)", "_L", source.control)])
            for source in mirror_sources)
        all_mirror_plan = plan_control_curve_mirror(mirror_pairs)
        all_mirror_count = controller.control_curves_mirror(":", (), "R")
        all_mirror_after = host.capture_control_curves(
            tuple(state.control for state in all_mirror_plan.after), strict=True)
        all_mirror_applied = (
            all_mirror_count == len(mirror_pairs)
            and all(_same_state(found, expected) for found, expected in
                    zip(all_mirror_after, all_mirror_plan.after)))
        cmds.undo()
        all_mirror_undo = all(_same_state(
            found, pair.target) for found, pair in zip(
                host.capture_control_curves(
                    tuple(pair.target.control for pair in mirror_pairs),
                    strict=True), mirror_pairs))

        swap_targets = (before_all[0], before_all[1])
        swap_styles = []
        for index, state in enumerate(swap_targets):
            shape = state.shapes[0].path
            cmds.setAttr(shape + ".overrideEnabled", True)
            cmds.setAttr(shape + ".overrideRGBColors", True)
            cmds.setAttr(shape + ".overrideColorRGB", .2 + index * .2,
                         .4, .8 - index * .2, type="double3")
            cmds.setAttr(shape + ".lineWidth", 2. + index)
            swap_styles.append(_shape_style(cmds, shape))
        custom_before = host.capture_control_curves((custom,), strict=True)[0]
        swap_count = controller.control_curves_swap(
            ":", tuple(state.control for state in swap_targets), custom)
        swap_after = host.capture_control_curves(
            tuple(state.control for state in swap_targets), strict=True)
        swap_applied = swap_count == 2 and all(
            _same_icon_geometry(custom_before, state)
            and _close(state.world_matrix, before.world_matrix)
            for state, before in zip(swap_after, swap_targets))
        swap_style_preserved = all(
            all(_shape_style(cmds, shape.path) == style
                for shape in state.shapes)
            for state, style in zip(swap_after, swap_styles))
        swap_source_preserved = _same_state(
            host.capture_control_curves((custom,), strict=True)[0], custom_before)
        swap_selection_preserved = tuple(
            cmds.ls(selection=True, long=True) or []) == selection_before
        cmds.undo()
        swap_undo = all(_same_state(found, expected) for found, expected in zip(
            host.capture_control_curves(
                tuple(state.control for state in swap_targets), strict=True),
            swap_targets))
        cmds.redo()
        swap_redo = all(_same_icon_geometry(custom_before, state) for state in
            host.capture_control_curves(
                tuple(state.control for state in swap_targets), strict=True))
        cmds.undo()

        auto_metrics = host.measure_control_curve_auto_scale(
            candidates, skin, semantics, strict=False)
        global_metric = next(row for row in auto_metrics
                             if any(key == "global" or key.startswith("global.")
                                    for key in row.semantic_keys))
        explicit_auto_plan = plan_control_curve_auto_scale(
            skin, (global_metric,))
        explicit_auto_count = controller.control_curves_auto_scale(
            ":", (global_metric.state.control,), skin)
        explicit_auto_after = host.capture_control_curves(
            (global_metric.state.control,), strict=True)[0]
        explicit_auto_applied = _same_state(
            explicit_auto_after, explicit_auto_plan.changes[0].after)
        auto_selection_preserved = tuple(
            cmds.ls(selection=True, long=True) or []) == selection_before
        cmds.undo()
        explicit_auto_undo = _same_state(
            host.capture_control_curves(
                (global_metric.state.control,), strict=True)[0],
            global_metric.state)
        cmds.redo()
        explicit_auto_redo = _same_state(
            host.capture_control_curves(
                (global_metric.state.control,), strict=True)[0],
            explicit_auto_plan.changes[0].after)
        cmds.undo()

        all_auto_plan = plan_control_curve_auto_scale(skin, auto_metrics)
        all_auto_count = controller.control_curves_auto_scale(":", (), skin)
        all_auto_after = host.capture_control_curves(candidates, strict=False)
        all_auto_applied = (
            all_auto_count == len(before_all)
            and all(_same_state(actual, change.after)
                    for actual, change in zip(all_auto_after,
                                              all_auto_plan.changes)))
        cmds.undo()
        all_auto_undo = all(
            _same_state(old, restored)
            for old, restored in zip(
                before_all, host.capture_control_curves(candidates, strict=False)))

        explicit_count = controller.control_curves_scale(":", (target,), 1.25)
        explicit_after = host.capture_control_curves((target,), strict=True)[0]
        explicit_scaled = _scaled(before_all[0], explicit_after, 1.25)
        selection_preserved = tuple(
            cmds.ls(selection=True, long=True) or []) == selection_before
        cmds.undo()
        explicit_undo = _same_state(
            before_all[0], host.capture_control_curves((target,), strict=True)[0])
        cmds.redo()
        explicit_redo = _scaled(
            before_all[0], host.capture_control_curves((target,), strict=True)[0], 1.25)
        cmds.undo()

        all_count = controller.control_curves_scale(":", (), 1.1)
        all_after = host.capture_control_curves(candidates, strict=False)
        all_scaled = all_count == len(before_all) and all(
            _scaled(old, new, 1.1) for old, new in zip(before_all, all_after))
        cmds.undo()
        all_undo = all(
            _same_state(old, new)
            for old, new in zip(
                before_all, host.capture_control_curves(candidates, strict=False)))
        cmds.redo()

        before_colors = host.capture_control_curve_colors(
            candidates, semantics, strict=False)
        right = next(state for state in before_colors
                     if control_curve_side(state) == "right")
        expected_right = plan_control_curve_colors((right,), "side").after[0]
        explicit_color_count = controller.control_curves_color(
            ":", (right.control,), "side")
        explicit_color_after = host.capture_control_curve_colors(
            (right.control,), semantics, strict=True)[0]
        explicit_color_applied = _same_color_state(
            explicit_color_after, expected_right)
        color_selection_preserved = tuple(
            cmds.ls(selection=True, long=True) or []) == selection_before
        cmds.undo()
        explicit_color_undo = _same_color_state(
            host.capture_control_curve_colors(
                (right.control,), semantics, strict=True)[0], right)
        cmds.redo()
        explicit_color_redo = _same_color_state(
            host.capture_control_curve_colors(
                (right.control,), semantics, strict=True)[0], expected_right)
        cmds.undo()

        expected_all_colors = plan_control_curve_colors(
            before_colors, "type").after
        all_color_count = controller.control_curves_color(":", (), "type")
        all_colors_after = host.capture_control_curve_colors(
            candidates, semantics, strict=False)
        all_colors_applied = (
            all_color_count == len(before_colors)
            and _same_color_states(all_colors_after, expected_all_colors))
        cmds.undo()
        all_colors_undo = _same_color_states(
            host.capture_control_curve_colors(
                candidates, semantics, strict=False), before_colors)
        cmds.redo()

        with tempfile.TemporaryDirectory(prefix="adv-py-curves-",
                                         dir=report.parent.resolve()) as folder:
            scene = Path(folder) / "scaled.ma"
            cmds.file(rename=str(scene))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(new=True, force=True)
            cmds.file(str(scene), open=True, force=True)
            reopened = host.capture_control_curves(candidates, strict=False)
            reopen_preserved = all(
                _scaled(old, new, 1.1)
                for old, new in zip(before_all, reopened))
            reopened_colors = host.capture_control_curve_colors(
                candidates, semantics, strict=False)
            color_reopen_preserved = _same_color_states(
                reopened_colors, expected_all_colors)
            persisted_auto_metrics = host.measure_control_curve_auto_scale(
                candidates, skin, semantics, strict=False)
            persisted_auto_plan = plan_control_curve_auto_scale(
                skin, persisted_auto_metrics)
            controller.control_curves_auto_scale(":", (), skin)
            auto_scene = Path(folder) / "auto-scaled.ma"
            cmds.file(rename=str(auto_scene))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(new=True, force=True)
            cmds.file(str(auto_scene), open=True, force=True)
            auto_reopened = host.capture_control_curves(candidates, strict=False)
            auto_save_reopen_preserved = all(
                _same_state(actual, change.after)
                for actual, change in zip(auto_reopened,
                                          persisted_auto_plan.changes))
            current_map = {state.control: state for state in auto_reopened}
            persisted_mirror_pairs = tuple(ControlCurveMirrorPair(
                current_map[pair.source.control], current_map[pair.target.control])
                for pair in mirror_pairs)
            persisted_mirror_plan = plan_control_curve_mirror(
                persisted_mirror_pairs)
            controller.control_curves_mirror(":", (), "R")
            mirror_scene = Path(folder) / "mirrored.ma"
            cmds.file(rename=str(mirror_scene))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(new=True, force=True)
            cmds.file(str(mirror_scene), open=True, force=True)
            mirror_reopened = host.capture_control_curves(
                tuple(state.control for state in persisted_mirror_plan.after),
                strict=True)
            mirror_save_reopen_preserved = all(
                _same_state(found, expected) for found, expected in
                zip(mirror_reopened, persisted_mirror_plan.after))
            current_custom = host.capture_control_curves((custom,), strict=True)[0]
            controller.control_curves_swap(
                ":", tuple(state.control for state in swap_targets), custom)
            swap_scene = Path(folder) / "swapped.ma"
            cmds.file(rename=str(swap_scene))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(new=True, force=True)
            cmds.file(str(swap_scene), open=True, force=True)
            swap_reopened = host.capture_control_curves(
                tuple(state.control for state in swap_targets), strict=True)
            swap_save_reopen_preserved = all(
                _same_icon_geometry(current_custom, state)
                for state in swap_reopened)

        checks = {
            "curves_discovered": len(before_all) > 1,
            "explicit_world_mirror_route": explicit_mirror_count == 1
                and explicit_mirror_applied,
            "mirror_selection_preserved": mirror_selection_preserved,
            "explicit_mirror_single_undo_redo": explicit_mirror_undo
                and explicit_mirror_redo,
            "registered_all_mirror_route": all_mirror_applied,
            "registered_all_mirror_single_undo": all_mirror_undo,
            "mirror_save_reopen_preserved": mirror_save_reopen_preserved,
            "custom_icon_multi_target_route": swap_applied,
            "custom_icon_source_preserved": swap_source_preserved,
            "custom_icon_style_preserved": swap_style_preserved,
            "custom_icon_selection_preserved": swap_selection_preserved,
            "custom_icon_single_undo_redo": swap_undo and swap_redo,
            "custom_icon_save_reopen_preserved": swap_save_reopen_preserved,
            "explicit_mesh_auto_scale_route": explicit_auto_count == 1
                and explicit_auto_applied,
            "auto_scale_selection_preserved": auto_selection_preserved,
            "explicit_auto_scale_single_undo_redo": explicit_auto_undo
                and explicit_auto_redo,
            "registered_all_mesh_auto_scale_route": all_auto_applied,
            "registered_all_auto_scale_single_undo": all_auto_undo,
            "auto_scale_save_reopen_preserved": auto_save_reopen_preserved,
            "explicit_product_route": explicit_count == 1 and explicit_scaled,
            "selection_preserved": selection_preserved,
            "explicit_single_undo_redo": explicit_undo and explicit_redo,
            "registered_all_product_route": all_scaled,
            "registered_all_single_undo": all_undo,
            "save_reopen_preserved": reopen_preserved,
            "explicit_side_color_route": explicit_color_count == 1
                and explicit_color_applied,
            "color_selection_preserved": color_selection_preserved,
            "explicit_color_single_undo_redo": explicit_color_undo
                and explicit_color_redo,
            "registered_all_type_color_route": all_colors_applied,
            "registered_all_color_single_undo": all_colors_undo,
            "color_save_reopen_preserved": color_reopen_preserved,
        }
        payload = {
            **checks,
            "registered_curve_controls": len(before_all),
            "status": "passed" if all(checks.values()) else "failed",
        }
        report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        return 0 if all(checks.values()) else 1
    finally:
        maya.standalone.uninitialize()


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
