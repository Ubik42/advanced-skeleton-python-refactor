# AutoPlace 七轴扫描、投影与引导生命周期：2026-10-02

本批按 ADV 6.925 只读 MEL 51771–53930 连续移植 AutoPlace 主循环和共享步骤，贯通应用、Maya 宿主以及 Body / Fit 的“自动放置／缩放”入口。生产代码不调用 ADV MEL；仅 Wrap、nCloth 和 nConstraint 使用 Maya 自带的创建命令。

## 代码接入范围

- 七阶段 z、x、yArmStraight、yElbowStraight、y、zLoft、yLoft，每阶段 100 层扫描；原版投影方向、曲线采样数、阈值、循环次数、失败退出和 Ctrl 环绕视角。
- Crotch、Root、Hip、ArmPit、Chest、Spine1、Neck、Head、Ankle、Knee、Toes 判定；踝部旋转采样、脚内外侧、脚尖与 Heel 锚点。
- 上下身及头部分离、网格壳跨越、Shoulder / Elbow Skin 与 DeltaMush 拉直、左右副本和重投影。
- 四指截面复核、指甲壳处理、指尖与指根拓扑生长、组件集合保存、nCloth 展指、Wrap、蒙皮复制与 straightenBS；拇指反向和倾斜空间采样。
- 截面 Loft、NURBS 转多边形、半侧轮廓、保留手柄偏移与枢轴旋转的投影替换。
- 全身枢轴到 Fit 的约束、手指形态与 fat、朝向更新、重新应用约束与直 Pole；保留原版 AutoPlaceSetFat 空局部 fitJoints 的行为，不擅自猜测躯干宽度。
- 完整 DeleteGuides 的手指 Wrap 还原、肩肘还原、SoftMod 反解、选择与显示恢复。已有 AutoPlacing 时，两个入口都会结束会话，不再直接拒绝。

重复手指扫描采用每指唯一的临时曲线与枢轴，避免原版重复短名导致下次查找歧义；没有改变形态检测阈值。模型准备参数来自现有 Skin / All / Right Eye 记录，写入仍有单次撤销和异常回滚。失败后的全局关节显示大小及选择约束状态恢复，不留半完成的显示偏好。

## 实际 Maya 证据

`validation/results/fit-auto-place-lifecycle/parity.json`，最终图形 Maya v4：未经修改原版的 asFitDeleteGuides 与 Python 在相同场景对照，全部 passed。

| 引导退出场景 | 49 个 Fit 关节最大矩阵差异 | Undo 最大差异 | Redo |
| --- | --- | --- | --- |
| 普通退出 | 0 | 0 | 0 |
| Shoulder / Elbow 还原 | 8.88e-16 | 3.55e-15 | 0 |
| SoftMod 清理 | 5.10e-9 | 5.33e-15 | 0 |
| 四指 straightenBS 还原 | 5.42e-8 | 7.11e-15 | 0 |

x、z、y 的 asSaveProjection 枢轴矩阵和 asGetProjectedCurveWidthMin 宽度对照差异全部为 0，重新投影及引导保存重开通过。没有将这些共享步骤的验收扩大成整套七阶段成功链的验收。

## 整套扫描尚未通过

实际使用原版提供的 `D:/3D/_tools/_DCC/MayaCraft/files/Rigged/sam/sam.mb`，提取其当前网格并去掉绑定历史，以相同几何与原版 biped Fit 运行。

- Python 后台及图形窗口均扫描到 y 手部阶段，在 zLoft 前因未识别四指形态清理退出；43 个 Fit 关节。这是“形态未识别的退出”证据，不是完整 AutoPlace 成功证据。
- 未修改原版 MEL 在同一输入的手指阶段报 `FingerCurveIndex` 名称匹配多个对象（52699 行），保留部分引导；严格全流程对照报告 failed，不能作为 Python 完整成功或等价证据。
- 记录：`validation/results/fit-auto-place-sam-source/parity.json`、`validation/results/fit-auto-place-sam-v3/smoke.json`。后者明确分类为 incomplete / not_detected，`guides=false` 表明没有完成引导创建，退出码为 1。
- 简单方块输入触发缺少 Knee 手柄或空 Elbow Skin 选择，未当成角色成功夹具；原版未对该方块取得成功参考。失败回滚最大矩阵残差约 2.60e-6，低于现有 1e-4 对照阈值，不声称精确回滚。
- nCloth 展指、拇指、两组 Loft 的完整成功输出尚无 Maya 证明；独立命名空间的完整 AutoPlace 也尚未验收。代码已接入，不能报为这些分支已通过。

下一批继续把真实角色的四指生长、展指与 Loft 成功链接通，同时保留原版在 Sam 输入上的错误证据。主体绑定严格 70／71 的前批结果未重跑，左臂 IK 残差仍未通过。整体 ADV 未完成，Goal 活跃；仅本地提交，不推送 GitHub。
