"""Extract static Face and eye meshes from a local FBX or Maya scene.

The source file is read only. Output is intended for ignored validation/results.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import maya.standalone
maya.standalone.initialize(name="python")
from maya import cmds


def one_mesh(name: str) -> str:
    matches = cmds.ls(name, long=True, type="transform") or []
    meshes = [path for path in matches if cmds.listRelatives(
        path, shapes=True, noIntermediate=True, type="mesh")]
    if len(meshes) != 1:
        raise ValueError(f"输入网格缺失或重名：{name}")
    return meshes[0]


def static_copy(source: str, name: str) -> str:
    copy = cmds.duplicate(source, name=name, returnRootsOnly=True)[0]
    copy = cmds.parent(copy, world=True, absolute=True)[0]
    descendants = cmds.listRelatives(copy, children=True, fullPath=True,
                                     type="transform") or []
    if descendants:
        cmds.delete(descendants)
    cmds.delete(copy, constructionHistory=True)
    return copy


def export_obj(mesh: str, path: Path) -> None:
    cmds.select(mesh, replace=True)
    cmds.file(str(path), force=True, exportSelected=True, type="OBJexport",
              options="groups=0;ptgroups=0;materials=0;smoothing=1;normals=1")


def main() -> None:
    source = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    if len(sys.argv) not in (5, 6):
        raise ValueError("用法：源场景 输出目录 头部网格 双眼网格，或头部网格 右眼网格 左眼网格")
    head_name = sys.argv[3]
    eye_names = sys.argv[4:]
    if not source.is_file() or source.suffix.lower() not in (
            ".fbx", ".ma", ".mb"):
        raise FileNotFoundError("需要存在的本地 FBX 或 Maya 场景")
    output.mkdir(parents=True, exist_ok=True)
    cmds.file(new=True, force=True)
    cmds.loadPlugin("objExport", quiet=True)
    if source.suffix.lower() == ".fbx":
        cmds.loadPlugin("fbxmaya", quiet=True)
        cmds.file(str(source), i=True, type="FBX", ignoreVersion=True,
                  mergeNamespacesOnClash=False, options="fbx")
    else:
        cmds.file(str(source), open=True, force=True,
                  executeScriptNodes=False)
    head = static_copy(one_mesh(head_name), "head")
    if len(eye_names) == 1:
        eyes = static_copy(one_mesh(eye_names[0]), "eyeOutter")
    else:
        right = static_copy(one_mesh(eye_names[0]), "eyeOutterRight")
        left = static_copy(one_mesh(eye_names[1]), "eyeOutterLeft")
        eyes = cmds.polyUnite(right, left, name="eyeOutter",
                              constructionHistory=False)[0]
        remaining = [path for path in (right, left) if cmds.objExists(path)]
        if remaining:
            cmds.delete(remaining)
    head_obj = output / "head.obj"
    eye_obj = output / "eyes.obj"
    export_obj(head, head_obj)
    export_obj(eyes, eye_obj)
    result = {
        "source_name": source.name,
        "head_mesh": head_name,
        "eye_meshes": list(eye_names),
        "head_vertices": int(cmds.polyEvaluate(head, vertex=True)),
        "head_faces": int(cmds.polyEvaluate(head, face=True)),
        "eye_vertices": int(cmds.polyEvaluate(eyes, vertex=True)),
        "head_obj": str(head_obj),
        "eyes_obj": str(eye_obj),
    }
    (output / "extraction.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print("Static Face/eye extraction:", result["head_vertices"],
          result["eye_vertices"], flush=True)


if __name__ == "__main__":
    main()
