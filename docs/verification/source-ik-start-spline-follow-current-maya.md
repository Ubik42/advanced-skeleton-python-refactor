# IK 起点、Spline 跟随与 Twist 缩放：当前 Maya 记录

2026-10-02 UTC。ADV 6.925 原版 MEL 保持只读，运行环境为本地 Maya 2024；没有推送 GitHub。

本批连续处理完整来源图、登记和重建，集中运行 Maya 验证。按原版补齐：

- MEL 80418–80499 的 IKParentConstraint → IKXOffset → 零 JO IKX 起点层在两种模式均创建，不能只在 OPM 模式创建。RP 长度测量起点与 IKXOffset 共用该父帧，保留绑定局部矩阵，并纳入锁定登记与接线审计。
- Spline 第一段的 Constrained 接收恢复原版父帧。OPM 接完整父世界矩阵；非 OPM 用无偏移 parentConstraint 与 Main scaleConstraint。第一段 Hybrid Follow 在非 OPM 模式分解完整 TRS／shear。控制器根不再重复继承 Main，对应原版独立 IKHandle 与缩放后的 IKJoints。
- MEL 78897 的非 OPM TwistSystem Main 缩放因子补回独立 Twist 父参考。原版 `asMatrixConnectAttr` 把父世界矩阵分解到已缩放的 TwistSystem，不能直接用父逆矩阵抵消此因素。Python 在每个已登记父参考图中表达这一矩阵因素；现有控制器地址保留。
- 新 Spline 跟随布局有明确持久化标记，旧登记缺省保留旧布局。同布局重建捕获旧 IK 起点、测量与 Twist 布局；显式改变 Spline 控制数量时仅迁移目标系统，避免修改无关 Arm／Leg 的所有权路径。

严格对照使用未修改原版生成的参考场景、108 个 Body／Part 关节、48 组控制用例，阈值保持 `1e-4`。

| 布局 | 全身严格对照 | 创建及完整重建 |
| --- | --- | --- |
| OPM 四组 Spline | 48／48；全局最大差异 0.0000490290 | Skin、姿态／动画往返、保存重开、FBX、保留原生 Skin／动画对象、撤销重做通过 |
| 非 OPM 四组 Spline | 44／48；全局最大差异 0.0001441541 | 同上，全部通过 |

非 OPM 中 Tail／Solo／Root 的最大差异分别为约 `6.64e-8`、`5.94e-8`、`9.29e-8`；Hip 与 Knee 最大差异分别约 `1.81e-8`、`2.70e-8`。前批侧边 Spline 的约 0.393／0.233 偏差及髋部约 0.00117 偏差已消除。

仍未通过的四组是 `Spine_M_main_nonuniform`、`SplineTail_R_main_nonuniform`、`SplineTail_L_main_nonuniform`、`SplineSolo_L_main_nonuniform`，都指向左侧肩／肘 Bendy Part。最大关节为 ShoulderPart2_L，约 0.0001441541；ElbowPart2_L 约 0.0001306978。没有放宽阈值，也没有将全身非 OPM 结果报为通过。此前标准 biped 的 left_arm_ik 小差异本批未独立重跑，仍待核对。

旧非 OPM 场景的 SplineTail_L 控制数量 3→5→3 迁移通过：保留原生 Skin／曲线身份、权重与成员、其他三组系统数量，撤销重做、同布局后续重建及保存重开通过。此迁移运行于本批 IK／Spline 修复后、最后 Twist 缩放修复前；最后修复保留旧图策略，新非 OPM 场景的完整重建已验证新增 Twist 布局持久化。

证据位于 `validation/results/`：

- OPM：`biped-source-native-follow-v3-opm/`、同名日志、`original-source-native-follow-v3-opm-pose.json`。
- 非 OPM：`biped-source-native-follow-v4-nonopm/`、同名日志、`original-source-native-follow-v4-nonopm-pose.json`。
- 旧场景数量迁移：`spline-legacy-to-native-follow-v3-count-SplineTail_L/spline-count-rebuild.json`，状态 passed。

下一项先连贯处理剩余肩／肘 Bendy 对照差异及标准左臂 IK，再推进覆盖矩阵中的其他明确缺口。当前证据证明上述核心组合的运行状态，不代表全部 ADV 源码、可选功能或默认模型外观已经复刻完成。Goal 保持进行中。
