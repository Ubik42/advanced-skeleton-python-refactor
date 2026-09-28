"""Add Bendy and Micro animator channels to the character registry."""
from __future__ import annotations

from dataclasses import replace

from adv_py.core.character_registry import (
    CharacterChannel, CharacterRegistration, encode_registration,
)
from adv_py.core.fit_bendy import FitBendyChainSpec


class RegisterBendyControls:
    def __init__(self, host) -> None:
        self._host = host

    def apply(self, before: CharacterRegistration,
              chains: tuple[FitBendyChainSpec, ...]
              ) -> CharacterRegistration:
        if not chains:
            return before
        if self._host.read_character_registration() != before:
            raise ValueError("Bendy 登记前角色文档已变化")
        channels = list(before.channels)
        nodes = list(before.nodes)
        keys = {item.key for item in channels}
        plugs = {(item.node, item.attribute) for item in channels}
        known = {item.path for item in nodes}

        def add(key: str, path: str, attribute: str) -> None:
            if key in keys or (path, attribute) in plugs:
                raise ValueError("Bendy 登记通道冲突：" + key)
            channels.append(CharacterChannel(key, path, attribute))
            keys.add(key)
            plugs.add((path, attribute))
            missing = []
            parent = path
            while parent and parent not in known:
                missing.append(parent)
                parent = parent.rsplit("|", 1)[0]
            for item in reversed(missing):
                nodes.append(self._host.capture_inbetween_registration_node(
                    item))
                known.add(item)

        attrs = tuple(prefix + axis for prefix in
                      ("translate", "rotate", "scale") for axis in "XYZ")
        for chain in chains:
            def bend_path(control: str) -> str:
                prefix = "|AdvPy_BendSystem|" + control + "Offset|"
                if (control == chain.control_names[0]
                        and chain.child_junction_control):
                    prefix += chain.circular_name + "|"
                return prefix + control

            for control in chain.control_names:
                path = bend_path(control)
                for attr in attrs:
                    add("bendy." + control + "." + attr, path, attr)
            add("bendy." + chain.control_names[0] + ".microVis",
                bend_path(chain.control_names[0]), "microVis")
            if chain.parent_bendy:
                start_control = chain.control_names[1]
                path = ("|AdvPy_BendSystem|" + start_control + "Offset|"
                        + start_control + "|" + chain.junction_offset_name
                        + "|" + chain.junction_name)
                for attr in attrs:
                    add("bendy." + chain.junction_name + "." + attr,
                        path, attr)
                add("bendy." + chain.junction_name + ".circular",
                    path, "circular")
            for offset, control in zip(chain.micro_offset_names,
                                       chain.micro_control_names):
                path = "|AdvPy_MicroSystem|" + offset + "|" + control
                for attr in attrs:
                    add("micro." + control + "." + attr, path, attr)
        after = replace(before, channels=tuple(channels), nodes=tuple(nodes))
        encode_registration(after)
        with self._host.transaction("登记 Bendy 控制器"):
            self._host.write_character_registration_extension(before, after)
            if self._host.read_character_registration() != after:
                raise RuntimeError("Bendy 控制器登记读回不一致")
        return after
