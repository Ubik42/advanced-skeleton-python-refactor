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

当前集中运行结果：

| 布局 | 严格原版动态对照 | 生命周期 |
| --- | --- | --- |
| OPM 四系统，108 Body／Part | 48／48，阈值 1e-4 | 创建、Skin、动画、保存重开、FBX、重建、撤销重做通过 |
| OPM 两 Body 关节布局，97 Body／Part | 48／48，阈值 1e-4 | 创建及完整重建通过 |
| 非 OPM 四系统，108 Body／Part | 43／48，阈值 1e-4；前批为 12／48 | 创建、Skin、动画、保存重开、FBX、保留原生对象的重建和撤销重做通过 |

OPM 对照产物：`original-spline-end-frame-multi-pose.json`、`original-spline-end-frame-pose.json`。
非 OPM 当前场景／日志：`biped-source-nonopm-end-ssc/`、`biped-source-nonopm-end-ssc.log`。
非 OPM 当前对照：`original-source-nonopm-end-ssc-pose.json`。以上产物均位于 `validation/results/`。

剩下五个非 OPM 失败用例为 `global_scale`、`Spine_M_main_nonuniform`、`SplineTail_R_main_nonuniform`、`SplineTail_L_main_nonuniform`、`SplineSolo_L_main_nonuniform`。最大差异分别约 0.12、0.37、1.30、1.30、1.30。多处上半身同时出现差异，下一步应核对 Root／Spline 原生求解及 Main 缩放接收，不能只针对报告中的最大误差关节补偏移。

标准 biped 前批左臂 IK 的约 0.00014226263 差异仍待修复，本批没有宣称修好。整体 ADV 复刻未完成，长期 Goal 保持活跃。

非 OPM 的 SplineTail_L 控制数量 3→5→3 已通过完整 Maya 验收：原生 Skin／动画曲线 UUID、权重和成员、撤销重做、保存重开、废弃曲线保留为断开状态、用户选择集更新、其余三个系统数量保留，以及数量变更后的同布局重建均通过。结果为 validation/results/spline-nonopm-count-SplineTail_L/spline-count-rebuild.json。
