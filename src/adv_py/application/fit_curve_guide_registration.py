"""Register CurveGuide animator controls and their owned DAG graph."""
from __future__ import annotations

from dataclasses import replace

from adv_py.core.body_fit_curve_guide import BodyFitCurveGuideBuilt
from adv_py.core.character_registry import (
    CharacterChannel, CharacterRegistration, encode_registration,
)


class RegisterFitCurveGuides:
    def __init__(self, host) -> None:
        self._host = host

    def apply(self, before: CharacterRegistration,
              built: tuple[BodyFitCurveGuideBuilt, ...],
              *, main_control: str,
              ) -> CharacterRegistration:
        if not built:
            return before
        if self._host.read_character_registration() != before:
            raise ValueError("Curve Guide 登记前角色文档已变化")
        keys = {item.key for item in before.channels}
        plugs = {(item.node, item.attribute) for item in before.channels}
        channels = []
        added: dict[str, tuple[str, str]] = {}
        nodes = list(before.nodes)
        known = {node.path for node in nodes}

        def add(key: str, path: str, attr: str) -> None:
            plug = (path, attr)
            if added.get(key) == plug:
                return
            if key in keys or plug in plugs:
                raise ValueError("Curve Guide 动画通道冲突：" + key)
            keys.add(key)
            plugs.add(plug)
            added[key] = plug
            channels.append(CharacterChannel(key, path, attr))

        add("fit.curve_guide.targets_visibility", main_control,
            "guideTargetsVis")

        for item in built:
            curve_name = item.curve_path.rsplit("|", 1)[-1]
            add("fit.curve_guide." + curve_name + ".blend",
                item.curve_path, "blend")
            ik_name = item.ik_control_path.rsplit("|", 1)[-1]
            for kind in ("translate", "rotate"):
                for axis in "XYZ":
                    add("fit.curve_guide." + ik_name + "."
                        + kind + axis, item.ik_control_path,
                        kind + axis)
            for control in item.cv_control_paths:
                leaf = control.rsplit("|", 1)[-1]
                for kind in ("translate", "rotate"):
                    for axis in "XYZ":
                        add("fit.curve_guide." + leaf + "."
                            + kind + axis, control, kind + axis)
                add("fit.curve_guide." + leaf + ".follow",
                    control, "follow")
            for path in (item.curve_path, item.ik_control_path,
                         *item.cv_control_paths, *item.helper_paths):
                missing = []
                node = path
                while node and node not in known:
                    missing.append(node)
                    node = node.rsplit("|", 1)[0]
                for path_to_capture in reversed(missing):
                    nodes.append(self._host.capture_character_registration_node(
                        path_to_capture))
                    known.add(path_to_capture)
        after = replace(before, channels=before.channels + tuple(channels),
                        nodes=tuple(nodes))
        encode_registration(after)
        with self._host.transaction("登记 Curve Guide"):
            self._host.write_character_registration_extension(before, after)
            if self._host.read_character_registration() != after:
                raise RuntimeError("Curve Guide 登记读回不一致")
        return after
