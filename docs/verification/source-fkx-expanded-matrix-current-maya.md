# 来源 FKX、FK Part、IK 起点与 Spline 扩展缩放索引

2026-10-02 UTC，Maya 2024。只读 ADV 6.925 MEL，继续 Python 复刻，无 GitHub 推送。

## 本批实际接入

Bendy／Twist 父参考的 FK／IK 混合输入改为真实 FKX 控制输出。原来的 parent-constrained FK 中间骨骼在非均匀 Main 缩放下丢失剪切；原版 Body BM／Bendy world-up 直接取 FKX。改动进入共用来源 Part 构建，覆盖 RP 与 Spline 的控制接收。

FK-only Inbetween Body Part 改为完整 FKX 世界矩阵、原有 Twist offset 和实际父逆矩阵。移除被接管的朝向约束及本地变换输入，接入现有闭合 Body 矩阵记录和登记检查。标准 biped 的 Neck 分段已实际验证。

OPM RP 起点恢复 MEL 80433–80499 的 IKParentConstraint → IKXOffset → IKX 层级：父跟随矩阵去掉缩放与剪切，绑定旋转由 Offset 承担，IKX jointOrient 为零。脚部起点查找、机制链恢复、登记、命名空间转换与重建使用新路径。闭合记录同时验证父跟随接线、Offset 的本地绑定矩阵、旋转顺序及 IKX 零朝向。传统非 OPM 暂保留其已有起点图，不宣称这部分也完成原版两层替换。

Spline 的基础关节缩放权重改按 asGetIKJoints 的 Inbetween 扩展链索引计算，连同体积权重一起修正；Twist 分段不加入 Fit Inbetween 链。索引进入 Spline 登记与严格解码，旧记录缺字段按旧布局读回，同布局重建保留保存的索引。

被新 Inbetween 下游图替换的旧 PM／MM 仅在接收身份、连接和节点类型相符且无消费者时删除，共享输入保留。低层 Inbetween 读回识别闭合新图，避免继续要求被替换的旧图。

## Maya 证据

`biped-source-final-matrix-fixed`：标准 biped OPM／Bendy，72 Body／18 Part／2233 通道。新建、Skin、姿态／动画文件往返、保存重开、FBX、保留 Skin／曲线 UUID 的重建和单次撤销重做通过。

`biped-source-uneven-current`：测试副本设 Root.inbetweenJoints=1、Spine1.inbetweenJoints=3、Neck.inbetweenJoints=1，原资产未改。72 Body／17 Part／2215 通道的相同完整生命周期通过。未修改的原版 MEL 在独立 Maya GUI 上构建相同测试副本，保存 89 个 Body／Part 的参考场景；原版 MEL SHA-256 为 828e6df4b7cabef3114f766af0e938b529e4b5599e22b014aa254a9695a3db02。

`biped-source-final-nonopm-current`：传统非 OPM 的标准 biped／Bendy 完整生命周期也通过，FBX 906864 字节；这不证明传统图的全部动态姿态与原版等价。

原来的 30 组标准对照现为 29 组通过，Main 非均匀缩放最大差约 4.9029024e-5，已经通过 1e-4 阈值。左臂 IK 位移仍差约 0.0001422626；两层起点替换没有消除此误差，不能宣称修复。

新增 `--source-matrices` 七组组合用例后，标准 90 关节×37 组和不均匀分段 89 关节×37 组均为 33／37 组通过、汇总 failed。新增 Neck FK／Part 缩放与旋转、Arm IK＋Main 非均匀缩放均通过。新增三组 Spline IK 差异必须保留：

| 用例 | 标准最大差异 | 不均匀分段最大差异 |
| --- | ---: | ---: |
| Spline IK＋Main 非均匀缩放 | 0.51132387 | 0.51058256 |
| Spline IK 中间控制器位移 | 0.21621773 | 0.20552242 |
| Spline IK 中间控制器缩放 | 0.05747226 | 0.05159119 |

报告分别为 `original-source-final-matrix-pose.json` 和 `original-source-uneven-pose.json`，结果保留于 validation/results。阈值未放宽，失败用例未删除。

## 下一段必须替换的主体逻辑

当前 `maya_fit_inbetween_spline_ik.py` 用相邻 corrected Spline 输出的 blendMatrix 插值生成独立 Part IKX。这是此前实现留下的架构差异：原版 Fit Inbetween 节点进入完整 IKX 父链、参与原生 ikSplineSolver 求解；仅补矩阵和缩放索引无法完成等价。

下一批应连贯替换 Spline 的完整扩展求解链、各段长度和 stretchEven 输出，并让 Body／Part、图登记、匹配、保存及重建读取同一真实链。同步核对曲线控制／上方向／rest offset，不能调整对照阈值或用局部补偿掩盖差异。之后继续左臂临界伸直求解输入及其余覆盖矩阵。默认模型外观、历史场景显式迁移和完整 ADV 源码覆盖仍未验收或未完成。Goal 活跃。
