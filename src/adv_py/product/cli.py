"""Maya standalone operations over application use cases."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from adv_py.application import (ApplyBodyCharacterAnimation, BakeBodyExportSkeleton,
    ApplyBodyCharacterPose, ApplyFacePerformance, BuildFaceBlendShapes, CaptureBodyCharacterAnimation,
    CaptureBodyCharacterPose, BuildBodyExportSkeleton, BuildBodyRootMotion,
    CaptureAnimatedBodyCharacterPose, KeyBodyCharacterPose,
    EnableBodyCharacterLimbAnimation, EnableBodyCharacterStretchMatching,
    EnableBodyCharacterSplineAnimation, EnableBodyCharacterSpaceAnimation,
    BakeBodyCharacterLimbMode, BakeBodyCharacterSpineMode,
    SwitchBodyCharacterSpace,
    BuildRegisteredBodyCharacter,
    CreateAndImportFitSkeleton, ExportFitSkeleton,
    ExportBodyFbx, ExportFaceTargetAsset, GenerateFaceTarget,
    BindSkin,
    FaceAssetLibrary, ImportFaceTargetAsset, ExportSkinWeights, ImportSkinWeights,
    TransferSkinWeightsBySurface,
    CaptureSkinWeightSurfaceSource, save_skin_weight_surface_source,
    load_skin_weight_surface_source,
    ImportMocapFbx, RetargetMocapFullFkToCharacter,
    RetargetCharacterSpineFk,
    MigrateRegisteredSpineCharacter,
    MigrateRegisteredSpineOnOriginalSkin,
    ReplaceRegisteredSpineCharacter,
    HandoffRegisteredSpineSkinCluster,
    PromoteOriginalSpineCharacter,
    RetargetMocapFullLimbIkToCharacter, RetargetMocapFullIkToCharacter,
    load_mocap_mapping_preset,
    ResolveBodyCharacter, TransferFaceTargetAsset,
    ExportFaceNeutralGeometry, load_face_neutral_geometry,
    save_face_neutral_geometry,
    InspectBodyCharacterPresets, load_character_animation, load_character_pose, save_character_animation,
    save_character_pose, RebuildBodyCharacter, load_face_target_asset,
    save_face_target_asset)
from adv_py.core import (BodyFbxCurvePolicy, BodyFbxEncoding,
                         BodyFbxExportProfile, BodyFbxFileVersion,
                         FaceLandmark, FaceShapeKind, FaceTarget,
                         face_performance_from_json,
                         registered_spine_weight_redistribution)
from adv_py.core.variable_body_fit import variable_axial_description
from .input_documents import (load_face_build_spec, load_face_landmarks,
                              load_skin_path_mapping, load_skin_redistribution,
                              load_surface_alignment)


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
    asset_export = commands.add_parser("face-asset-export",
        help="将雕刻目标导出为带摘要的稀疏位移文档")
    asset_export.add_argument("scene", type=Path)
    asset_export.add_argument("--namespace", required=True)
    asset_export.add_argument("--neutral", required=True)
    asset_export.add_argument("--name", required=True)
    asset_export.add_argument("--kind", choices=tuple(kind.value for kind in FaceShapeKind), required=True)
    asset_export.add_argument("--target", required=True)
    asset_export.add_argument("--frame", type=int)
    asset_export.add_argument("--output", type=Path, required=True)
    asset_import = commands.add_parser("face-asset-import",
        help="在匹配的中性网格上恢复雕刻目标")
    asset_import.add_argument("scene", type=Path)
    asset_import.add_argument("--namespace", required=True)
    asset_import.add_argument("--neutral", required=True)
    asset_import.add_argument("--asset", type=Path, required=True)
    asset_import.add_argument("--target", required=True)
    asset_import.add_argument("--output", type=Path, required=True)
    geometry_export = commands.add_parser("face-geometry-export",
        help="导出跨场景转移所需的源中性网格几何")
    geometry_export.add_argument("scene", type=Path)
    geometry_export.add_argument("--namespace", required=True)
    geometry_export.add_argument("--neutral", required=True)
    geometry_export.add_argument("--output", type=Path, required=True)
    asset_transfer = commands.add_parser("face-asset-transfer",
        help="按源网格表面对应关系转移雕刻位移到不同拓扑")
    asset_transfer.add_argument("scene", type=Path)
    asset_transfer.add_argument("--namespace", required=True)
    transfer_source = asset_transfer.add_mutually_exclusive_group(required=True)
    transfer_source.add_argument("--source-neutral")
    transfer_source.add_argument("--source-geometry", type=Path)
    asset_transfer.add_argument("--target-neutral", required=True)
    asset_transfer.add_argument("--asset", type=Path, required=True)
    asset_transfer.add_argument("--max-distance", type=float, required=True)
    asset_transfer.add_argument("--alignment", type=Path,
        help="三个源/目标顶点对应及误差上限的 JSON 文件")
    asset_transfer.add_argument("--output", type=Path, required=True)
    library_add = commands.add_parser("face-library-add",
        help="将面部目标资产登记到不可覆盖的版本目录")
    library_add.add_argument("--library", type=Path, required=True)
    library_add.add_argument("--asset", type=Path, required=True)
    library_add.add_argument("--release", required=True)
    library_list = commands.add_parser("face-library-list",
        help="列出面部资产版本和损坏状态")
    library_list.add_argument("--library", type=Path, required=True)
    library_export = commands.add_parser("face-library-export",
        help="从版本目录导出指定面部资产")
    library_export.add_argument("--library", type=Path, required=True)
    library_export.add_argument("--name", required=True)
    library_export.add_argument("--release", required=True)
    library_export.add_argument("--output", type=Path, required=True)
    library_merge = commands.add_parser("face-library-merge",
        help="以共同基线合并两个雕刻版本并登记新版本")
    library_merge.add_argument("--library", type=Path, required=True)
    library_merge.add_argument("--name", required=True)
    library_merge.add_argument("--base", required=True)
    library_merge.add_argument("--left", required=True)
    library_merge.add_argument("--right", required=True)
    library_merge.add_argument("--release", required=True)
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
    key_current = commands.add_parser("animation-key",
        help="在指定帧写入已登记角色的完整控制姿态")
    key_current.add_argument("scene", type=Path)
    key_current.add_argument("--namespace", required=True)
    key_current.add_argument("--frame", type=int, required=True)
    key_current.add_argument("--output", type=Path, required=True)
    enable = commands.add_parser("animation-enable",
        help="显式启用角色的动画控制通道")
    enable.add_argument("scene", type=Path)
    enable.add_argument("--namespace", required=True)
    enable.add_argument("--kind", choices=("limb", "stretch", "spline", "spaces"),
                        required=True)
    enable.add_argument("--output", type=Path, required=True)
    limb_bake = commands.add_parser("animation-bake-limb",
        help="在帧区间内转换手臂或腿部 FK/IK 模式")
    limb_bake.add_argument("scene", type=Path)
    limb_bake.add_argument("--namespace", required=True)
    limb_bake.add_argument("--start", type=int, required=True)
    limb_bake.add_argument("--end", type=int, required=True)
    limb_bake.add_argument("--step", type=int, default=1)
    limb_bake.add_argument("--limb", choices=("arm", "leg"), required=True)
    limb_bake.add_argument("--side", choices=("R", "L"), required=True)
    limb_bake.add_argument("--mode", choices=("fk", "ik"), required=True)
    limb_bake.add_argument("--output", type=Path, required=True)
    spine_bake = commands.add_parser("animation-bake-spine",
        help="在帧区间内转换脊柱 FK/IK 模式")
    spine_bake.add_argument("scene", type=Path)
    spine_bake.add_argument("--namespace", required=True)
    spine_bake.add_argument("--start", type=int, required=True)
    spine_bake.add_argument("--end", type=int, required=True)
    spine_bake.add_argument("--step", type=int, default=1)
    spine_bake.add_argument("--mode", choices=("fk", "ik"), required=True)
    spine_bake.add_argument("--output", type=Path, required=True)
    space_switch = commands.add_parser("animation-switch-space",
        help="在指定帧切换头、手或脚控制空间")
    space_switch.add_argument("scene", type=Path)
    space_switch.add_argument("--namespace", required=True)
    space_switch.add_argument("--key", choices=("head", "hand_R", "hand_L",
                                               "foot_R", "foot_L"), required=True)
    space_switch.add_argument("--mode", choices=("body", "global"), required=True)
    space_switch.add_argument("--frame", type=int, required=True)
    space_switch.add_argument("--output", type=Path, required=True)
    body_build = commands.add_parser("body-build",
        help="从现有 Fit 场景构建 Body 骨架、完整控制 Rig 并登记角色")
    body_build.add_argument("scene", type=Path)
    body_build.add_argument("--namespace", required=True)
    body_build.add_argument("--fit", default="FitSkeleton")
    body_build.add_argument("--spine-segments", type=int,
        help="可变脊柱段数；标准双段角色可省略")
    body_build.add_argument("--head-aim", action="store_true")
    body_build.add_argument("--output", type=Path, required=True)
    fit_export = commands.add_parser("fit-export",
        help="导出现有 Fit 容器的完整文档")
    fit_export.add_argument("scene", type=Path)
    fit_export.add_argument("--namespace", required=True)
    fit_export.add_argument("--fit", default="FitSkeleton")
    fit_export.add_argument("--output", type=Path, required=True)
    fit_import = commands.add_parser("fit-import",
        help="在场景中新建 Fit 容器并导入完整文档")
    fit_import.add_argument("scene", type=Path)
    fit_import.add_argument("--namespace", required=True)
    fit_import.add_argument("--document", type=Path, required=True)
    fit_import.add_argument("--fit", default="FitSkeleton")
    fit_import.add_argument("--output", type=Path, required=True)
    presets = commands.add_parser("presets", help="检查角色姿态与动画预设目录")
    presets.add_argument("scene", type=Path)
    presets.add_argument("--namespace", required=True)
    presets.add_argument("--directory", type=Path, required=True)
    skin_export = commands.add_parser("skin-export", help="导出网格的完整蒙皮权重文档")
    skin_export.add_argument("scene", type=Path)
    skin_export.add_argument("--namespace", required=True)
    skin_export.add_argument("--skin", required=True)
    skin_export.add_argument("--mesh", required=True)
    skin_export.add_argument("--output", type=Path, required=True)
    skin_import = commands.add_parser("skin-import", help="将完整蒙皮权重文档写入场景")
    skin_import.add_argument("scene", type=Path)
    skin_import.add_argument("--namespace", required=True)
    skin_import.add_argument("--weights", type=Path, required=True)
    skin_import.add_argument("--mapping", type=Path,
        help="显式目标网格、Skin 和影响关节路径映射文档")
    skin_import.add_argument("--allow-unweighted-missing", action="store_true")
    skin_import.add_argument("--output", type=Path, required=True)
    skin_source = commands.add_parser("skin-surface-source-export",
        help="在同一场景快照中封装源网格几何和完整权重")
    skin_source.add_argument("scene", type=Path)
    skin_source.add_argument("--namespace", required=True)
    skin_source.add_argument("--skin", required=True)
    skin_source.add_argument("--mesh", required=True)
    skin_source.add_argument("--output", type=Path, required=True)
    skin_surface = commands.add_parser("skin-surface-transfer",
        help="按源网格表面投影，将完整权重转移到不同拓扑的目标网格")
    skin_surface.add_argument("scene", type=Path)
    skin_surface.add_argument("--namespace", required=True)
    surface_input = skin_surface.add_mutually_exclusive_group(required=True)
    surface_input.add_argument("--source-skin")
    surface_input.add_argument("--source-asset", type=Path)
    skin_surface.add_argument("--source-mesh")
    skin_surface.add_argument("--target-skin", required=True)
    skin_surface.add_argument("--target-mesh", required=True)
    surface_mapping = skin_surface.add_mutually_exclusive_group()
    surface_mapping.add_argument("--mapping", type=Path)
    surface_mapping.add_argument("--redistribution", type=Path,
        help="源影响关节到一个或多个目标关节的完整比例文档")
    surface_mapping.add_argument("--registered-source-namespace",
        help="从同场景已登记来源角色与目标角色的绑定脊柱自动计算影响重分配")
    skin_surface.add_argument("--alignment", type=Path,
        help="三个源/目标顶点对应及误差上限的 JSON 文件")
    skin_surface.add_argument("--max-distance", type=float, required=True)
    skin_surface.add_argument("--max-discarded-weight", type=float, default=0.)
    skin_surface.add_argument("--allow-target-extra-influences", action="store_true",
        help="允许目标 skinCluster 多出关节；写入时将这些关节的目标顶点权重清零")
    skin_surface.add_argument("--allow-unweighted-missing", action="store_true",
        help="路径映射可省略在源资产所有顶点均为零权重的关节")
    skin_surface.add_argument("--output", type=Path, required=True)
    skin_bind = commands.add_parser("skin-bind",
        help="将现有网格绑定到显式列出的关节")
    skin_bind.add_argument("scene", type=Path)
    skin_bind.add_argument("--namespace", required=True)
    skin_bind.add_argument("--mesh", required=True)
    skin_bind.add_argument("--influence", action="append", required=True)
    skin_bind.add_argument("--skin", default="AdvPy_BodySkin")
    skin_bind.add_argument("--max-influences", type=int, default=4)
    skin_bind.add_argument("--no-maintain-max-influences", action="store_true")
    skin_bind.add_argument("--output", type=Path, required=True)
    fbx = commands.add_parser("fbx-publish", help="从身体动画场景发布独立烘焙 FBX")
    fbx.add_argument("scene", type=Path)
    fbx.add_argument("--namespace", required=True)
    fbx.add_argument("--start", type=int, required=True)
    fbx.add_argument("--end", type=int, required=True)
    fbx.add_argument("--step", type=int, default=1)
    fbx.add_argument("--curve-policy", choices=tuple(item.value for item in
                     BodyFbxCurvePolicy), default=BodyFbxCurvePolicy.SAMPLED_LINEAR.value)
    fbx.add_argument("--value-tolerance", type=float, default=0.)
    fbx.add_argument("--matrix-tolerance", type=float, default=0.)
    fbx.add_argument("--euler-filter", action="store_true",
                     help="仅在临时 FBX 副本上整理旋转曲线跨圈跳变")
    fbx.add_argument("--output", type=Path, required=True)
    mocap = commands.add_parser("mocap-retarget",
        help="从外部 FBX 和版本化映射预设写入角色控制动画")
    mocap.add_argument("scene", type=Path)
    mocap.add_argument("--namespace", required=True)
    mocap.add_argument("--source", type=Path, required=True)
    mocap.add_argument("--mapping", type=Path, required=True)
    mocap.add_argument("--source-namespace", required=True)
    mocap.add_argument("--start", type=int, required=True)
    mocap.add_argument("--end", type=int, required=True)
    mocap.add_argument("--step", type=int, default=1)
    mocap.add_argument("--mode", choices=("fk", "limb-ik", "full-ik"), default="fk")
    mocap.add_argument("--output", type=Path, required=True)
    spine_transfer = commands.add_parser("character-spine-retarget",
        help="将同场景角色动画重采样到不同段数脊柱的 FK 控制")
    spine_transfer.add_argument("scene", type=Path)
    spine_transfer.add_argument("--namespace", required=True)
    spine_transfer.add_argument("--source-namespace", required=True)
    spine_transfer.add_argument("--start", type=int, required=True)
    spine_transfer.add_argument("--end", type=int, required=True)
    spine_transfer.add_argument("--step", type=int, default=1)
    spine_transfer.add_argument("--reference", type=float)
    spine_transfer.add_argument("--output", type=Path, required=True)
    spine_migrate = commands.add_parser("character-spine-migrate",
        help="单次事务迁移已登记角色的变段数脊柱 FK 动画和 Skin 权重")
    spine_migrate.add_argument("scene", type=Path)
    spine_migrate.add_argument("--namespace", required=True)
    spine_migrate.add_argument("--source-namespace", required=True)
    spine_migrate.add_argument("--source-skin", required=True)
    spine_migrate.add_argument("--source-mesh", required=True)
    spine_migrate.add_argument("--target-skin", required=True)
    spine_migrate.add_argument("--target-mesh", required=True)
    spine_migrate.add_argument("--start", type=int, required=True)
    spine_migrate.add_argument("--end", type=int, required=True)
    spine_migrate.add_argument("--step", type=int, default=1)
    spine_migrate.add_argument("--reference", type=float)
    spine_migrate.add_argument("--max-distance", type=float, required=True)
    spine_migrate.add_argument("--max-discarded-weight", type=float, default=0.)
    spine_migrate.add_argument("--allow-target-extra-influences", action="store_true")
    spine_migrate.add_argument("--output", type=Path, required=True)
    skin_handoff = commands.add_parser("spine-skin-handoff",
        help="保留原网格和 skinCluster，将其影响关节交给另一已登记脊柱角色")
    skin_handoff.add_argument("scene", type=Path)
    skin_handoff.add_argument("--namespace", required=True)
    skin_handoff.add_argument("--replacement-namespace", required=True)
    skin_handoff.add_argument("--skin", required=True)
    skin_handoff.add_argument("--mesh", required=True)
    skin_handoff.add_argument("--output", type=Path, required=True)
    original_migrate = commands.add_parser("character-spine-original-skin-migrate",
        help="一次事务迁移变段数脊柱 FK 动画并交接原网格和 skinCluster")
    original_migrate.add_argument("scene", type=Path)
    original_migrate.add_argument("--namespace", required=True)
    original_migrate.add_argument("--replacement-namespace", required=True)
    original_migrate.add_argument("--skin", required=True)
    original_migrate.add_argument("--mesh", required=True)
    original_migrate.add_argument("--start", type=int, required=True)
    original_migrate.add_argument("--end", type=int, required=True)
    original_migrate.add_argument("--step", type=int, default=1)
    original_migrate.add_argument("--reference", type=float)
    original_migrate.add_argument("--output", type=Path, required=True)
    original_promote = commands.add_parser("character-spine-promote",
        help="清理已交接的旧 Rig 并让目标 Rig 接管原角色命名空间")
    original_promote.add_argument("scene", type=Path)
    original_promote.add_argument("--namespace", required=True)
    original_promote.add_argument("--replacement-namespace", required=True)
    original_promote.add_argument("--skin", required=True)
    original_promote.add_argument("--mesh", required=True)
    original_promote.add_argument("--output", type=Path, required=True)
    original_replace = commands.add_parser("character-spine-replace",
        help="一次事务完成变段数脊柱动画、原 Skin 和角色标识替换")
    original_replace.add_argument("scene", type=Path)
    original_replace.add_argument("--namespace", required=True)
    original_replace.add_argument("--replacement-namespace", required=True)
    original_replace.add_argument("--skin", action="append", required=True)
    original_replace.add_argument("--mesh", action="append", required=True)
    original_replace.add_argument("--start", type=int, required=True)
    original_replace.add_argument("--end", type=int, required=True)
    original_replace.add_argument("--step", type=int, default=1)
    original_replace.add_argument("--reference", type=float)
    original_replace.add_argument("--extension", action="append", default=[])
    original_replace.add_argument("--output", type=Path, required=True)
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
    return load_face_landmarks(path)


def _face_build_spec(path: Path) -> tuple[str, tuple[FaceTarget, ...]]:
    return load_face_build_spec(path)


def _emit(event: str, **payload) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False), file=sys.stderr,
          flush=True)


def _run_library(args) -> dict:
    library = FaceAssetLibrary(args.library)
    if args.command == "face-library-list":
        return {"status": "ok", "assets": [asdict(entry)
            for entry in library.list()]}
    if args.command == "face-library-add":
        entry = library.add(load_face_target_asset(args.asset), args.release)
        _emit("asset_version_registered", name=entry.name,
              release=entry.release)
        return {"status": "ok", "asset": asdict(entry)}
    if args.command == "face-library-merge":
        entry = library.merge(args.name, args.base, args.left,
                              args.right, args.release)
        _emit("asset_versions_merged", name=entry.name, release=entry.release)
        return {"status": "ok", "asset": asdict(entry)}
    asset = library.resolve(args.name, args.release)
    saved = save_face_target_asset(asset, args.output)
    _emit("asset_version_exported", name=asset.name,
          release=args.release)
    return {"status": "ok", "output": str(saved),
            "name": asset.name, "release": args.release}


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
    if args.command == "fit-export":
        exported = ExportFitSkeleton(host).apply(args.output, args.fit)
        _emit("fit_exported", joints=len(exported.plan.document.joints))
        return {"status": "ok", "output": str(exported.plan.destination),
                "joints": len(exported.plan.document.joints)}
    if args.command == "fit-import":
        output = gateway.preflight_output(args.output)
        imported = CreateAndImportFitSkeleton(host).apply(args.document, args.fit)
        _emit("fit_imported", joints=len(imported.joint_paths))
        saved = gateway.save_new(output)
        _emit("scene_saved", scene=str(saved))
        return {"status": "ok", "output": str(saved),
                "joints": len(imported.joint_paths)}
    if args.command == "body-build":
        output = gateway.preflight_output(args.output)
        description = (variable_axial_description(args.spine_segments)
            if args.spine_segments is not None else None)
        built = BuildRegisteredBodyCharacter(host).apply(args.fit,
            axial_description=description, include_head_aim=args.head_aim)
        registration = built.registration
        _emit("character_registered", channels=len(registration.channels))
        saved = gateway.save_new(output)
        _emit("scene_saved", scene=str(saved))
        return {"status": "ok", "output": str(saved),
                "joints": len(registration.body),
                "channels": len(registration.channels),
                "compatibility_digest": registration.compatibility_digest}
    if args.command == "presets":
        entries = InspectBodyCharacterPresets(host).list(args.directory)
        return {"status": "ok", "presets": [asdict(entry) for entry in entries]}
    if args.command == "skin-export":
        exported = ExportSkinWeights(host).apply(args.skin, args.mesh, args.output)
        _emit("skin_exported", vertices=exported.plan.document.vertex_count,
              bytes=exported.bytes_written)
        return {"status": "ok", "output": str(exported.plan.destination),
                "vertices": exported.plan.document.vertex_count,
                "bytes": exported.bytes_written}
    if args.command == "skin-surface-source-export":
        source = CaptureSkinWeightSurfaceSource(host).execute(args.skin, args.mesh)
        saved = save_skin_weight_surface_source(source, args.output)
        _emit("skin_surface_source_exported", vertices=source.weights.vertex_count)
        return {"status": "ok", "output": str(saved),
                "vertices": source.weights.vertex_count,
                "triangles": len(source.geometry.triangles)}
    if args.command == "fbx-publish":
        destination = args.output.resolve()
        if destination.suffix.lower() != ".fbx" or not destination.parent.is_dir():
            raise ValueError("FBX 输出必须是现有目录中的 .fbx 路径")
        if destination.exists():
            raise FileExistsError("FBX 输出已存在：" + str(destination))
        if args.start > args.end or args.step < 1:
            raise ValueError("FBX 发布帧范围或采样步长无效")
        namespace = "" if args.namespace == ":" else args.namespace.strip(":") + ":"
        body_root = namespace + "Root_M"
        source_container = "|" + namespace + "FitSkeleton"
        BuildBodyRootMotion(host).apply(body_root_name=body_root,
                                        source_container=source_container)
        _emit("root_motion_built", namespace=args.namespace)
        BuildBodyExportSkeleton(host).apply(body_root_name=body_root,
                                            source_container=source_container)
        _emit("export_skeleton_built", namespace=args.namespace)
        baked = BakeBodyExportSkeleton(host).apply(start_frame=args.start,
            end_frame=args.end, sample_by=args.step, body_root_name=body_root,
            source_container=source_container)
        _emit("export_skeleton_baked", frames=len(baked.plan.bake.frames))
        profile = BodyFbxExportProfile(BodyFbxFileVersion.FBX_2020,
            host.scene_up_axis(), host.scene_linear_unit(), BodyFbxEncoding.BINARY,
            BodyFbxCurvePolicy(args.curve_policy), args.value_tolerance,
            args.matrix_tolerance, args.euler_filter)
        exported = ExportBodyFbx(host).apply(destination, start_frame=args.start,
            end_frame=args.end, sample_by=args.step, body_root_name=body_root,
            source_container=source_container, profile=profile)
        _emit("fbx_published", joints=len(baked.plan.body.joints),
              bytes=exported.artifact.byte_count)
        return {"status": "ok", "output": str(destination),
                "joints": len(baked.plan.body.joints),
                "frames": len(baked.plan.bake.frames),
                "bytes": exported.artifact.byte_count,
                "sha256": exported.artifact.content_sha256,
                "curve_policy": exported.applied_profile.curve_policy,
                "removed_linear_keys": exported.applied_profile.removed_linear_keys,
                "max_matrix_error": exported.applied_profile.max_matrix_error,
                "euler_filter": exported.applied_profile.euler_filter,
                "euler_filtered_curves": exported.applied_profile.euler_filtered_curves}
    if args.command == "mocap-retarget":
        from adv_py.adapters import MayaMocapClipHost, MayaMocapControlHost

        gateway.preflight_output(args.output)
        preset = load_mocap_mapping_preset(args.mapping)
        target_namespace = "" if args.namespace == ":" else args.namespace
        target = MayaMocapControlHost(namespace=target_namespace)
        target.read_character_registration()
        imported = ImportMocapFbx(MayaMocapClipHost()).apply(args.source,
            namespace=args.source_namespace)
        _emit("mocap_imported", joints=len(imported.clip.joints),
              namespace=args.source_namespace)
        services = {"fk": RetargetMocapFullFkToCharacter,
                    "limb-ik": RetargetMocapFullLimbIkToCharacter,
                    "full-ik": RetargetMocapFullIkToCharacter}
        samples = services[args.mode](target).apply_with_preset(imported.snapshot.root,
            preset, start_frame=args.start, end_frame=args.end, sample_by=args.step)
        _emit("mocap_retargeted", mode=args.mode, frames=len(samples[0]))
        output = gateway.save_new(args.output)
        _emit("scene_saved", scene=str(output))
        return {"status": "ok", "output": str(output), "mode": args.mode,
                "source_joints": len(imported.clip.joints),
                "frames": len(samples[0]), "source_root": imported.snapshot.root}
    if args.command == "character-spine-retarget":
        from adv_py.adapters import MayaMocapControlHost

        gateway.preflight_output(args.output)
        target_namespace = "" if args.namespace == ":" else args.namespace
        source_namespace = "" if args.source_namespace == ":" else args.source_namespace
        target = MayaMocapControlHost(namespace=target_namespace)
        samples = RetargetCharacterSpineFk(target).apply(source_namespace,
            start_frame=args.start, end_frame=args.end, sample_by=args.step,
            reference_frame=args.reference)
        _emit("character_spine_retargeted", frames=len(samples[0]),
              source_namespace=source_namespace, target_namespace=target_namespace)
        output = gateway.save_new(args.output)
        _emit("scene_saved", scene=str(output))
        return {"status": "ok", "output": str(output),
                "frames": len(samples[0]), "mode": "fk"}
    if args.command == "character-spine-migrate":
        from adv_py.adapters import MayaCharacterSpineMigrationHost

        gateway.preflight_output(args.output)
        target_namespace = "" if args.namespace == ":" else args.namespace
        source_namespace = "" if args.source_namespace == ":" else args.source_namespace
        target = MayaCharacterSpineMigrationHost(namespace=target_namespace)
        result = MigrateRegisteredSpineCharacter(target).apply(source_namespace,
            args.source_skin, args.source_mesh, args.target_skin, args.target_mesh,
            start_frame=args.start, end_frame=args.end, sample_by=args.step,
            reference_frame=args.reference, max_distance=args.max_distance,
            max_discarded_weight=args.max_discarded_weight,
            allow_target_extra_influences=args.allow_target_extra_influences)
        _emit("character_spine_migrated", frames=result.frames,
              groups=result.fk_groups, changed_vertices=result.changed_vertices)
        output = gateway.save_new(args.output)
        _emit("scene_saved", scene=str(output))
        return {"status": "ok", "output": str(output),
                "frames": result.frames, "fk_groups": result.fk_groups,
                "changed_vertices": result.changed_vertices}
    if args.command == "spine-skin-handoff":
        from adv_py.adapters import MayaSpineSkinHandoffHost

        gateway.preflight_output(args.output)
        source_namespace = "" if args.namespace == ":" else args.namespace
        target_namespace = ("" if args.replacement_namespace == ":"
                            else args.replacement_namespace)
        result = HandoffRegisteredSpineSkinCluster(
            MayaSpineSkinHandoffHost()).apply(source_namespace,
            target_namespace, args.skin, args.mesh)
        _emit("spine_skin_handed_off", vertices=result.vertex_count,
              target_influences=result.target_influence_count)
        output = gateway.save_new(args.output)
        _emit("scene_saved", scene=str(output))
        return {"status": "ok", "output": str(output),
                "vertices": result.vertex_count,
                "target_influences": result.target_influence_count}
    if args.command == "character-spine-original-skin-migrate":
        from adv_py.adapters import MayaOriginalSkinSpineMigrationHost

        gateway.preflight_output(args.output)
        source_namespace = "" if args.namespace == ":" else args.namespace
        target_namespace = ("" if args.replacement_namespace == ":"
                            else args.replacement_namespace)
        result = MigrateRegisteredSpineOnOriginalSkin(
            MayaOriginalSkinSpineMigrationHost(namespace=target_namespace)).apply(
                source_namespace, target_namespace, args.skin, args.mesh,
                start_frame=args.start, end_frame=args.end,
                sample_by=args.step, reference_frame=args.reference)
        _emit("character_spine_original_skin_migrated", frames=result.frames,
              groups=result.fk_groups, vertices=result.vertices,
              target_influences=result.target_influences)
        output = gateway.save_new(args.output)
        _emit("scene_saved", scene=str(output))
        return {"status": "ok", "output": str(output),
                "frames": result.frames, "fk_groups": result.fk_groups,
                "vertices": result.vertices,
                "target_influences": result.target_influences}
    if args.command == "character-spine-promote":
        from adv_py.adapters import MayaOriginalSpinePromotionHost

        gateway.preflight_output(args.output)
        source_namespace = "" if args.namespace == ":" else args.namespace
        target_namespace = ("" if args.replacement_namespace == ":"
                            else args.replacement_namespace)
        result = PromoteOriginalSpineCharacter(
            MayaOriginalSpinePromotionHost()).apply(source_namespace,
                target_namespace, args.skin, args.mesh)
        _emit("character_spine_promoted", removed=result.old_nodes_removed,
              retained=result.retained_nodes,
              replacement=result.replacement_nodes)
        output = gateway.save_new(args.output)
        _emit("scene_saved", scene=str(output))
        return {"status": "ok", "output": str(output),
                "removed": result.old_nodes_removed,
                "retained": result.retained_nodes,
                "replacement": result.replacement_nodes}
    if args.command == "character-spine-replace":
        from adv_py.adapters import MayaOriginalSkinSpineMigrationHost

        gateway.preflight_output(args.output)
        source_namespace = "" if args.namespace == ":" else args.namespace
        target_namespace = ("" if args.replacement_namespace == ":"
                            else args.replacement_namespace)
        if len(args.skin) != len(args.mesh):
            raise ValueError('每个 --skin 都需要对应位置的 --mesh')
        result = ReplaceRegisteredSpineCharacter(
            MayaOriginalSkinSpineMigrationHost(namespace=target_namespace)).apply_many(
                source_namespace, target_namespace, tuple(zip(args.skin, args.mesh)),
                start_frame=args.start, end_frame=args.end,
                sample_by=args.step, reference_frame=args.reference,
                extensions=tuple(args.extension))
        _emit("character_spine_replaced", frames=result.frames,
              groups=result.fk_groups, vertices=result.vertices,
              removed=result.old_nodes_removed, skins=result.skin_count)
        output = gateway.save_new(args.output)
        _emit("scene_saved", scene=str(output))
        return {"status": "ok", "output": str(output),
                "frames": result.frames, "fk_groups": result.fk_groups,
                "vertices": result.vertices,
                "skins": result.skin_count,
                "removed": result.old_nodes_removed,
                "retained": result.retained_nodes,
                "replacement": result.replacement_nodes}
    if args.command == "face-asset-export":
        output = args.output.resolve()
        if output.suffix.lower() != ".json" or output.exists():
            raise ValueError("资产输出须为尚不存在的 .json 文件")
        output.parent.mkdir(parents=True, exist_ok=True)
        if args.frame is not None:
            gateway.seek(args.frame)
        target = FaceTarget(args.name, FaceShapeKind(args.kind), args.target)
        asset = ExportFaceTargetAsset(host).execute(args.neutral, target)
        saved = save_face_target_asset(asset, output)
        _emit("face_asset_exported", channel=asset.name,
              changed_vertices=len(asset.deltas))
        return {"status": "ok", "output": str(saved),
                "channel": asset.name, "changed_vertices": len(asset.deltas)}
    if args.command == "face-geometry-export":
        output = args.output.resolve()
        if output.suffix.lower() != ".json" or output.exists():
            raise ValueError("中性几何输出须为尚不存在的 .json 文件")
        output.parent.mkdir(parents=True, exist_ok=True)
        geometry = ExportFaceNeutralGeometry(host).execute(args.neutral)
        saved = save_face_neutral_geometry(geometry, output)
        _emit("face_geometry_exported", vertices=geometry.mesh.vertex_count,
              triangles=len(geometry.triangles))
        return {"status": "ok", "output": str(saved),
                "vertices": geometry.mesh.vertex_count,
                "triangles": len(geometry.triangles)}
    if args.command == "face-asset-transfer":
        output = args.output.resolve()
        if output.suffix.lower() != ".json" or output.exists():
            raise ValueError("转移资产输出须为尚不存在的 .json 文件")
        output.parent.mkdir(parents=True, exist_ok=True)
        source = load_face_target_asset(args.asset)
        alignment = load_surface_alignment(args.alignment) if args.alignment else None
        service = TransferFaceTargetAsset(host)
        plan = (service.execute_from_geometry(
            load_face_neutral_geometry(args.source_geometry),
            args.target_neutral, source, max_distance=args.max_distance,
            alignment=alignment)
            if args.source_geometry else service.execute(args.source_neutral,
                args.target_neutral, source, max_distance=args.max_distance,
                alignment=alignment))
        saved = save_face_target_asset(plan.result.asset, output)
        _emit("face_asset_transferred",
              source_triangles=plan.result.source_triangle_count,
              changed_vertices=plan.result.transferred_vertex_count,
              max_neutral_distance=plan.result.max_neutral_distance)
        return {"status": "ok", "output": str(saved),
                "changed_vertices": plan.result.transferred_vertex_count,
                "max_neutral_distance": plan.result.max_neutral_distance}
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
    if args.command == "skin-bind":
        bound = BindSkin(host).apply(args.mesh, tuple(args.influence),
            skin_name=args.skin, maximum_influences=args.max_influences,
            maintain_maximum_influences=not args.no_maintain_max_influences)
        _emit("skin_bound", vertices=bound.plan.input_state.vertex_count,
              influences=len(bound.snapshot.influence_paths))
        output = gateway.save_new(args.output)
        _emit("scene_saved", scene=str(output))
        return {"status": "ok", "output": str(output),
                "vertices": bound.plan.input_state.vertex_count,
                "influences": len(bound.snapshot.influence_paths)}
    if args.command == "skin-import":
        mapping = load_skin_path_mapping(args.mapping) if args.mapping else None
        imported = ImportSkinWeights(host).apply(args.weights,
            mapping=mapping,
            allow_unweighted_missing=args.allow_unweighted_missing)
        _emit("skin_imported", vertices=imported.plan.target_document.vertex_count,
              changed_vertices=imported.edit_result.changed_vertex_count)
        output = gateway.save_new(args.output)
        _emit("scene_saved", scene=str(output))
        return {"status": "ok", "output": str(output),
                "vertices": imported.plan.target_document.vertex_count,
                "changed_vertices": imported.edit_result.changed_vertex_count}
    if args.command == "skin-surface-transfer":
        mapping = load_skin_path_mapping(args.mapping) if args.mapping else None
        redistribution = (load_skin_redistribution(args.redistribution)
            if args.redistribution else None)
        target_skin = args.target_skin
        target_mesh = args.target_mesh
        if args.registered_source_namespace:
            if args.source_asset or not args.source_mesh:
                raise ValueError("登记脊柱影响迁移需要同场景源 skinCluster 和源网格")
            from adv_py.adapters import MayaBodyBuildHost
            source_namespace = ("" if args.registered_source_namespace == ":"
                                else args.registered_source_namespace)
            source_registration = MayaBodyBuildHost(
                namespace=source_namespace).read_character_registration()
            target_registration = host.read_character_registration()
            source_state = host.capture_all_skin_weights(args.source_skin,
                                                         args.source_mesh)
            target_state = host.capture_all_skin_weights(args.target_skin,
                                                         args.target_mesh)
            target_skin = target_state.skin_name
            target_mesh = target_state.geometry_path
            redistribution = registered_spine_weight_redistribution(
                source_registration, target_registration,
                source_state.influence_paths, target_state.influence_paths,
                source_namespace=source_namespace,
                target_namespace=host.namespace,
                target_skin_name=target_skin,
                target_mesh_path=target_mesh,
                allow_target_extra_influences=args.allow_target_extra_influences)
        alignment = load_surface_alignment(args.alignment) if args.alignment else None
        operation = TransferSkinWeightsBySurface(host)
        if args.source_asset:
            if args.source_mesh:
                raise ValueError("使用源资产时不得同时指定源网格")
            source = load_skin_weight_surface_source(args.source_asset)
            plan, edit = operation.apply_from_documents(source.weights,
                source.geometry, target_skin, target_mesh,
                max_distance=args.max_distance,
                max_discarded_weight=args.max_discarded_weight, mapping=mapping,
                redistribution=redistribution,
                alignment=alignment,
                allow_target_extra_influences=args.allow_target_extra_influences,
                allow_unweighted_missing=args.allow_unweighted_missing)
            transfer = plan.transfer
        else:
            if not args.source_mesh:
                raise ValueError("场景内转移须提供源网格路径")
            result = operation.apply(args.source_skin, args.source_mesh,
                target_skin, target_mesh, max_distance=args.max_distance,
                max_discarded_weight=args.max_discarded_weight, mapping=mapping,
                redistribution=redistribution,
                alignment=alignment,
                allow_target_extra_influences=args.allow_target_extra_influences,
                allow_unweighted_missing=args.allow_unweighted_missing)
            transfer, edit = result.plan.transfer, result.edit_result
        _emit("skin_surface_transferred",
              vertices=transfer.document.vertex_count,
              changed_vertices=edit.changed_vertex_count)
        output = gateway.save_new(args.output)
        _emit("scene_saved", scene=str(output))
        return {"status": "ok", "output": str(output),
                "vertices": transfer.document.vertex_count,
                "changed_vertices": edit.changed_vertex_count,
                "max_surface_distance": transfer.max_surface_distance,
                "max_discarded_weight": transfer.max_discarded_weight}
    if args.command == "face-asset-import":
        asset = load_face_target_asset(args.asset)
        imported = ImportFaceTargetAsset(host).apply(args.neutral, asset,
                                                    args.target)
        _emit("face_asset_imported", target=imported.target.mesh,
              changed_vertices=len(imported.asset.deltas))
        output = gateway.save_new(args.output)
        _emit("scene_saved", scene=str(output))
        return {"status": "ok", "output": str(output),
                "target": imported.target.mesh,
                "changed_vertices": len(imported.asset.deltas)}
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
    if args.command == "animation-key":
        gateway.seek(args.frame)
        pose = CaptureAnimatedBodyCharacterPose(host).execute()
        keyed = KeyBodyCharacterPose(host).apply(pose)
        _emit("animation_keyed", frame=args.frame, channels=len(keyed.channels))
        output = gateway.save_new(args.output)
        _emit("scene_saved", scene=str(output))
        return {"status": "ok", "output": str(output), "frame": args.frame,
                "channels": len(keyed.channels)}
    if args.command == "animation-enable":
        service = {"limb": EnableBodyCharacterLimbAnimation,
                   "stretch": EnableBodyCharacterStretchMatching,
                   "spline": EnableBodyCharacterSplineAnimation,
                   "spaces": EnableBodyCharacterSpaceAnimation}[args.kind]
        enabled = service(host).apply()
        _emit("animation_channels_enabled", kind=args.kind,
              channels=len(enabled.channels))
        output = gateway.save_new(args.output)
        _emit("scene_saved", scene=str(output))
        return {"status": "ok", "output": str(output), "kind": args.kind,
                "channels": len(enabled.channels)}
    if args.command in ("animation-bake-limb", "animation-bake-spine"):
        if args.command == "animation-bake-limb":
            baked = BakeBodyCharacterLimbMode(host).execute(
                args.start, args.end, args.limb, args.side, args.mode, args.step)
        else:
            baked = BakeBodyCharacterSpineMode(host).execute(
                args.start, args.end, args.mode, args.step)
        _emit("animation_mode_baked", mode=args.mode,
              frames=len(baked.samples))
        output = gateway.save_new(args.output)
        _emit("scene_saved", scene=str(output))
        return {"status": "ok", "output": str(output), "mode": args.mode,
                "frames": len(baked.samples)}
    if args.command == "animation-switch-space":
        pose = SwitchBodyCharacterSpace(host).execute(
            args.key, args.mode, args.frame)
        mode = dict(pose.spaces)[args.key]
        _emit("animation_space_switched", key=args.key,
              mode=mode, frame=args.frame)
        output = gateway.save_new(args.output)
        _emit("scene_saved", scene=str(output))
        return {"status": "ok", "output": str(output), "key": args.key,
                "mode": mode, "frame": args.frame}
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
    if args.command.startswith("face-library-"):
        try:
            print(json.dumps(_run_library(args), ensure_ascii=False), flush=True)
            return 0
        except (OSError, ValueError, RuntimeError) as error:
            _emit("failed", type=type(error).__name__, message=str(error))
            return 2
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
