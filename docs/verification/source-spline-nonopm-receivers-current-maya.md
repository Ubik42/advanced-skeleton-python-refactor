# 来源 Spline 末端与传统非 OPM 接收：当前 Maya 记录

2026-10-02 UTC，本地 Maya 2024，原版 ADV 6.925 MEL 保持只读。没有推送 GitHub。

本批按原版场景图补齐两类接收，保留原版参数与分支：

- OPM 未创建普通 FK 控制器的末端仍继承原 FKX 的完整父级帧，不能套用普通 NoShear 接收。末端补偿和 Inbetween 下游接收同步修正，显式创建控制器的例外保留。
- 传统非 OPM 的 Main 缩放接入 DeformationSystem，Root 保留局部 FK scale。Spline 独立 IKScaler 与 FK 控制器局部 scale 通过原版 ScaleBlend 接入 Body／Part；求解 IKSp 不再接入体积 scale。
- 非 OPM Part 接入原 FKX／IKX 的 pointConstraint，FK-only Part 直接接局部 FK scale；新增闭合图登记、审计、重建地址改写和模式升级处理。
- Inbetween 插入后，Body 的 inverseScale 读取实际关节父级，避免沿旧 Spline 采样跳过 Part。
- Bendy falloff 读取整段骨骼长度。原版在 Part 插入之前捕获完整长度，不能改用最后一小段 Part 长度。
- 非 OPM 的 FK SSC 遍历全部原 Fit 身份，包括没有控制器的末端，补齐最后 Finger 父 FKX 的 SSC 设置。此修正已进入构建／重建，但未独立解决当前整体缩放差异。
- 多系统数量重建的角色登记超过旧 2 MB 上限。完整角色登记改为有界 8 MB，单条图记录仍使用原 2 MB 限制，完整字段／节点类型／身份／摘要检查保留。
- 非 OPM Root Spline 的 Base FK 不再重复套用通用缩放补偿，整体缩放用例已经通过。
- 按 MEL 79894／80151 补非 OPM Inbetween 的局部旋转分解／重组与完整 FKX 父帧；按原版 SSC 分支补 FKPS1 的原生 scaleConstraint 和位置缩放，下游 FK Offset 保留插入 Part 后的完整父级帧。为保留已有公开控制器地址，Python 使用矩阵接收表达该父帧，并非声称物理 DAG 已逐节点完全一致。
- 按 MEL 83464–83483 补非 Bendy IK Twist Part 位移：起点 Body 世界矩阵与下游独立 FKX／IKX 混合矩阵等分，再乘起点逆矩阵接本地位移。显式不补偿的 Part 保留已有 Twist CM／OPM 接收。新增闭合图记录、生成属性、单位转换重命名、改挂地址及 Spline 模式迁移处理。

当前集中运行结果：

| 布局 | 严格原版动态对照 | 生命周期 |
| --- | --- | --- |
| OPM 四系统，108 Body／Part | 48／48，阈值 1e-4 | 创建、Skin、动画、保存重开、FBX、重建、撤销重做通过 |
| OPM 两 Body 关节布局，97 Body／Part | 48／48，阈值 1e-4 | 创建及完整重建通过 |
| 非 OPM 四系统，108 Body／Part | 44／48，阈值 1e-4；前批为 43／48，较早为 12／48 | 创建、Skin、动画、保存重开、FBX、保留原生对象的重建和撤销重做通过 |

OPM 对照产物：`original-spline-end-frame-multi-pose.json`、`original-spline-end-frame-pose.json`。
非 OPM 当前场景／日志：`biped-source-nonopm-twist-position/`、`biped-source-nonopm-twist-position.log`。
非 OPM 当前对照：`original-source-nonopm-twist-position-pose.json`。以上产物均位于 `validation/results/`。

剩下四个非 OPM 失败用例为 `Spine_M_main_nonuniform`、`SplineTail_R_main_nonuniform`、`SplineTail_L_main_nonuniform`、`SplineSolo_L_main_nonuniform`。最大差异分别为 0.0475956651、0.3925744469、0.2332361515、0.2332361515，最大误差关节依次为 Knee_R、Tail0Part1_R、Tail0Part1_L、Solo0Part1_L。前批对应约 0.37／1.30／1.30／1.30；头颈／手指在 Spine 组合下已对齐。Twist Part 位移接线补齐后用例通过数没有继续增加，不能把该接线宣称为剩余缩放误差的根因修复。

进一步定位：Spine 组合下 Root、LegLock 和 Hip FKX 世界矩阵已与原版基本一致，Hip IKX 位置仍不同，Body Hip 在初始 Leg IK 模式下继承该差异。原版 IKXHip 经过 IKParentConstraintHip／IKXOffsetHip 两层，当前 Python 的 Hip IK Driver 直接位于缩放机制组下；需要核对原版两层父帧的绑定偏移及非均匀缩放行为。下一步优先核对该 RP IK 起点接收，以及侧边 Spline 的第一段 IKX 与 Part 接收；禁止添加报告特例偏移、修改阈值或引入 MEL 已注释废弃的 JOMM 逻辑。定位产物为 `nonopm-ik-parent-diagnostic.json`。

新增 Twist 位移在四系统场景的补偿 Part 路径经过集中 Maya 验证；显式不补偿 Part 的已有 CM 分支代码已接入，尚未单独构造该组合进行原版动态对照。OPM 两种布局结果沿用前批，本轮未重跑。

标准 biped 前批左臂 IK 的约 0.00014226263 差异仍待修复，本批没有宣称修好。整体 ADV 复刻未完成，长期 Goal 保持活跃。

最新非 OPM 的 SplineTail_L 控制数量 3→5→3 已通过完整 Maya 验收：原生 Skin／动画曲线 UUID、权重和成员、撤销重做、保存重开、废弃曲线保留为断开状态、用户选择集更新、其余三个系统数量保留，以及数量变更后的同布局重建均通过。补完整 FK 父帧后及新增 Twist 位移后分别集中验收通过。最新结果为 `validation/results/spline-nonopm-twist-position-count-SplineTail_L/spline-count-rebuild.json`。
