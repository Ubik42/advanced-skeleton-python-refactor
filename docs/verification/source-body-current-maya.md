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

## 原位重建尚未通过

重建已改用既有嵌套 Fit 导出合同。旧 Fit 缺少的可选设置仅在暂存文档补齐原版关闭默认值，源容器不被改写。暂存恢复实际 Fit 通道锁定、显示状态、旋转顺序、segmentScaleCompensate 和兄弟顺序；选择集在兼容处理之后再创建。

新旧控制语义与 Body 拓扑现在一致。绑定矩阵检查仍发现 Toes／ToesEnd、RingFinger 和 PinkyFinger 的差异，最大矩阵元素差约 0.963；原位替换未获通过。此结果不能写成“重建保留蒙皮／动画成功”。下一步核对 Fit 往返与来源分支 FK／脚趾驱动的保存策略，维持现有严格检查。

主动改变 Spline 控制数量、旧 0–1 模式显式升级、完整 Face 及覆盖矩阵其余缺口不在本次通过范围。全量 Goal 仍未完成。
