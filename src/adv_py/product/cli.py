"""Maya standalone operations over application use cases."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from adv_py.application import (ApplyBodyCharacterAnimation,
    ApplyBodyCharacterPose, ApplyFacePerformance, BuildFaceBlendShapes, CaptureBodyCharacterAnimation,
    CaptureBodyCharacterPose, GenerateFaceTarget, ResolveBodyCharacter,
    InspectBodyCharacterPresets, load_character_animation, load_character_pose, save_character_animation,
    save_character_pose, RebuildBodyCharacter)
from adv_py.core import (FaceLandmark, FaceShapeKind, FaceTarget,
                         face_performance_from_json)
from adv_py.core.character_registry import safe_json


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="adv-rig",
        description="在独立 Maya 后台进程中查看角色或生成面部资产。")
    commands = result.add_subparsers(dest="command", required=True)
    characters = commands.add_parser("characters", help="列出场景中的角色登记")
    characters.add_argument("scene", type=Path)
    target = commands.add_parser("face-target", help="由顶点标记生成表情或口型目标")
    target.add_argument("scene", type=Path)
    target.add_argument("--namespace", required=True)
    target.add_argument("--neutral", required=True)
    target.add_argument("--name", required=True)
    target.add_argument("--kind", choices=tuple(kind.value for kind in FaceShapeKind), required=True)
    target.add_argument("--target", required=True)
    target.add_argument("--landmarks", type=Path, required=True)
    target.add_argument("--output", type=Path, required=True)
    animation = commands.add_parser("face-animation", help="写入已校验的面部动画文档")
    animation.add_argument("scene", type=Path)
    animation.add_argument("--namespace", required=True)
    animation.add_argument("--control", required=True)
    animation.add_argument("--clip", type=Path, required=True)
    animation.add_argument("--output", type=Path, required=True)
    face_build = commands.add_parser("face-build", help="由现有目标网格构建面部控制与变形器")
    face_build.add_argument("scene", type=Path)
    face_build.add_argument("--namespace", required=True)
    face_build.add_argument("--spec", type=Path, required=True)
    face_build.add_argument("--control-name", default="AdvPy_FaceControls")
    face_build.add_argument("--deformer-name", default="AdvPy_FaceBlendShape")
    face_build.add_argument("--output", type=Path, required=True)
    pose_capture = commands.add_parser("pose-capture", help="捕获已登记角色的静态姿态文档")
    pose_capture.add_argument("scene", type=Path)
    pose_capture.add_argument("--namespace", required=True)
    pose_capture.add_argument("--frame", type=int)
    pose_capture.add_argument("--output", type=Path, required=True)
    pose_apply = commands.add_parser("pose-apply", help="将静态姿态应用到角色")
    pose_apply.add_argument("scene", type=Path)
    pose_apply.add_argument("--namespace", required=True)
    pose_apply.add_argument("--pose", type=Path, required=True)
    pose_apply.add_argument("--output", type=Path, required=True)
    clip_capture = commands.add_parser("animation-capture", help="采样全身动画片段")
    clip_capture.add_argument("scene", type=Path)
    clip_capture.add_argument("--namespace", required=True)
    clip_capture.add_argument("--start", type=int, required=True)
    clip_capture.add_argument("--end", type=int, required=True)
    clip_capture.add_argument("--step", type=int, default=1)
    clip_capture.add_argument("--output", type=Path, required=True)
    clip_apply = commands.add_parser("animation-apply", help="写入全身动画片段")
    clip_apply.add_argument("scene", type=Path)
    clip_apply.add_argument("--namespace", required=True)
    clip_apply.add_argument("--clip", type=Path, required=True)
    clip_apply.add_argument("--output", type=Path, required=True)
    presets = commands.add_parser("presets", help="检查角色姿态与动画预设目录")
    presets.add_argument("scene", type=Path)
    presets.add_argument("--namespace", required=True)
    presets.add_argument("--directory", type=Path, required=True)
    rebuild = commands.add_parser("rebuild", help="保留原数据并原位重建同布局角色")
    rebuild.add_argument("scene", type=Path)
    rebuild.add_argument("--namespace", required=True)
    rebuild.add_argument("--replacement", required=True)
    rebuild.add_argument("--extension", action="append", default=[])
    rebuild.add_argument("--output", type=Path, required=True)
    return result


def _read_text(path: Path, limit: int = 8_000_000) -> str:
    if path.stat().st_size > limit:
        raise ValueError("输入文档过大：" + str(path))
    return path.read_text(encoding="utf-8")


def _landmarks(path: Path) -> tuple[FaceLandmark, ...]:
    document = safe_json(_read_text(path))
    if not isinstance(document, dict) or set(document) != {"landmarks"}:
        raise ValueError("顶点标记文档必须只含 landmarks 字段")
    rows = document["landmarks"]
    if not isinstance(rows, list):
        raise ValueError("landmarks 必须是数组")
    result = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"vertex", "displacement", "radius"}:
            raise ValueError("单个标记须包含 vertex、displacement 和 radius")
        if not isinstance(row["displacement"], list):
            raise ValueError("标记位移必须是三个数值的数组")
        result.append(FaceLandmark(row["vertex"], tuple(row["displacement"]),
                                   row["radius"]))
    return tuple(result)


def _face_build_spec(path: Path) -> tuple[str, tuple[FaceTarget, ...]]:
    document = safe_json(_read_text(path))
    if (not isinstance(document, dict) or set(document) != {"neutral", "targets"}
            or not isinstance(document["neutral"], str)
            or not isinstance(document["targets"], list)):
        raise ValueError("面部构建文档须包含 neutral 和 targets")
    targets = []
    for row in document["targets"]:
        if not isinstance(row, dict) or set(row) != {"name", "kind", "mesh"}:
            raise ValueError("面部目标须包含 name、kind 和 mesh")
        targets.append(FaceTarget(row["name"], FaceShapeKind(row["kind"]),
                                  row["mesh"]))
    return document["neutral"], tuple(targets)


def _emit(event: str, **payload) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False), file=sys.stderr,
          flush=True)


def _run(args, gateway) -> dict:
    from adv_py.adapters import MayaFaceHost

    gateway.open(args.scene)
    _emit("scene_opened", scene=str(args.scene.resolve()))
    if args.command == "characters":
        characters = []
        for namespace in gateway.namespaces():
            host = MayaFaceHost(namespace=namespace)
            service = ResolveBodyCharacter(host)
            for name in service.discover():
                try:
                    registration = service.execute(name)
                    heads = [joint.path for joint in registration.body
                        if joint.path.rsplit("|", 1)[-1].rsplit(":", 1)[-1] == "Head_M"]
                    characters.append({"namespace": namespace, "name": name,
                        "writable": True, "joint_count": len(registration.body),
                        "channel_count": len(registration.channels),
                        "face_control": heads[0] + "|AdvPy_FaceControls"
                            if len(heads) == 1 else None,
                        "compatibility_digest": registration.compatibility_digest})
                except ValueError as error:
                    characters.append({"namespace": namespace, "name": name,
                        "writable": False, "reason": str(error)})
        return {"status": "ok", "characters": characters}
    selected_namespace = ("" if args.command == "rebuild" else None)
    host = MayaFaceHost(namespace=selected_namespace if args.namespace == ":"
                        else args.namespace)
    if args.command == "presets":
        entries = InspectBodyCharacterPresets(host).list(args.directory)
        return {"status": "ok", "presets": [asdict(entry) for entry in entries]}
    if args.command in ("pose-capture", "animation-capture"):
        output = args.output.resolve()
        if output.suffix.lower() != ".json" or output.exists():
            raise ValueError("文档输出须为尚不存在的 .json 文件")
        output.parent.mkdir(parents=True, exist_ok=True)
        if args.command == "pose-capture":
            if args.frame is not None:
                gateway.seek(args.frame)
            pose = CaptureBodyCharacterPose(host).execute()
            saved = save_character_pose(pose, output)
            _emit("pose_captured", channels=len(pose.channels))
            return {"status": "ok", "output": str(saved),
                    "channels": len(pose.channels)}
        animation = CaptureBodyCharacterAnimation(host).execute(
            args.start, args.end, args.step)
        saved = save_character_animation(animation, output)
        _emit("animation_captured", frames=len(animation.samples))
        return {"status": "ok", "output": str(saved),
                "frames": len(animation.samples)}
    gateway.preflight_output(args.output)
    if args.command == "face-build":
        neutral, targets = _face_build_spec(args.spec)
        built = BuildFaceBlendShapes(host).apply(neutral, targets,
            control_name=args.control_name, deformer_name=args.deformer_name)
        _emit("face_built", channels=len(built.binding.channels),
              max_geometry_delta=built.binding.max_geometry_delta)
        output = gateway.save_new(args.output)
        _emit("scene_saved", scene=str(output))
        return {"status": "ok", "output": str(output),
                "control": built.binding.control_path,
                "channels": len(built.binding.channels),
                "max_geometry_delta": built.binding.max_geometry_delta}
    if args.command == "rebuild":
        result = RebuildBodyCharacter(host).apply(args.replacement,
            extensions=tuple(args.extension))
        _emit("character_rebuilt", joints=len(result.registration.body),
              preserved_extensions=len(result.original.extensions))
        output = gateway.save_new(args.output)
        _emit("scene_saved", scene=str(output))
        return {"status": "ok", "output": str(output),
                "joints": len(result.registration.body),
                "preserved_extensions": len(result.original.extensions)}
    if args.command == "pose-apply":
        pose = load_character_pose(args.pose)
        ApplyBodyCharacterPose(host).apply(pose)
        _emit("pose_applied", channels=len(pose.channels))
        output = gateway.save_new(args.output)
        _emit("scene_saved", scene=str(output))
        return {"status": "ok", "output": str(output),
                "channels": len(pose.channels)}
    if args.command == "animation-apply":
        animation = load_character_animation(args.clip)
        ApplyBodyCharacterAnimation(host).apply(animation)
        _emit("animation_applied", channels=len(animation.samples[0][1].channels),
              frames=len(animation.samples))
        output = gateway.save_new(args.output)
        _emit("scene_saved", scene=str(output))
        return {"status": "ok", "output": str(output),
                "channels": len(animation.samples[0][1].channels),
                "frames": len(animation.samples)}
    if args.command == "face-target":
        target = FaceTarget(args.name, FaceShapeKind(args.kind), args.target)
        plan = GenerateFaceTarget(host).apply(args.neutral, target,
                                              _landmarks(args.landmarks))
        _emit("asset_generated", target=target.mesh, channel=target.name)
        output = gateway.save_new(args.output)
        _emit("scene_saved", scene=str(output))
        return {"status": "ok", "output": str(output),
                "target": target.mesh, "vertex_count": plan.neutral.vertex_count}
    performance = face_performance_from_json(_read_text(args.clip))
    ApplyFacePerformance(host).apply(args.control, performance)
    _emit("animation_applied", channels=len(performance.channels),
          frames=len(performance.samples))
    output = gateway.save_new(args.output)
    _emit("scene_saved", scene=str(output))
    return {"status": "ok", "output": str(output),
            "channels": len(performance.channels), "frames": len(performance.samples)}


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    from adv_py.adapters.maya_scene_gateway import MayaSceneGateway

    gateway = MayaSceneGateway()
    try:
        gateway.start()
        result = _run(args, gateway)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0
    except (ImportError, OSError, ValueError, RuntimeError) as error:
        _emit("failed", type=type(error).__name__, message=str(error))
        return 2
    finally:
        gateway.close()
