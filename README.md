# AdvancedSkeleton Python 重构工程

这是一个面向本机已授权 AdvancedSkeleton 安装的私有研究与迁移工程。长期目标是把绑定意图表达为 DCC 无关的 Python 数据与用例，再通过独立适配器落到 Maya 和 Blender。核心合同不依赖 `maya.cmds` 或 `bpy`，Blender 是一等目标宿主。

开发顺序严格采用 **Maya-first、Blender-second**：第一阶段以现有 ADV/MEL 行为为基准，在 Maya 内完成分模块 Python 重构；第二阶段只迁移已经在 Maya 稳定并形成清晰语义合同的能力。现有 Blender 代码是冻结的架构可行性验证，不代表两条产品线并行开发。

已验证环境：Windows、Maya 2024 standalone、Blender 5.2.0 LTS background、Python 3.10/3.14。当前版本在既有可移植骨架基线上，完成两个 Maya-only FitSkeleton 切片：关节标签读写，以及 Fit joint 可选元数据读取与审计；尚未实现完整 FitSkeleton、蒙皮或产品 UI。

## 当前完成

- 不复制或提交 AdvancedSkeleton 原始源码，仅通过命令行读取本机路径。
- 提取 MEL 顶层过程、行号、规模、参数、调用关系、全局变量和动态 `eval` 风险。
- 生成 JSON 清单和中文 Markdown 体检报告。
- 提供 DCC 无关的 `RigPlan`、预检、构建编排和构建后复检合同。
- 提供可执行的内存、Maya 与 Blender `RigHost` 适配器。
- 同一份自生成两节骨架计划已在 Maya 2024 和 Blender 5.2 后台构建并清理。
- 同一份 `LimbSpec` 已在两边创建 Bind/FK/IK 三链、FK 控制、IK 目标、Pole Vector 和 blend，并完成真实姿态验收。
- Maya 关节标签用例已移除 UI 当前值和当前选择依赖，支持内置标签、自定义标签、批量预检、单次 Undo、读取与隐藏。
- `MayaFitJointHost` 可显式批量读取 Twist、Bendy、Inbetween、镜像、层级、世界朝向与 IK Local 等元数据，并在纯 Python 层报告冲突和范围问题。
- 提供受限的 Legacy Bridge，供未来 Python 功能在 Maya 内调用尚未迁移的 MEL 过程。
- 记录目标架构、迁移顺序、验收策略和许可边界。

## 最短使用路径

```powershell
cd D:\3D\_tools\advanced-skeleton-python-refactor
py -3 -m pip install -e .
adv-migrate inventory D:\Downloads\AdvancedSkeleton\AdvancedSkeleton.mel --output reports
```

运行不依赖 Maya 的最小测试：

```powershell
py -3 -m unittest discover -s tests -v
```

真实宿主验证命令和结果字段见 [后台宿主验证](validation/README.md)。

输出文件默认被 Git 忽略，因为它们可能包含专有过程名、源码路径和结构信息。

## 项目边界

本工程不是 AdvancedSkeleton 的开源镜像或替代产品，不包含原始 MEL、模板、图标、场景或文档，也不应公开发布由原始源码派生的实现。使用与修改仍受本机 AdvancedSkeleton 许可协议约束。

详细设计见 [迁移架构](docs/迁移架构.md)、[跨 DCC 路线](docs/跨DCC路线.md) 与 [社区调研](docs/社区调研.md)。第一次本机扫描识别到 1,052 个顶层过程、55 个 MEL 全局变量和 151 个含动态 `eval` 的过程；完整报告留在本机 `reports/`，不进入版本库。

## 当前跨 DCC 限制

- Blender 约束目前只支持单 source 和 `maintain_offset=False`。
- 控制器暂以 Maya transform / Blender Empty 表达，还没有可移植曲线形状。
- 世界矩阵已经覆盖平移、骨骼朝向和本地 Y-roll；非均匀缩放与镜像矩阵尚未进入合同。
- 宿主事务提供确定性显式回滚，目前不依赖 Blender 后台模式下不稳定的全局 Undo Stack。
- Blender 将 Bind 与 FK/IK 机制骨链放在独立 Armature，避免跨骨链 blend 驱动形成依赖环；该差异留在适配器内部。
- 当前 IK/FK 是最小可运行合同，尚无镜像 limb、IK/FK 无缝匹配、拉伸和 twist。
- Maya 重构阶段达到门槛前，不继续扩展 Blender 功能；Blender 适配器只做防回归维护。
- 当前 Maya FitSkeleton 已覆盖标签与一组常用可选元数据；元数据创建/删除、完整层级校验和编辑动作仍待后续切片。
