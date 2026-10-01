# 来源 Spline、Root 与 Bendy OPM 接入

本批连续开发依据 AdvancedSkeleton 6.925 MEL 79525–79529、80507–80521、81690–81699、82728–82876、83745–83778、83920–83937 和 Root LegLock 矩阵分支。原版源码保持只读。

## 已接入代码

- 来源 Spline 的 Body 输出改为实际 FKX／IK 输出世界矩阵 BM、独立 ScaleBlend／ScaleCM、扭转补偿和实际父逆矩阵。IK scaler／volume 不再叠加进这些 IK 求解关节的本地缩放；FKX 已带有主控与 Sub 的缩放，普通 OPM 分支的 ScaleBlend FK 项为 1。
- 首关节采用既有 firstJointFixed 输出作为 IK 来源。普通直接 Root FK 也使用完整 FKX 世界矩阵接法；Root LegLock 的 OPM 分支接完整输出矩阵并归零本地 TRS／shear，旧角色保留原来的 DM 接法。
- Bendy 的 Body／Twist Part 由 MicroX 世界矩阵乘实际父逆矩阵驱动，不再使用父约束加只含缩放的 OPM。MicroOffset 的缩放继续来自该骨段的独立 ScaleBlend／FK 缩放乘 BendMPX 的 Y/Z 缩放。所有 Part 共享起点的独立来源，避免回读已经归零的 Body.scale。
- Spline 与 Bendy 连用时显式创建本地 ScaleBlend，使用主 FK scale 和独立 IK scaler／volume，避免将旧世界缩放约束输出再次乘入 MicroOffset。相关 IK 求解关节的本地缩放归一。
- 新图写入关闭字段集合的原生节点 JSON，保存所有权、实际边与常量；Body 与附加 Part 均纳入检查和路径更新。Root Motion 创建／删除时在姿态检查前切换真实父逆矩阵，并更新保存记录。
- 已有 Spline FK 匹配扩展接上原生 BM：匹配缩放通过比例矩阵作用于 FKX，Bendy 的共享 ScaleBlend 切换到匹配缩放。数值匹配读取完整 OPM 局部矩阵，避免读取恒为零／一的 TRS 通道。
- 新建来源 Spline 的固定首关节朝向层使用独立名字，避免与第 4 个 IK 主控的朝向层同名。保存布局保留旧命名；首关节固定图增加父链、权重和输出检查。
- 保存 Spline 的 Body／Bendy 矩阵索引、固定朝向命名策略；重建按保存图的索引逐项恢复。旧角色不会因为已有 RP 矩阵就自动切换其 Spline、Root 或 LegLock 图。

## 验证边界和剩余工作

只有静态语法、计划构造字段、本地模块依赖和差异检查；没有导入项目、运行功能测试、启动 Maya 或推送 GitHub。以上均为“代码接入，Maya 未验收”。

后续已补来源 Spline 原版普通对齐／切换及首关节姿态迁移代码，见[后续接入记录](source-spline-align-switch.md)。仍未完成：较老 Spline 求解版本的逐版本构建／迁移；主动增删控制器的动画／图交接；覆盖矩阵中尚未关闭的其他分支，以及最终 Maya 整链验收。代码接入并不证明这些项目已完成，不关闭 Goal。
