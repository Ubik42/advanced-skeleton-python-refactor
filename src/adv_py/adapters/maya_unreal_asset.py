"""Locate ADV's original asUnreal.ma without importing Maya or copying assets."""
from __future__ import annotations

import os
from pathlib import Path


_PROJECT_SOURCE = (Path(__file__).resolve().parents[3] / 'local' / 'adv_6_925'
                   / 'AdvancedSkeletonFiles' / 'div' / 'asUnreal.ma')


def unreal_asset(explicit_path: str = '') -> Path:
    """Use the selected asset, configured asset, or an installed ADV asset.

    Native asExportMannequin takes this file from AdvancedSkeletonFiles/div
    beside AdvancedSkeleton.mel. Search only nearby script directories; never
    fabricate or download a substitute template.
    """
    configured = explicit_path.strip() or os.environ.get('ADV_6925_UNREAL_FILE', '').strip()
    if configured:
        path = Path(configured).expanduser()
        if path.suffix.lower() != '.ma' or not path.is_file():
            raise FileNotFoundError('原版 asUnreal.ma 模板不存在：' + str(path))
        return path.resolve()
    if _PROJECT_SOURCE.is_file():
        return _PROJECT_SOURCE
    roots = [Path(value).expanduser() for value in
             os.environ.get('MAYA_SCRIPT_PATH', '').split(os.pathsep) if value]
    app_dir = os.environ.get('MAYA_APP_DIR', '').strip()
    app_root = Path(app_dir).expanduser() if app_dir else Path.home() / 'Documents' / 'maya'
    roots.append(app_root / 'scripts')
    try:
        roots.extend(folder / 'scripts' for folder in app_root.iterdir()
                     if folder.is_dir() and folder.name[:1].isdigit())
    except OSError:
        pass
    visited = set()
    for root in roots:
        pending = [(root, 0)]
        while pending:
            folder, depth = pending.pop(0)
            if folder in visited:
                continue
            visited.add(folder)
            for candidate in (folder / 'AdvancedSkeletonFiles' / 'div' / 'asUnreal.ma',
                              folder / 'div' / 'asUnreal.ma', folder / 'asUnreal.ma'):
                if candidate.is_file():
                    return candidate.resolve()
            if depth == 2:
                continue
            try:
                pending.extend((child, depth + 1) for child in folder.iterdir()
                               if child.is_dir())
            except OSError:
                continue
    raise FileNotFoundError('缺少原版 AdvancedSkeletonFiles/div/asUnreal.ma；'
                            '请选择模板或设置 ADV_6925_UNREAL_FILE')
