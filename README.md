# AdvancedSkeleton Python 重构工程

这是一个面向本机已授权 AdvancedSkeleton 安装的私有研究与迁移工程。长期目标是把绑定意图表达为 DCC 无关的 Python 数据与用例，再通过独立适配器落到 Maya 和 Blender。核心合同不依赖 `maya.cmds` 或 `bpy`，Blender 是一等目标宿主。

开发顺序严格采用 **Maya-first、Blender-second**：第一阶段以现有 ADV/MEL 行为为基准，在 Maya 内完成分模块 Python 重构；第二阶段只迁移已经在 Maya 稳定并形成清晰语义合同的能力。现有 Blender 代码是冻结的架构可行性验证，不代表两条产品线并行开发。

已验证环境：Windows、Maya 2024 standalone、Blender 5.2.0 LTS background、Python 3.10/3.14。当前版本完成七十六个 Maya-only 切片：FitSkeleton 数据与朝向、M/R/L 对称展开、基础 30 关节与五指 70 关节 Body 构建、安全 ReBuild、双臂完整 FK/IK、双腿原子 FK/IK/Foot Rig、双手分层 FK controls、Hand curl/spread 聚合姿态、语义 Hand Pose 保存/加载、命名预设库和统一角色总控。五指源模板在 Right Wrist 下定义 Thumb/Index/Middle/Ring/Pinky 各四个 Fit joints，38 个源 joints 展开成 70 个 Body joints。`BuildBodyHandFkControls` 在 Wrist_R/L 下分别建立控制根，每根手指由 1→2→3 三层曲线控制，并在绑定 offset 与 FK control 之间加入零通道 Pose 层；每侧 `handCurl`、五个单指 curl 与 `handSpread` 通过显式 DG 网络驱动 Pose 层，手动 FK rotate 仍可叠加。`ExportBodyHandPose`/`ImportBodyHandPose` 用不含 Maya 路径的 schema v1 保存这 14 个聚合值和 30 个 FK 旋转，调用方可通过 `RigA:Root_M` 这类明确角色根在多个 Maya namespace 实例间迁移同一姿态。导出允许只读捕获动画状态；导入默认保持严格静态写入，也可显式使用当前帧写键模式，并能只恢复明确指定的左手或右手。`MirrorBodyHandPose` 在场景内把一侧当前姿态镜像到对侧，保持聚合语义并按行为坐标系转换 FK 旋转。`SaveBodyHandPosePreset`、`InspectBodyHandPosePresetLibrary` 与 `ApplyBodyHandPosePreset` 再用安全中文名称和 `.handpose.json` 后缀组成 DCC 无关的目录预设库；保存原子落盘且不覆盖，清单只读校验全部文件，应用支持规范名称查询与单侧目标。只有目标侧需要满足写入条件，源侧与非目标侧仍做完整结构与结果复检。`BuildBodyCharacterRig` 保持 30 关节 Body 的 Arm/Leg/Global 行为，并在完整 70 关节五指 Body 上把 Hand 纳入同一个顶层事务。Skin 已覆盖显式绑定、稀疏权重写入、JSON 往返、路径映射、显式镜像及严格几何配对。当前尚未包含预设重命名/删除/缩略图、自动角色选择、逐指 spread、动画区间 bake、自动手指权重和产品 UI。

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
- `BuildOrientedFitTemplate` 把模板创建、真实场景计划复算与朝向提交组合成可复用的一次 Undo 用例；`BuildSyntheticBodySourceFit` 保留 18 关节基础源拓扑，`BuildSyntheticBodyWithHandSourceFit` 则在同一身体上增加一个可镜像的完整五指源。五个四关节链都使用 Finger 标签，Wrist 显式选择 Middle 分支朝向；预演、38 关节创建、28 个朝向写入、复检和失败回滚位于一个事务。
- `BuildBodyHandFkControls` 从已验证的 70 关节 Body 规划双侧五指控制。两个 Hand FK roots 直接挂在 Wrist_R/L 下；每指前三节建立逐级嵌套的 offset/Pose/control 与 orientConstraint，共 30 个零通道 Pose 层和 30 个 NURBS controls。每侧 Hand root 提供 `handCurl`、五个单指 curl 和 `handSpread`；30 个 `blendWeighted` 按 0.45/0.75/1.0 分段叠加全局与单指 curl，8 个 `multDoubleLinear` 为外侧四指提供带左右镜像符号的 spread。网络只驱动 Pose.rotateY/Z，控制器自身 rotate 保持可写。计划阶段核对完整父链、全部节点名和 30 个 Body 目标 rotate 输入；构建后复检 Pose 层、属性、DG 连线、Body 绑定姿态和 Fit 不变性，失败或一次 Undo 会完整移除控制系统。
- `ExportBodyHandPose` 把双侧 14 个聚合值与 30 个 FK control 本地旋转写入 DCC 无关的 schema v1 JSON；文件不保存 Maya DAG 路径，带 SHA-256 内容摘要，使用同目录临时文件复检后原子落盘并拒绝覆盖。调用方可显式传入 namespaced `body_root_name`，应用层从实际 Body 根解析同一 namespace，并要求全部 Body joints、Hand roots、controls、Pose 层与 DG 节点一致归属。只读导出可捕获当前动画姿态；`ImportBodyHandPose` 默认核对静态可写性和无输入连接，也可用 `keyframe=True` 在当前帧给未连接通道或原生 animCurve 写键。`target_side=FitBuildSide.RIGHT/LEFT` 只恢复指定手，计划会把另一侧当前值合并成完整预期文档。`MirrorBodyHandPose` 直接从当前源手构造对侧完整预期文档：聚合值同号复制，FK 旋转按 `(-X, -Y, Z)` 转换，并支持静态或当前帧写键。结构与最终文档仍全量复检，但源侧约束或未知驱动不会阻断目标侧；两种写入都只修改实际差异，重复执行不创建空事务，多角色场景不会依赖当前选择或模糊短名。
- Hand Pose 命名预设库以普通目录和 `.handpose.json` 文件为边界：名称先规范为 NFC，允许中文，但拒绝路径分隔符、控制字符、Windows 保留名、首尾空白、大小写或 Unicode 冲突。保存复用原子导出且拒绝覆盖；清单会只读解析并校验目录内全部预设；按名应用保留磁盘中的规范显示名，并继续复用 schema 摘要、显式 namespace、单侧目标、当前帧写键、幂等与单事务 Undo 合同。
- `PlanFitSymmetry` 从完整 Fit 层级和镜像元数据生成 `_M/_R/_L` 构建实例。默认 18 个源关节展开为 30 个实例，`noMirror/noMirrorLeft` 沿父链继承，未标记的 Left 起始分支会在构建前拒绝。
- `BuildBodySkeleton` 在全量名称与源标签预检后，把 30 个对称实例作为根级 Maya joint DAG 一次提交；构建后复检路径、父级、世界位置、Maya side、标签与中性朝向，并确认 Fit 源未改变。
- `OrientBodySkeleton` 把 Fit 世界轴传递给 M/R 输出；L 输出反射 X Aim 与 Y Secondary 后用叉积重建右手 Z 轴。写入前检查完整 `jointOrient` 可写性，单事务写入后恢复全部世界位置，并复检拓扑、位置、朝向、Fit 输入和幂等性。
- `BuildOrientedBodySkeleton` 复用同一套物化与朝向步骤，在一个 Maya Undo Chunk 内完成 30 joints 的创建、朝向、位置恢复和复检；朝向阶段失败时，新建骨架也会一并撤销。
- 原子 Body 根节点保存锁定的 owner、artifact kind、schema、Fit 来源和 joint 数量；`InspectBodySkeletonProvenance` 只读判断现有骨架是否属于本工程的当前合同，为后续安全 ReBuild 提供明确边界。
- `InspectBodyRebuildSafety` 组合当前 Fit 展开、Body provenance、实际 joint 父链、根下全部 DAG 节点和外部 DG 连接；用户 attachment、skinCluster、constraint、动画曲线或普通连接都会以稳定 issue 阻止替换。
- `ReplaceOwnedBodySkeleton` 只替换通过安全评估的 Python Body。预检会忽略旧树自身的同名路径并保留外部冲突，事务内再次检查场景漂移后删除旧树、完整重建并复检；任一失败由同一 Undo 恢复旧 Body。
- `BuildBodyArmFkControls` 从已验证的 Python Body 快照生成双侧 Shoulder/Elbow/Wrist FK 规格，在单个 Undo Chunk 内创建 6 个零通道 NURBS 控制器、offset 层级和 orientConstraint；名称、Body 所有权、Fit 输入或构建后连线异常都会阻止或回滚整套控制。
- `BuildBodyArmMechanisms` 为左右手臂分别生成 FK 与 IK 的 Shoulder/Elbow/Wrist 驱动链，共 12 个机制 joint。每个 joint 保存到 Body 来源的 message 连线，初始世界帧与 source joint 一致，两套链可独立运动并由一次 Undo 完整移除。
- `BuildBodyLegMechanisms` 复用可变长度的 DCC 无关 limb mechanism 合同，为左右腿分别生成 Hip→Knee→Ankle→Toes→ToesEnd FK 与 IK 驱动链；共 20 个 joint 在单一事务内创建并复检，失败或一次 Undo 都会完整移除。
- `BuildBodyArmFkMechanismControls` 先核对 Body provenance 与完整 mechanism 快照，再让 6 个 FK controls 驱动对应 FK driver joints；Body 和 IK 链保持不受 FK 操作直接影响，控制层与机制层可分别 Undo。
- `BuildBodyLegFkMechanismControls` 复用可变长度 limb FK 控制规格，为左右 Hip/Knee/Ankle/Toes 建立 8 个零通道 NURBS controls；Toes control 只驱动同侧 Toes FK driver，IK 链与 Body 继续保持隔离，控制层和机制层可分两次 Undo。
- `BuildBodyLegIkControls` 为左右 Leg IK mechanisms 建立 Ankle/Pole Vector controls、RP IK Handle 和 Ankle orientConstraint；笔直腿会从 Knee 世界轴中确定性选择非共线备用方向，真实目标求解与 Body 隔离已经 Maya 验证。
- `BuildBodyLegBlend` 创建左右独立的 `legIkFk_R/L`、reverse 节点、8 个双源 orientConstraint 和 Knee/Ankle 的 4 个双源 pointConstraint；Toes 旋转由同侧 FK/IK Toes driver 进入 Body，FK=0、IK=1、0.5 权重及左右隔离均在 Maya 2024 中验证。
- `BuildBodyLegVisibility` 复用通用 limb 显隐合同，把每侧 reverse 输出连接到 Hip FK 根层级，并把 `legIkFk_R/L` 连接到对应 Ankle/PV IK 根层级；执行前拒绝缺失源和不可写或已有输入的 visibility，构建失败由单一事务回滚。
- `BuildBodyLegRig` 在场景零修改预演后，用一个 Undo Chunk 依次创建 Leg mechanisms、FK controls、Body blend、Ankle/PV IK、模式显隐、双段 stretch、stretch bias、knee pin、主轴感知 twist/volume 与双侧 Foot pivot；全部属性和节点名进入统一碰撞预检，任一阶段失败会移除此前所有 Leg/Foot 产物，一次 Undo 可恢复干净 Body 和 ReBuild 安全状态。
- `BuildBodyCharacterRig` 从同一份 Body/Fit 快照预演 Arm、Leg 与可选 Hand 计划，并在一个外层 Undo Chunk 中复用各阶段而不嵌套事务。30 关节 Body 继续只组合 Arm/Leg/Global；完整 70 关节五指 Body 自动增加两个 Wrist 子根、30 个 Pose 层、30 个 Hand FK controls 与 curl/spread 网络，残缺五指在事务前拒绝。随后建立 `AdvPy_CharacterControls → AdvPy_GlobalOffset → AdvPy_Global` 层级，以统一 TRS 驱动 Body 和八个 limb 顶层根，并把正值 `globalScale` 接入全部九个根及 Arm/Leg stretch 比例补偿。构建后逐项核对所有阶段、Body 绑定姿态和 Fit 不变性，任何异常都会撤销完整角色 Rig。
- `MatchBodyLegFkToIk` 从当前 Hip/Knee/Ankle/Toes Body 姿态计算 Ankle IK、Pole Vector 与 Toe IK control 的目标世界帧；事务内先把目标侧 Foot 通道归零，再依次匹配三个控制目标并切换 blend，复检四关节位置/朝向、Foot 值和另一侧状态。
- `MatchBodyLegIkToFk` 按 Hip→Knee→Ankle→Toes 父子顺序把四层 FK controls 对齐到当前 Body 世界轴，并把当前 Hip–Knee、Knee–Ankle 的有符号本地主轴长度写入 FK drivers 后再切换；提交后复检段长、四关节位置/朝向、另一侧 blend、Fit 输入和 FK 控制本地平移。
- `BuildBodyLegFoot` 仍可为独立组合的 pre-Foot Leg stages 追加双侧五级 reverse-foot pivot；默认成品入口已经由 `BuildBodyLegRig` 原子包含该阶段。Ankle IK control 暴露 `footRoll/heelRoll/outerBank/innerBank/toeRoll/ballRoll`：自动 `footRoll` 由每侧 4 个分段节点和 3 个加法节点生成 Heel/Ball/Toe 输出，五个手动通道仍可叠加，inner bank 继续通过显式负号节点保持正值语义。RP IK Handle 挂到 Ball pivot；原 Ankle 朝向约束会在同一事务内安全改接到 Ball pivot，Toe pivot 下的零通道三轴 Toe IK control 直接驱动 Toes IK driver。
- 通用 `BodyLimbStretchPlan` 从 mechanism 世界轴确定每段实际本地主轴，Arm 与 Leg 只提供目标控制和业务命名。Leg 使用 Hip 到 Ankle IK control 的距离驱动 Knee/Ankle IK driver，`legStretch_R/L` 在 0–1 内混合，`legGlobalScale` 补偿角色缩放，短目标保持绑定段长；`legStretchBias_R/L` 只分配超出绑定长度的部分，默认按上下段绑定长度占比保持原有同比伸长。`legKneePin_R/L` 在该结果与全局比例补偿后的 Hip→PV、PV→Ankle 距离之间混合，最终总长比例继续驱动 volume。Foot pivot 位于测距目标之后，roll 不会反向改变腿长。
- `BuildBodyArmIkControls` 根据 Shoulder/Elbow/Wrist 几何计算稳定 Pole Vector 位置，为左右 IK mechanism 创建 Wrist/PV NURBS controls、RP IK Handle 和 poleVectorConstraint；可达目标位置经过真实 Maya 求解验证。
- Wrist IK control 通过独立 orientConstraint 驱动对应 Wrist IK driver；约束名称、source 和 driven joint 进入核心规格与构建后审计，为后续 FK→IK 姿态匹配提供手腕朝向合同。
- `MatchBodyArmFkToIk` 从当前 Body 的 Shoulder/Elbow/Wrist 世界姿态计算 Wrist IK 与 Pole Vector 目标；只允许目标侧处于 FK 模式且相关通道可写，并在一次 Undo 中对齐控制、切换 blend、复检关节位置和 Wrist 朝向，另一侧保持不变。
- `MatchBodyArmIkToFk` 按 Shoulder→Elbow→Wrist 父子顺序把 FK controls 对齐到当前 Body 世界轴，并把两段 FK driver 本地 X 长度匹配到当前 IK/Body 后再切回 FK；普通及拉伸姿态的三关节位置/朝向、另一侧 blend、Fit 输入和 FK control translate 零值均经过 Maya 复检。
- `BuildBodyArmBlend` 创建左右独立的 `armIkFk_R/L` 属性、reverse 权重和 6 个双源 orientConstraint；FK=0、IK=1 与 0.5 混合均在 Maya 2024 中验证。
- Arm blend 同时为两侧 Elbow/Wrist 建立 4 个双源 pointConstraint，使 FK/IK driver 的段长和世界位置变化能传到最终 Body；Shoulder 保持固定位置。
- `BodyArmStretchPlan` 为左右臂分别定义绑定长度、Wrist 测距、no-compression、0–1 stretch 强度和两段本地 X 输出；共享的正值 `armGlobalScale` 输入先修正参考长度，Maya DG 网络只在补偿后的 Wrist 距离超出原长时伸长。
- 通用 `BodyLimbTwistPlan` 根据每段端点与起点关节世界轴选择唯一主轴，再用对应四元数分量与 W 投影剥离 swing；Arm/Leg 包装保留业务命名，每侧 Upper/Lower 段默认各生成 2 个 helper，轴向角按比例分配，位置随 stretch 后的 Body 端点实时更新。
- 通用 `BodyLimbVolumePlan` 对每侧最终 stretch ratio 应用 `ratio^-0.5`，Arm/Leg 分别用独立强度在横向比例 1 与面积近似守恒值之间混合；每个 helper 都从 twist 主轴推导另外两条正交缩放轴，不修改轴向 scale。
- `BindSkin` 对一个显式 mesh 和显式 influence 集合执行零修改预演，拒绝缺失节点、空网格、已有 skinCluster 与名称冲突；Maya 在独立 Undo Chunk 内创建 closest-distance skinCluster，并复检几何体、影响关节、归一化和最大影响数。
- `EditSkinWeights` 接受显式顶点索引和完整非零 influence 权重，验证总和、索引范围、成员关系、锁权重和最大影响数；只提交实际变化，完成后逐顶点复检，重复应用不创建 Undo。
- `ExportSkinWeights` 将全部顶点写成带 schema v1 与 SHA-256 内容摘要的独立 JSON，使用同目录临时文件复检后原子落盘并拒绝覆盖；`ImportSkinWeights` 严格匹配 skin、mesh、顶点数、influence 集合和最大影响数，再复用权重事务恢复。
- `SkinWeightPathMapping` 允许导入到不同的目标 skinCluster、mesh 和 influence 路径；所有源 influence 必须完整且只出现一次，目标必须一一对应，映射后的文档重新通过完整权重与摘要校验。
- `MirrorSkinWeights` 根据显式且互不重叠的源/目标顶点对复制权重，并通过 influence 双射重写目标；中心 influence 可使用身份映射，未映射源权重、锁定目标或重复对应都会在写入前失败。
- `MirrorSkinWeightsByGeometry` 读取单个 mesh 的完整世界空间顶点位置，按调用方指定的 X 镜像平面、方向和容差生成严格一一对应的顶点对，再复用显式镜像的预检、权重事务与复检。
- `BuildBodyArmRig` 在场景零修改预演后，用一个事务依次构建 mechanisms、FK controls、Body blend、RP IK 和左右独立的模式显隐；FK=0 仅显示 FK 层级，IK=1 显示 Wrist/PV，最后阶段失败会回滚此前全部 Arm 节点，一个 Undo 也能完整移除成品。
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
- 当前 Maya Arm 与 Leg 均支持左右独立 IK stretch、主轴感知 twist helper 和只在 IK 模式响应的可调正交体积保持；Leg 还支持保持总长度的上下段 stretch bias，以及由 Pole Vector 与 Ankle 控制实时测距的 knee pin。完整 Character 入口已用统一 Global TRS 和正值等比 `globalScale` 串联 Body、Arm 与 Leg，70 关节 Body 会在同一事务增加 Hand FK；非均匀缩放、shear、World Match 与镜像 limb 尚未完成。
- 当前 Skin Bind 只接受调用方明确给出的单个 mesh 与 joint 列表；JSON 和 influence 映射都要求调用方给出完整路径及对应关系，不会自动猜测 namespace、短名或左右 influence。几何镜像只接受严格 X 平面对称顶点，不处理拓扑不对称或近似重采样。尚不支持权重模板、热区/测地线算法、批量绑定或解绑迁移。
- Maya 重构阶段达到门槛前，不继续扩展 Blender 功能；Blender 适配器只做防回归维护。
- 当前 Maya 主线已有 Arm/Leg/Hand/Global 的完整 Character 入口：双臂、双腿 FK/IK/Foot、完整五指 Hand FK 与 curl/spread 聚合层在同一事务构建，统一 Global control 驱动 Body 和九个根级目标，Hand roots 作为 Wrist 子级跟随 Arm FK/IK。30 关节旧 Body 不强制 Hand，70 关节五指 Body 自动启用 Hand，残缺五指会在事务前停止。Hand Pose schema v1 已可在 Maya 中保存、静态恢复、单侧恢复、当前帧安全写键或场景内左右镜像，并能在显式指定的 namespace 角色实例间复用；命名预设库已支持安全中文名称、原子保存、只读清单和按名应用。预设重命名/删除/缩略图、自动角色发现、逐指 spread、动画区间 bake、World Match、非均匀缩放与 Blender 迁移仍待后续 Maya 阶段。
