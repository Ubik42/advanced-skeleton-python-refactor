"""Atomic file operations for portable MoCap mapping presets."""
import os
from pathlib import Path
import tempfile

from adv_py.core.mocap_mapping import MocapMappingValidationError
from adv_py.core.mocap_preset import decode_mocap_mapping_preset, encode_mocap_mapping_preset


def save_mocap_mapping_preset(preset,destination):
    target=Path(destination).expanduser().absolute()
    if target.suffix.casefold()!='.json' or not target.parent.is_dir():
        raise MocapMappingValidationError('动捕映射预设目标必须是现有目录中的 .json 文件')
    if target.exists():raise FileExistsError(target)
    text=encode_mocap_mapping_preset(preset)
    handle,temporary=tempfile.mkstemp(prefix='.mocap-preset-',suffix='.tmp',dir=target.parent)
    try:
        with os.fdopen(handle,'w',encoding='utf8',newline='\n') as stream:
            stream.write(text);stream.flush();os.fsync(stream.fileno())
        if decode_mocap_mapping_preset(Path(temporary).read_text(encoding='utf8'))!=preset:
            raise RuntimeError('动捕映射预设临时文件复检失败')
        os.link(temporary,target)
    finally:Path(temporary).unlink(missing_ok=True)
    return target


def load_mocap_mapping_preset(source):
    path=Path(source).expanduser()
    if path.suffix.casefold()!='.json' or path.stat().st_size>250_000:
        raise MocapMappingValidationError('动捕映射预设文件类型或大小无效')
    return decode_mocap_mapping_preset(path.read_text(encoding='utf8'))
