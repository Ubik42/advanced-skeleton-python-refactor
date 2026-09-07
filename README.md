# AdvancedSkeleton Python 重构工程

这是一个面向本机已授权 AdvancedSkeleton 安装的私有研究与迁移工程。长期目标是把绑定意图表达为 DCC 无关的 Python 数据与用例，再通过独立适配器落到 Maya 和 Blender。核心合同不依赖 `maya.cmds` 或 `bpy`，Blender 是一等目标宿主。

开发顺序严格采用 **Maya-first、Blender-second**：第一阶段以现有 ADV/MEL 行为为基准，在 Maya 内完成分模块 Python 重构；第二阶段只迁移已经在 Maya 稳定并形成清晰语义合同的能力。现有 Blender 代码是冻结的架构可行性验证，不代表两条产品线并行开发。

已验证环境：Windows、Maya 2024 standalone、Blender 5.2.0 LTS background、Python 3.10/3.14。当前版本完成二十八个 Maya-only 切片：FitSkeleton 数据与朝向、M/R/L 对称展开、30 关节 Body 构建与安全 ReBuild，以及双臂 FK/IK 机制链、FK controls、Wrist/Pole Vector RP IK。左右独立的 blend 属性现在把两套机制结果输出到 Body。腿/手指控制、匹配、蒙皮和产品 UI 尚未实现。

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
- `FitJointPatch` 可先生成逐字段变更计划，再在一个 Maya Undo Chunk 内创建、更新或删除属性，并重新读取目标字段完成复检。
- `InspectFitHierarchy` 一次读取 FitSkeleton 完整 DAG，使用纯 Python 检查唯一根、根命名与中心位置、父链完整性、重复短名及已确认的名称限制。
- `EnsureFitSkeletonSettings` 先预览缺失的容器字段，再在一个 Undo Chunk 内增量补齐显示、构建和 ReBuild 设置；已有值保持不变，脚本文本不会在该用例中执行。
- `CreateFitSkeleton` 根据 Maya 当前 Y/Z Up 创建根级圆环和完整默认设置，保持当前选择；任何同名节点都会在事务前阻止创建，不会被删除或自动改名。
- `CreateFitTemplate` 可在空容器内原子创建任意已验证的 `FitTemplateSpec`；`CreateMinimalFitTemplate` 保留三关节兼容入口。
- `synthetic_upper_body_fit_template` 生成 14 关节 T-pose 躯干、颈、头和双臂树，验证 Spine2 三分支、局部位置及 Maya 标签。该素材由代码独立生成，不读取授权安装中的身体模板。
- `BuildSyntheticUpperBodyFit` 在空且已配置的 FitSkeleton 上先预演完整层级与 11 个朝向，再用一个 Undo 事务创建并朝向 14 关节上半身树；创建后的实际计划若与预演不同，会回滚整棵树。
- `BuildOrientedFitTemplate` 把模板创建、真实场景计划复算与朝向提交组合成可复用的一次 Undo 用例；`BuildSyntheticBodySourceFit` 生成 18 关节的中心链与单侧 Right 臂/腿源拓扑。
- `PlanFitSymmetry` 从完整 Fit 层级和镜像元数据生成 `_M/_R/_L` 构建实例。默认 18 个源关节展开为 30 个实例，`noMirror/noMirrorLeft` 沿父链继承，未标记的 Left 起始分支会在构建前拒绝。
- `BuildBodySkeleton` 在全量名称与源标签预检后，把 30 个对称实例作为根级 Maya joint DAG 一次提交；构建后复检路径、父级、世界位置、Maya side、标签与中性朝向，并确认 Fit 源未改变。
- `OrientBodySkeleton` 把 Fit 世界轴传递给 M/R 输出；L 输出反射 X Aim 与 Y Secondary 后用叉积重建右手 Z 轴。写入前检查完整 `jointOrient` 可写性，单事务写入后恢复全部世界位置，并复检拓扑、位置、朝向、Fit 输入和幂等性。
- `BuildOrientedBodySkeleton` 复用同一套物化与朝向步骤，在一个 Maya Undo Chunk 内完成 30 joints 的创建、朝向、位置恢复和复检；朝向阶段失败时，新建骨架也会一并撤销。
- 原子 Body 根节点保存锁定的 owner、artifact kind、schema、Fit 来源和 joint 数量；`InspectBodySkeletonProvenance` 只读判断现有骨架是否属于本工程的当前合同，为后续安全 ReBuild 提供明确边界。
- `InspectBodyRebuildSafety` 组合当前 Fit 展开、Body provenance、实际 joint 父链、根下全部 DAG 节点和外部 DG 连接；用户 attachment、skinCluster、constraint、动画曲线或普通连接都会以稳定 issue 阻止替换。
- `ReplaceOwnedBodySkeleton` 只替换通过安全评估的 Python Body。预检会忽略旧树自身的同名路径并保留外部冲突，事务内再次检查场景漂移后删除旧树、完整重建并复检；任一失败由同一 Undo 恢复旧 Body。
- `BuildBodyArmFkControls` 从已验证的 Python Body 快照生成双侧 Shoulder/Elbow/Wrist FK 规格，在单个 Undo Chunk 内创建 6 个零通道 NURBS 控制器、offset 层级和 orientConstraint；名称、Body 所有权、Fit 输入或构建后连线异常都会阻止或回滚整套控制。
- `BuildBodyArmMechanisms` 为左右手臂分别生成 FK 与 IK 的 Shoulder/Elbow/Wrist 驱动链，共 12 个机制 joint。每个 joint 保存到 Body 来源的 message 连线，初始世界帧与 source joint 一致，两套链可独立运动并由一次 Undo 完整移除。
- `BuildBodyArmFkMechanismControls` 先核对 Body provenance 与完整 mechanism 快照，再让 6 个 FK controls 驱动对应 FK driver joints；Body 和 IK 链保持不受 FK 操作直接影响，控制层与机制层可分别 Undo。
- `BuildBodyArmIkControls` 根据 Shoulder/Elbow/Wrist 几何计算稳定 Pole Vector 位置，为左右 IK mechanism 创建 Wrist/PV NURBS controls、RP IK Handle 和 poleVectorConstraint；可达目标位置经过真实 Maya 求解验证。
- `BuildBodyArmBlend` 创建左右独立的 `armIkFk_R/L` 属性、reverse 权重和 6 个双源 orientConstraint；FK=0、IK=1 与 0.5 混合均在 Maya 2024 中验证。
- `EditFitJointPositions` 对显式关节提交本地位置 Patch，只写实际变化且可写的轴；锁定/驱动轴、Root 离中和无效层级会在批量事务前失败。
- `OrientSimpleFitChain` 为唯一子级或显式选择的分支子级建立 X-Aim/Y-Secondary 朝向，自动选择与 Aim 正交的世界参考轴，并补偿 Maya 隐式产生的后代位置与全部直接子级 jointOrient 变化。
- worldOrient 元数据会解析为带正负号的本地 Up/Forward 轴策略；不完整、同轴冲突或当前写入器尚不支持的组合会在 Undo 事务前停止。
- `OrientWorldFitJoints` 在 Maya Y-Up 单子链中应用固定 Up/Forward，或用全局 `secondaryAxis` 与子级水平投影解算 free Forward；两者都写入完整右手系世界朝向并补偿后代位置。
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
- 世界矩阵已经覆盖平移、骨骼朝向和本地 Y-roll；镜像合同已覆盖 YZ 平面位置、拓扑展开和右手行为朝向，非均匀缩放尚未进入合同。
- 宿主事务提供确定性显式回滚，目前不依赖 Blender 后台模式下不稳定的全局 Undo Stack。
- Blender 将 Bind 与 FK/IK 机制骨链放在独立 Armature，避免跨骨链 blend 驱动形成依赖环；该差异留在适配器内部。
- 当前 IK/FK 是最小可运行合同，尚无镜像 limb、IK/FK 无缝匹配、拉伸和 twist。
- Maya 重构阶段达到门槛前，不继续扩展 Blender 功能；Blender 适配器只做防回归维护。
- 当前 Maya 主线已形成双臂 FK control / RP IK control → mechanisms → blend → Body 的可运行路径。下一步进入 IK/FK match、控制可见性和更完整的 Body Build 编排；腿/手指、World Match 与其他阶段仍待后续切片。
