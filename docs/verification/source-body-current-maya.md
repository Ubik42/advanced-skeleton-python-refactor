# 当前 Body 主链的 Maya 运行记录

2026-10-01，Maya 2024。本批沿原版 6.925 的 Fit → Body／Part → 控制器与驱动 → Skin → 保存重开 → FBX 主链集中修复。

## 本批实现

- 普通标准 Fit 也走真实标签驱动的来源构建器，不再因为 Root／Chest 名称而进入旧固定身体模块。
- 接入原版零弯曲 RP 中间关节的世界 Z 轻移，依据 MEL 7110–7120 的起点 Y／-100；保留 makeIdentity 意外重置的 segmentScaleCompensate。
- 在来源构建中合并 Twist 与 Inbetween Part，改挂后重映射驱动路径；避免通用补偿和最后一个 Inbetween FKX 同时占用下游 FK Offset。
- 接入原版 Root／HipSwingReverse 接收矩阵名称、真实 Body 的所有权识别及变形关节最终 provenance 核对。
- 按原版启动依赖加载 quatNodes／matrixNodes；正确命名曲线 Shape、读取周期曲线的独立 CV，不访问 Maya 折叠的重复闭合 CV。
- 核对真实 DAG 连接身份；记录属于角色的自动 unitConversion，并在登记之前完成原版收尾命名。单精度常量按属性的真实存储精度比较，保持计划原值。
- 使用几何过滤器 API 读取 Skin 成员，兼容不带 legacy objectSet 的原生 Skin；FBX 成员读取使用完整角色地址。
- 原生写键在根命名空间产生的 animCurve，只在原生时间输入、全部输出属于该角色时接受；其他角色的曲线仍不接受。
- 反向脚与 RP 共用有明确所有权的 AlignIKTo，并保留 RP 的世界／nonZero／localOrient 朝向；先创建完整 footRoll 节点图再接线。
- Eye Aim 曲线明确设置 Shape 名称；校正矩阵通过 Maya MMatrix 求逆，避免创建并删除临时 DG 接收节点。

## 实际通过范围

`validation/maya_source_skeleton_one_click_smoke.py` 通过：来源骨架的一键和分步构建，默认与三段脊柱，外部源关节／网格保留，无效输入回滚，新角色 Skin，FBX，保存重开后的完整登记读回。默认样例为 24 个 Body、18 个 Part、814 个通道。

`validation/maya_original_biped_current_smoke.py` 使用只读原版 `biped.ma`，未修改参考文件。普通面板构建通过，生成 72 个 Body、18 个 Part、1582 个通道。代理网格完成 Skin，Global.translateX 在 1／5 帧由 0 到 10，顶点世界 X 同步移动 10；保存 Maya Binary、重开登记及带 Skin FBX 导出通过。运行产物位于 `validation/results/biped-current-20261001/`，包含 `.mb`、`.fbx` 和 JSON 报告。

该代理网格用于验证原生蒙皮和动画连通性，不代表复杂人体模型的权重质量、控制器全部动作、原版界面视觉或全功能验收。

## 原位重建的本批修复

重建已改用既有嵌套 Fit 导出合同。旧 Fit 缺少的可选设置仅在暂存文档补齐原版关闭默认值，源容器不被改写。暂存恢复实际 Fit 通道锁定、显示状态、旋转顺序、segmentScaleCompensate 和兄弟顺序；选择集在兼容处理之后再创建。

原先 Toes／ToesEnd、RingFinger 和 PinkyFinger 的绑定矩阵差异已经定位并修复。原版 MEL 6815–7350 在瞄准父关节时保留子关节的世界朝向；此前 Python 保存并恢复的是旧局部 jointOrient，导致子关节跟着父关节转动。现按原版保留直接子关节的世界轴与后代位置，并补 Cup、Eye、LegAim、AimAt、FreeOrient 和偏离中心的 Root 分支。真实 biped 的新旧绑定矩阵检查已通过，未放宽比较阈值。

重建同时恢复原 Fit 实际存在的 fat／fatFront／fatWidth／fatY／fatZ，保留生成的 ControlSet／DeformSet 成员；来源构建默认 DeformSet 包含实际 Part。修复暂存命名空间下 addElement 等集合目标解析，避免新角色写入旧角色集合。保留用户属性时仅排除明确列出的构建元数据，未知用户属性继续交接。FK 缩放、LegLock 和 UnTwister 根据实际连接及 AllSet 中的所属节点恢复。

蒙皮、生产变形器和用户附件的集合交接使用 Maya 原生成员操作，比较成员关系而非可重排的稀疏槽位；原生 Skin、动画曲线及权重检查继续保留。Skin 成员写入兼容传统 deformerSet 与 component tags，修改后主动求值，确保 FBX 复制立即读取到实际的局部成员。局部蒙皮两种模式的变形、撤销、保存重开及恢复完整成员检查已通过。

真实 biped 的同布局原位替换及蒙皮／动画保留已通过，记录为 `validation/results/maya2024-empty-space-rebuild-20261001.log`。普通来源角色没有旧式空间接收器时，姿态和动画文件允许空空间列表，仍严格比较 Body 姿态以及实际存在的空间。Fit 朝向独立检查全部通过，记录为 `validation/results/maya2024-fit-world-frame-20261001.json`。

本批最终扩展检查已通过：局部蒙皮、姿态／动画 JSON 往返、带 Skin FBX、原位重建、原生 Skin／角色动画曲线 UUID 保留、ControlSet／DeformSet 成员保留、暂存命名空间清理、单次撤销重做、网格动画采样，以及重建场景保存重开。结果为 `validation/results/biped-rebuild-undo-accepted-20261001/original-biped-current.json`；日志为 `validation/results/maya2024-biped-rebuild-undo-accepted-20261001.log`。该结果针对原版 biped 的同布局重建及代理网格，不扩大到主动变更控制数量、任意用户附件或完整 Face。

最后一项实际修复是撤销重做恢复：Maya 世界变换命令在重做时依赖逐步恢复中的父级，原有局部通道终值记录漏过了被锁定的通道。现对新建、没有输入连接的局部通道记录终值，临时解锁写回后恢复锁定；已有节点和驱动通道仍不被改写。严格 Spline 局部绑定矩阵复检、变形采样和重建保存重开均通过。最后静态解析 738 个 Python 源文件，姿态／重建数据的 11 项定向测试通过。

主动改变 Spline 控制数量、旧 0–1 模式显式升级、完整 Face 及覆盖矩阵其余缺口不在本次通过范围。全量 Goal 仍未完成。
