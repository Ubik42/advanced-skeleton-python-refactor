# 原版 One Joint Prop 完整绑定与重建

2026-10-02 UTC。本批把旧的圆圈＋单关节约束简化实现替换为共用来源 Body 构建，接通 Preparation、Fit、RootX／Extra、Main、Geometry、登记、Skin 和保留数据重建。没有进入性能优化或 Blender 阶段。

只读依据是 ADV 6.925 的 `asOneJointProp`（77122 起）、末端 OPM 与单 Root 约束（80571–80589）、Main.height 极值规则（79475 起）。原版 MEL SHA256 仍为 `828e6df4b7cabef3114f766af0e938b529e4b5599e22b014aa254a9695a3db02`。

保留第一 Skin 世界包围盒中心、JO=(90,0,90)、fat=bboxMaxY/2、半径 3 的 Fit CV 缩放；不能把 fat 改成半高度。Skin 固定使用原版 mi=3、dr=4、rui=false，与普通 Smooth Bind 用户偏好无关。原版单 Root 没有 FKRoot，RootX 直接驱动 Root_M，ControlSet 包含三个控制，DeformSet 为空。Hi 缺失时用选中模型建立普通显示层，只把第一 Skin 的顶层 DAG 归入 Geometry。

Maya 2024 实测：

| 输入／选项 | 原版动作对照 | 保存重开／保留 Skin 与动画重建／重建撤销重做 |
| --- | --- | --- |
| 常规道具，中心 Y=5 | 9／9 | 通过 |
| OPM | 9／9 | 通过 |
| OPM＋Extra＋Sub | 9／9 | 通过 |
| 地面原点，Skin＋All 两个模型 | 9／9，两模型顶点均比较 | 通过，两套 Skin UUID 保留 |
| 中心 Y=-0.5 | 9／9 | 通过 |

45 组对照最大矩阵／曲线／顶点差异约 1.48619e-7，阈值仍为 1e-4。Fit 容器 CV 差异为零。OPM／Extra／Sub 参考使用未经修改的原版 One Joint Prop 后，再通过原版 Rebuild 设置选项；原版首次创建 Fit 的 UI 回调会重置 Preparation 选项，不能将此参考描述成首次创建保持了选项。

独立 `hero` 命名空间绑定 `model` 模型、保留外部同名临时节点、创建撤销重做，以及绑定完成／Geometry 归档完成两处主动异常后恢复全部节点身份，已运行。引用的 Skin＋All 双模型通过面板控制器入口、移动变形、创建撤销重做与保存重开。

完整来源双足角色共享重建回归通过：原 Fit UUID／CV、保留模型 Skin UUID 和登记 Body 数量一致。内部曲线蒙皮属于重新生成的控制图，不列入保留模型 Skin 身份要求。相关 Core 检查 20／20 通过，改变的 Python 文件编译与差异检查通过。新增面板四项选项传入已接代码，本批没有重新做图形窗口点击验收；不能借用旧面板截图证明新增选项。

内部重建现在单独携带 Preparation 对象记录和 Fit CV。公开便携 Fit 导出仍拒绝场景地址与脚本；本批没有放宽该合同，也没有执行记录的脚本文本。旧 Spline 登记仅枚举节点时，空原生 IK 链不再被索引越界阻断。

运行入口：`validation/maya_one_joint_prop_source_parity.py`（默认与 `--batch`）、`validation/maya_one_joint_prop_isolation.py`、`validation/maya_one_joint_prop_smoke.py`。详细报告在 `validation/results/one-joint-prop-source/`；原版参考在 `validation/results/original-one-joint-prop/`。

边界：本批没有重跑 Body 的 71 组来源对照，沿用前批 70／71；左臂 IK 约 0.00014226 仍未通过。Sam 完整 AutoPlace 成功链、真实默认角色外观和全部 Face 可选分支仍未完成。不能由道具通过推断 Maya 整体完成。后续保持先补齐 Maya 原版复刻，再做行为不变的优化，最后完整迁移 Blender。
