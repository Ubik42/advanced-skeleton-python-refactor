# 来源骨架共用主体构建：2026-09-30

依据：AdvancedSkeleton 6.925 `asFBXRig` 创建并标记 Fit 后调用 `asReBuildAdvancedSkeleton`（参考 MEL 第 77469 行）。导入层不应另建 FK／简化 IK 系统。

本次代码接入：

- FBX 导入调用 `BuildRegisteredBodyCharacter` 的来源骨架分支，删除宿主原来的独立 Main、FK 和三关节 IK 创建代码。
- 来源分支复用 Body 朝向构建、通用 FK、FKX／Sub／Extra、肢体机制、RP IK、FK／IK 混合、Main、Global 跟随、Aim、缩放补偿、来源通道锁定和选择集。
- 肢体读取现有 `fit_joint_ik_info`，沿原标签查询继承起止关节、重复系统后缀及完整父链。RP 求解不再仅接受三关节；中点采用原查询的索引。单组中线 Root／Chest 或数字标签 Spline 已接到共用曲线构建；控制器数量和曲线 CV 驱动仍需按原版继续改写，不能算完整 Spline 复刻。
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

## 尚未完成的范围

来源分支不能据此等同于原版通用构建的全部功能。仍需完整补齐：多组和侧向 Spline；原 Fit 标签控制器数量、CV 蒙皮及原控制器排布；带 RP／Spline IK 的来源 Inbetween 求解链和混合驱动；来源 RP 的通用区间匹配、额外 Follow／空间与动画发布恢复。Bendy 和 FK-only Inbetween 已接代码，但其组合、保存重开与真实绑定行为仍未验收，不能算全量复刻完成。

本次没有启动 Maya，没有运行场景测试，没有推送 GitHub。静态语法和宿主方法声明核对仅说明代码结构能被解析、调用的方法已有实现，不证明 Maya 绑定运行结果。Goal 继续进行中。

静态核对：693 个源文件可解析；来源主体编排调用的 27 个宿主方法均有声明；`git diff --check` 通过。未运行 Python 功能测试或 Maya 场景。
