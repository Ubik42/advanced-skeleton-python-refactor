"""Add Bendy and Micro animator channels to the character registry."""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import replace
from typing import Protocol

from adv_py.core.character_registry import (
    CharacterChannel, CharacterNode, CharacterRegistration,
    encode_registration,
)
from adv_py.core.fit_bendy import FitBendyChainSpec


class BendyRegistrationHost(Protocol):
    def read_character_registration(self) -> CharacterRegistration: ...

    def capture_inbetween_registration_node(
        self, path: str,
    ) -> CharacterNode: ...

    def capture_bendy_control_path(
        self, name: str, ancestors: tuple[str, ...],
    ) -> str: ...

    def write_character_registration_extension(
        self, before: CharacterRegistration,
        after: CharacterRegistration,
    ) -> None: ...

    def transaction(self, label: str) -> AbstractContextManager[None]: ...


class RegisterBendyControls:
    def __init__(self, host: BendyRegistrationHost) -> None:
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
            bend_paths = {}
            for control in chain.control_names:
                ancestors = (control + "Offset", "AdvPy_BendSystem")
                if (control == chain.control_names[0]
                        and chain.child_junction_control):
                    ancestors = (chain.circular_name, *ancestors)
                extra = control + "Extra"
                extra_path = self._host.capture_bendy_control_path(
                    extra, ancestors)
                path = self._host.capture_bendy_control_path(
                    control, (extra, *ancestors))
                bend_paths[control] = path
                for attr in attrs:
                    add("bendy." + control + "." + attr, path, attr)
                    add("bendy." + control + ".extra." + attr,
                        extra_path, attr)
            add("bendy." + chain.control_names[0] + ".microVis",
                bend_paths[chain.control_names[0]], "microVis")
            if chain.parent_bendy:
                start_control = chain.control_names[1]
                extra = chain.junction_extra_name
                ancestors = (
                    chain.junction_offset_name, start_control,
                    start_control + "Extra",
                    start_control + "Offset", "AdvPy_BendSystem")
                extra_path = self._host.capture_bendy_control_path(
                    extra, ancestors)
                path = self._host.capture_bendy_control_path(
                    chain.junction_name,
                    (extra, *ancestors))
                for attr in attrs:
                    add("bendy." + chain.junction_name + "." + attr,
                        path, attr)
                    add("bendy." + chain.junction_name + ".extra."
                        + attr, extra_path, attr)
                add("bendy." + chain.junction_name + ".circular",
                    path, "circular")
            for offset, extra, control in zip(
                    chain.micro_offset_names, chain.micro_extra_names,
                    chain.micro_control_names):
                path = self._host.capture_bendy_control_path(
                    control, (extra, offset, "AdvPy_MicroSystem"))
                for attr in attrs:
                    add("micro." + control + "." + attr, path, attr)
        after = replace(before, channels=tuple(channels), nodes=tuple(nodes))
        encode_registration(after)
        with self._host.transaction("登记 Bendy 控制器"):
            self._host.write_character_registration_extension(before, after)
            if self._host.read_character_registration() != after:
                raise RuntimeError("Bendy 控制器登记读回不一致")
        return after
