# 来源 RP 默认跟随、PoleAim 与动态缩放

2026-10-02 UTC，Maya 2024。以未修改的 ADV 6.925 MEL 和原版 biped Fit 为依据，继续补普通来源角色的动态主图；没有推送 GitHub。

本批实际接入：

- `asFollowLevels` 的 MainExtra（倒序）、Main、Root、Chest 默认目标；Pole 增加对应 IK 目标，Leg Pole 改用 PoleAim2，默认 followLeg 为 10。保留 centerBetweenFeet 和自动 Scapula 的排除条件。
- Arm swivel 接 IK handle；Leg swivel 接 PoleAim 的旋转矩阵。副轴参考按 MEL 80914 使用变形末端的绑定朝向，PoleAim2 保留 Pole 的世界朝向。
- follow 权重和 swivel 进入角色通道，闭合图记录进入保存、登记读回、命名空间改挂、FBX 暂存和重建；重建不会将构建记录当作用户属性覆盖新图。
- Main 原生 scaleXYZ 保持可编辑，已有统一 globalScale 移至外层 Offset，并参与 MainScaleMultiplyDivide 的乘法。RP 距离除数继承原版 Main.sy。
- RP 动态节点采用原版 Fit 后序遍历及源侧／镜像侧顺序。Pole.lock 的末端目标按创建当时的 objExists 判断，不能提前引用以后才创建的 Leg 测量节点。
- Bendy Part 保留原版本地 ScaleBlend，同时 MicroOffset 继续接缩放乘法。该双层结果是原版实际行为；旧 Python 在接 MicroX OPM 时清除了 Part 本地缩放。闭合矩阵记录兼容旧格式，并登记新增的 Part 缩放连接。
- FK NoShear 把平移和绑定旋转分开：先对父级世界矩阵去剪切，再应用绑定旋转及实际父逆矩阵，与 MEL 80240–80277 的顺序一致。

## 运行证据与边界

`biped-rp-follow-aligned-current` 已通过 72 Body／18 Part／2233 通道的新建、Skin、姿态与动画文件往返、保存重开、带 Skin FBX、原位重建、Skin／动画曲线 UUID 保留、单次撤销重做及重建保存重开。FBX 902944 字节。

传统非 OPM 的 `biped-rp-follow-nonopm-current` 同样通过上述生命周期，FBX 906848 字节。这仅证明该构建和持久化流程可运行，未证明传统图的全部动态姿态与原版等价。

严格对照入口 `validation/maya_original_body_pose_compare.py --extended` 扩为 30 组、90 个 Body／Part，共 2700 次世界矩阵比较，阈值仍为 1e-4；原版 FKIKBlend 10 对应现有 Python RP 模式 1。`original-rp-follow-aligned-pose.json` 中 26 组通过：原有七组、右臂 IK／swivel／拉伸／antiPop／length／Pole.lock／半混合、腿部位移／swivel、foot roll／rock、Root／Chest／Arm 默认跟随等。

该中间版本仍有 Main 非均匀缩放、Shoulder 非均匀缩放、Wrist 非均匀缩放和左臂 IK 位移四组差异。最新 NoShear 顺序修正后，`biped-rp-follow-noshear-current` 的完整生命周期再次通过；`original-rp-follow-noshear-pose.json` 中 27／30 组通过，Wrist 非均匀缩放已通过。仍失败的三组为 Main 非均匀缩放（最大约 1.0155863）、Shoulder 非均匀缩放（约 0.2959292）和左臂 IK 位移（约 0.0001422626）。整体对照报告仍为 failed，不放宽阈值、不删除用例。Shoulder 的下游接收器及 Main 的 Spline／Part 补偿仍需继续按原版核对。完整 ADV、可选分支组合、默认模型权重与界面外观均不在本记录的验收范围。Goal 保持活跃。
