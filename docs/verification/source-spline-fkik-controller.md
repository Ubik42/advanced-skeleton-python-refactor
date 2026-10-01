# 来源 Spline 独立 FKIK 控制器

2026-10-01，代码接入；用户本轮解除真实运行限制后，已启动 Maya 2024 集中运行来源标准骨架主链。运行在创建 Fit 的 Hip 朝向处失败，尚未进入 Body；本批 FKIK 控制器未获 Maya 验收，未推送 GitHub。

对照只读 `AdvancedSkeleton.mel` 的 Advanced FKIK 段（约 81830–81945），来源 Spline 新建流程增加 `FKIK{系统}_{侧别}` 控制器与 `FKIKParentConstraint{系统}_{侧别}` 接收层，位于 `Group|MotionSystem|FKIKSystem`。复用本地原版 `FKIK_icon` 曲线，按 Fit 范围和 IK 长度选择尺寸，冻结图形的 Y 轴 90 度旋转，按原版的左右／NonSymmetry 符号、fatWidth 和外侧方向放置。父级跟随取实际直接关节父级（含 Part）；直接父级为 Root_M 时使用 LegLockConstrained，无关节父级时使用起点本身。OPM 分支保留缩放，普通约束分支只保留父约束。

用户模式属性移到独立控制器，名称 `FKIKBlend`、范围 0–10。驱动权重由原版 0.1 unitConversion 输出提供；FK 反向权重、Body 矩阵、Root／LegLock、Part、Inbetween、Bendy 与标准 Spline 驱动消费者共同使用归一化输出。最后一个 IK 控制器继续保存 stretchy、volume、ikHybridVis、ikCvVis 和 Follow 属性。

autoVis／FKVis／IKVis 位于独立 FKIK 控制器。显示条件直接接用户 0–10 值，FK 显示使用 setRange 的 10→0 输出；Hybrid 显示经过另一条 0.1 unitConversion，再进入原版 average／ikHybridVis／-0.5 图。IK 控制曲线形状和参考曲线继续使用原显示入口。

单姿态匹配、原版 Align／Switch、前帧保护键、区间切换和精确迁移均按实际模式属性及端点值操作。跨角色 IK／阶梯 FKIK 迁移把采样值归一化后判定端点，原生曲线仍使用用户范围；来源和目标范围不同的直接曲线迁移会拒绝，未增加隐式转换。

保存格式增加闭合的 source_mode 数据，核对骨链标记、模式通道唯一性、控制器／接收层／父级节点身份，并纳入角色登记、ControlSet 与 AllSet。多组 Spline 保留各自模式控制器；命名空间包装透传角色身份对象。同布局重建保留保存的 source_mode，包括旧角色的 None：旧 0–1 模式图继续按原保存布局恢复，不在重建中自动搬移或缩放动画曲线。

本批集中通过 733 个源码文件的 AST 语法检查和改动文件的本地导入路径检查；静态检查阶段未导入项目。随后实际 Maya 运行暴露完全直腿 RP 平面退化：Hip primary=(0,-1,0)，end reference=(0,8,0)。原版在约 7110–7120 有检测零旋转并将中间 IK 关节沿世界 Z 轻移的分支；当前朝向路径没有接入这项位置调整，仍须贯通规划、写入和位置复检，不能用任意备用轴掩盖。日志位于忽略的 validation/results/maya2024-source-current-20261001.log。

仍需开发：主动改变 Spline 控制数量时的节点增删、接收器／通道重映射和动画交接；旧 0–1 模式图到独立 0–10 控制器的显式升级；覆盖矩阵中的其他未完成项。新增代码尚未经 Maya 整链验收，不代表全量复刻完成。
