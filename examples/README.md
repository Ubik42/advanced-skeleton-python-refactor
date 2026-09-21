# 全身控制与显式蒙皮示例

`maya_complete_character.py` 的 `build_character(with_hand=True)` 从空场景生成 Fit、Body、完整角色控制与代理网格，并写入每个顶点的显式权重。`with_hand=False` 使用 30 关节身体，默认使用 70 关节五指身体。返回值包含 `host`、`container`、`rig`、`mesh`、`skin` 和 `weights`。

环境要求：Maya 2024、Z Up、degree 角度单位、Undo 开启。场景不得已有 joint、mesh、FitSkeleton 或 AdvPy 命名对象；不清空已有场景。普通标记对象和选择会保留。

在仓库目录运行的 mayapy 脚本中：

```python
import sys
from pathlib import Path
import maya.standalone

root = Path.cwd()
sys.path[:0] = [str(root / "src"), str(root / "examples")]
maya.standalone.initialize(name="python")
try:
    from maya import cmds
    from maya_complete_character import build_character
    from adv_py.application import SwitchBodyControlSpace

    cmds.upAxis(axis="z", rotateView=False)
    cmds.undoInfo(state=True)
    character = build_character(with_hand=True)
    spine = character.rig.plan.torso.torso.spine
    cmds.setAttr(spine.fk_controls[1] + ".rotateZ", -20)
    SwitchBodyControlSpace(character.host).execute(
        character.rig.plan.control_spaces, "head", "global",
    )
finally:
    maya.standalone.uninitialize()
```

代理网格由每条非零身体骨段的低分段圆柱合并而成：30 关节对应 348 顶点，70 关节对应 828 顶点。每个顶点分配相邻两关节的正权重，总和为 1。权重由示例骨段几何确定，然后交给 `BindSkin` 与 `EditSkinWeights` 的既有校验及读回接口。代理包含分离的表面，目的是复现控制到线性蒙皮的完整链路，不代表生产网格拓扑或自动高质量权重。

示例宿主把内部用例加入同一外层事务，任何异常向外传播并整体回滚；标准宿主仍拒绝嵌套事务。一次 Undo 移除本次 Fit、Body、控制、网格与 skinCluster，Redo 恢复相同位置。适配器以 UUID 区分本次新建对象，在事务结束记录其无输入局部变换，避免重做世界空间构建命令时依赖部分恢复的父级。

综合后台验收入口为 `validation/maya_complete_character_smoke.py`。它核对显式权重、全身代表动作、脊柱双向匹配、全部空间切换、Global 移动 / 旋转 / 1.5 倍缩放、整个流程 Undo / Redo，以及蒙皮写入阶段注入失败后的整体回滚。具体命令见 [后台验证](../validation/README.md)。


## 已保存角色的全身静态姿态

完整角色构建后，在绑定姿态执行 `RegisterBodyCharacter(host).apply(rig)`，再保存场景。角色登记保存在场景中；关闭并用新的 Maya standalone 进程重新打开后，`examples/maya_saved_character_pose.py` 的两个函数只依赖场景登记与姿态文件：

```python
from maya import cmds
from maya_saved_character_pose import capture_to_file, restore_from_file
from adv_py.adapters import MayaBodyBuildHost
from adv_py.application import ResolveBodyCharacter, MatchBodySpine

# Maya standalone 已初始化；传入实际场景和新文件的绝对路径。
cmds.file(scene_path, open=True, force=True)
capture_to_file(new_pose_path)
# 对控制器做静态修改后恢复。
restore_from_file(new_pose_path)
character = ResolveBodyCharacter(MayaBodyBuildHost()).execute()
MatchBodySpine(MayaBodyBuildHost()).execute(character.spine, "ik")
```

应用层分别提供 `CaptureBodyCharacterPose(host).execute()`、`ApplyBodyCharacterPose(host).plan(pose)` 和 `.apply(pose)`。预演只读；应用在一笔事务中恢复全部声明控制值，再恢复五组空间来源及目标偏移。空间名字相同也需要恢复偏移，否则过去的空间重绑定会改变实际姿态。最后核对全部控制值、空间目标矩阵和 Body 矩阵，超出 `1e-4` 即回滚。

姿态 JSON 只有语义通道标识、数值、空间状态和变换参考，不包含 DAG 路径或 UUID。Body 世界矩阵用于结果复检，不直接写到受约束骨骼。文件带版本、内容摘要和绑定兼容摘要；只支持拓扑、绑定布局和特性一致的角色，不做跨骨架重定向。`save_character_pose` 发布前复检临时文件，原子创建新目标；已有目标或并发写入均报错，不覆盖文件。文件父目录必须已存在。

当前支持标准无 namespace、非引用的单角色、cm / degree 单位和正等比 Global 缩放。静态捕获与应用拒绝动画层、动画输入、外部输入及锁定通道；不清除键、不创建键，不保证其他帧历史运动。手部旧预设接口继续保留其独立语义。

完整的两进程复现命令见 [角色姿态验收](../validation/README.md)。


## 已保存角色的动画操作

`maya_saved_character_animation.py` 提供 `capture_to_file(destination, start, end, step=1)`、`restore_from_file(source)` 和 `convert_spine(start, end, mode, step=1)`。角色必须在构建绑定姿态完成登记；之后允许原生用户动画曲线，保存重开后仍可使用相同入口。

片段恢复在一笔事务中写入所有采样帧，其他帧原有键值保留；脊柱转换在每个采样帧匹配全身世界姿态，再写入目标 FK / IK 控制。时间单位、完整数据形态和点间插值限制见 [角色动画操作](../docs/角色动画操作.md)。
