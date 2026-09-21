"""Read FBX in isolated mayapy, then create verified animation in the scene."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Protocol

from adv_py.core.mocap_clip import MocapClip,decode_mocap_clip
from adv_py.core.mocap_source import MocapSourceSnapshot,MocapSourceSummary,MocapSourceValidationError,summarize_mocap_source


@dataclass(frozen=True,slots=True)
class MocapFbxImportPlan:
    source: Path
    namespace: str
    byte_count: int
    content_sha256: str


@dataclass(frozen=True,slots=True)
class MocapFbxImportResult:
    plan: MocapFbxImportPlan
    clip: MocapClip
    snapshot: MocapSourceSnapshot
    summary: MocapSourceSummary


class MocapFbxImportHost(Protocol):
    def mocap_scene_units(self) -> tuple[str,str,str]: ...
    def preflight_mocap_clip_import(self,namespace: str,clip: MocapClip | None) -> None: ...
    def create_mocap_clip(self,namespace: str,clip: MocapClip) -> MocapSourceSnapshot: ...


def _digest(path):
    result=sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):result.update(block)
    return result.hexdigest()


class ImportMocapFbx:
    def __init__(self,host: MocapFbxImportHost):self._host=host

    def plan(self,source,*,namespace):
        original=Path(source).expanduser()
        path=original.resolve()
        if (original.is_symlink() or path.suffix.casefold()!='.fbx' or not path.is_file()
                or not 64<=path.stat().st_size<=2_000_000_000):
            raise MocapSourceValidationError('动捕导入来源必须是非空且大小受限的普通 FBX 文件')
        if not isinstance(namespace,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',namespace):
            raise MocapSourceValidationError('动捕导入命名空间必须是独立的可移植标识')
        self._host.preflight_mocap_clip_import(namespace,None)
        return MocapFbxImportPlan(path,namespace,path.stat().st_size,_digest(path))

    def apply(self,source,*,namespace):
        plan=self.plan(source,namespace=namespace)
        worker=Path(__file__).resolve().parents[1]/'adapters'/'maya_mocap_fbx_worker.py'
        units=self._host.mocap_scene_units()
        with tempfile.TemporaryDirectory(prefix='advpy-mocap-fbx-') as directory:
            output=Path(directory)/'clip.json'
            run=subprocess.run([sys.executable,str(worker),str(plan.source),str(output),*units],
                               capture_output=True,text=True,timeout=300,check=False)
            if run.returncode or not output.is_file() or output.stat().st_size>50_000_000:
                raise MocapSourceValidationError('独立 Maya 进程读取动捕 FBX 失败：'+run.stderr[-1600:])
            clip=decode_mocap_clip(output.read_text(encoding='utf8'))
        if plan.source.stat().st_size!=plan.byte_count or _digest(plan.source)!=plan.content_sha256:
            raise MocapSourceValidationError('动捕 FBX 文件在读取期间发生变化')
        self._host.preflight_mocap_clip_import(plan.namespace,clip)
        snapshot=self._host.create_mocap_clip(plan.namespace,clip)
        return MocapFbxImportResult(plan,clip,snapshot,summarize_mocap_source(snapshot))
