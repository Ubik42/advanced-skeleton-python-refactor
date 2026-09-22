"""Isolated Maya scene lifecycle for the headless product entry."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile


class MayaSceneGateway:
    def __init__(self):
        self._started = False
        self._source: Path | None = None

    def start(self) -> None:
        import maya.standalone
        maya.standalone.initialize(name="python")
        self._started = True

    def close(self) -> None:
        if self._started:
            import maya.standalone
            maya.standalone.uninitialize()
            self._started = False

    def open(self, source: Path) -> None:
        from maya import cmds

        source = source.resolve(strict=True)
        if not source.is_file() or source.suffix.lower() not in (".ma", ".mb"):
            raise ValueError("输入必须是现有 Maya .ma 或 .mb 场景")
        cmds.file(str(source), open=True, force=True)
        cmds.undoInfo(state=True)
        self._source = source

    def namespaces(self) -> tuple[str | None, ...]:
        from maya import cmds

        names = cmds.namespaceInfo(listOnlyNamespaces=True, recurse=True) or []
        return (None,) + tuple(sorted(set(name.lstrip(":") for name in names
            if name.lstrip(":") not in ("UI", "shared"))))

    def save_new(self, output: Path) -> Path:
        from maya import cmds

        output = self.preflight_output(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(
            prefix="." + output.stem + "-", suffix=".ma", dir=output.parent)
        os.close(handle)
        temporary = Path(temporary_name)
        try:
            cmds.file(rename=str(temporary))
            cmds.file(save=True, type="mayaAscii", force=True)
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise RuntimeError("Maya 未写出有效场景")
            os.link(temporary, output)
            return output
        finally:
            temporary.unlink(missing_ok=True)

    def preflight_output(self, output: Path) -> Path:
        if self._source is None:
            raise RuntimeError("尚未打开输入场景")
        output = output.resolve()
        if output.suffix.lower() != ".ma" or output == self._source:
            raise ValueError("输出必须是不同于输入的 .ma 场景")
        if output.exists():
            raise FileExistsError("输出场景已存在：" + str(output))
        return output
