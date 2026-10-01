# 来源骨架共用主体构建：2026-09-30

依据：AdvancedSkeleton 6.925 `asFBXRig` 创建并标记 Fit 后调用 `asReBuildAdvancedSkeleton`（参考 MEL 第 77469 行）。导入层不应另建 FK／简化 IK 系统。

本次代码接入：

- FBX 导入调用 `BuildRegisteredBodyCharacter` 的来源骨架分支，删除宿主原来的独立 Main、FK 和三关节 IK 创建代码。
- 来源分支复用 Body 朝向构建、通用 FK、FKX／Sub／Extra、肢体机制、RP IK、FK／IK 混合、Main、Global 跟随、Aim、缩放补偿、来源通道锁定和选择集。
- 肢体读取现有 `fit_joint_ik_info`，沿原标签查询继承起止关节、重复系统后缀及完整父链。RP 求解不再仅接受三关节；中点采用原查询的索引。单组中线 Root／Chest 或数字标签 Spline 已接到共用曲线构建；本批继续按原版补写控制器数量、曲线 CV 驱动与 Hybrid 控制链，仍不能算完整 Spline 复刻。
- FK／IK 显隐乘入原 Sub／Extra 曲线开关，保留子控制变换，No Control 曲线不重新显现。根 FK 局部缩放与 Main 比例通过共同总控计划相乘。
- FBX 动画约束、烘焙、回接原蒙皮骨架和曲线投射使用真实控制器映射；投射的原名称规则仍按原语义名称判断。
- 登记在烘焙和可选 Root Motion 改挂之后创建；允许原生时间动画曲线，保留烘焙前绑定矩阵，更新改挂后的关节路径及控制空间根。
- 非标准、缺少 Root／Chest 描述的直接 Fit 构建可以进入来源分支；已有标准躯干描述的入口保持原主体编排。

后续代码接入：

- 来源分支创建 Fit Part 层级，FK、RP、Spline 机制使用改挂后的实际路径；Twist 从真实 FK／IK 输出投影，Part 缩放从相应 Body 输出读取。
- 单组中线 Spline 与标准曲线主体复用同一构建函数；FBX 动画别名包含对应的 Spline FK 机制控制，隐藏控制和末端路径同步改挂。
- 来源登记允许没有标准五组控制空间；有 Spline 的来源角色使用闭合的版本 4 登记，保存曲线计划并允许 Part 插入父链。
- 重建通过来源 Root FK 身份恢复来源入口，从 Fit 重新读取标签，并捕获已保存的 FKX、位置、缩放补偿、Global、Aim 和跟随布局。锁定所有 Root 动画轴时仍可通过节点身份识别。
- Spline 动画匹配扩展接管已有的 FK 位置与缩放连接，避免重复驱动；已有通道不重复登记，初始匹配缩放取实际当前输出。共用曲线校验识别对应匹配连接。
- 来源 Bendy 从现有 Twist Part 和实际 FK／IK 独立矩阵创建共用曲线、Micro、二级跟随与变形驱动，登记 Bendy／Micro 通道；普通 Twist 分配与 Bendy 不重复接管同一 Part。曲线保存校验保留其源图，并核对 Micro 接管的所有权、目标和输出。
- FK-only 来源 Inbetween 接入共用 FK 分段、回接、UnTwister 和通道登记，更新 FK 接收路径；已有分段缩放不会被通用 Part 缩放覆盖。
- 普通 Twist 调整参数进入首次登记。登记服务增加只读描述路径，使 FBX 在最后首次写文档之前也能合并这些控制通道。

## 2026-10-01 连续核心开发追加

- 来源 Inbetween 同时接入 FK-only、RP 与 Spline：沿实际 RP 完整骨链收集全部分段，每个 handle 只重建一次；共用 FK 接收、IK Part、Body 混合、UnTwister 与通道登记。插入后同步更新求解列表、机制父路径、辅助 IKX 和 FK 末端／跟随内部引用。
- 来源 Spline 主控数量读取 `FitJointIkInfo.control_count`；原版两个控制器分支补成三个。曲线 CV 保留实际骨链位置，少于四个 CV 使用 degree 1，其余 degree 3。实际主控与 CV 朝向由 Maya 边界按原版 `fractionMode` 的 motionPath 查询；没有运行该查询。
- CV 选择最近主控，再仅从相邻的 ±1 主控中选择第二个；保留距离权重、起止 stiff 重排及 setRange 条件。建图使用原版 maintained multMatrix／blendMatrix，分别实现 OPM 与非 OPM 输出。没有引入 CV SkinCluster。
- 来源曲线增加 CV、IKhybrid 控制器与层级、IK X 父约束输出、ikLocal 朝向、曲线形状朝向，以及 autoVis／FKVis／IKVis、ikCvVis、ikHybridVis 的显示路由。新增控制与矩阵接收层进入版本 4 登记，旧 spline 文档字段有兼容默认值。
- 来源主构建接入原有 Advanced Constraint、follow、follow*、followSpaces、ikFollow、AimAt、Geo Attach、Proximity Pin、Wheel／RollingBall、Curve Guide 与 OPM Tweaker。机制关节通过明确映射回 Body 身份；构建前合并检查控制依赖。Wheel、Curve Guide、Tweaker 的登记提供首次写文档之前的只读描述接口。
- RP 机制、IK 和混合现在按实际 R／L／M 骨链创建，支持单侧 No Mirror；共享参数保留双侧默认值。来源关节与系统标识允许原 Build Name 中的下划线。Foot 初始 IK 仍由末端实际标签包含 Foot 决定，不按 Leg 名称猜测。
- 旧 bool ikLocal 按原 MEL 的数值类型分支读为 addCtrl／nonZero；来源重建策略排除由 Inbetween 独立矩阵图驱动的 Part FK 控制，不再误当成普通 FK 朝向约束控制。

## 尚未完成的范围

来源分支不能据此等同于原版通用构建的全部功能。仍需补齐多组和侧向 Spline 的独立命名、曲线系统保存与重建；Spline CV／Hybrid 的完整 Extra／Sub 与 Follow 层级；来源 RP 的 ikLocal 三模式、脚部 pivots／Foot／IKhybrid 的通用接入；来源 RP 的通用区间动画匹配、发布与恢复。新旧 Spline 控制数量变化时的动画兼容也需要处理。源码覆盖矩阵里的其余主体差异仍然有效。

本批是 Python 代码接入，没有启动 Maya，没有运行功能／场景测试，没有推送 GitHub。静态解析与方法声明检查不能证明运行绑定与原版等价。Goal 保持进行中，不能宣布全量复刻完成。

集中静态核对：699 个源文件可解析；来源主体与新增阶段直接调用的 33 个宿主方法均有实现声明；新增模块的仓库导入声明可解析；差异格式检查通过。未执行导入、Python 功能测试或 Maya 场景。
