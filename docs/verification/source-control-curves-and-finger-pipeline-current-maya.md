# 控制器源码复刻与四指连续阶段记录

日期：2026-10-02 UTC。原版为未修改的 ADV 6.925 MEL；本批属于 Maya Python 复刻补缺，不是性能优化或 Blender 开发。

## 实际代码改变

- 自动缩放恢复 `asProjectControlCurve` 的逐 CV 双方向射线投射、最近正向命中、999 距离上限、周期曲线 CV 数量和肩／胯／手指／胸／眼／下颌保护规则。公开入口采用当前选择，空选择不处理；删除过去的均匀尺寸估算路径。旧估算函数仅保留兼容，不作为 ADV 自动缩放执行入口。
- FBX FK 投射同样修复返回的投射曲线 transform 读取、周期 CV 数量和距离上限。
- 手动缩放恢复原版 Move 组件枢轴，支持原版的零／负缩放和 Ctrl 倒数；不再围绕控制器局部原点缩放。空输入从 ControlSet／FaceControlSet 按原版选择成员。
- 恢复 32 色调色板、自定义 RGB、线宽、XYZ 90 度旋转、原版类型与侧别选择器。所有图形操作接入面板与事务。
- 修复 Driving Systems／Pose Functions 旧栏目未映射导致整个面板创建失败的问题。
- 独立角色投射允许读取外部 Skin 网格，投射临时对象仍属于当前角色；没有放宽对外部对象写入的限制。

## 集中实际 Maya 证据

| 范围 | 结果 | 原始报告 |
| --- | --- | --- |
| 控制器投射，包括保护分支、周期曲线、变换父级、失败回滚、命名空间、空选择与无命中 | 16／16；其中 12 类 CV 与原版及 FBX helper 差异为 0 | `validation/results/control-curve-projection-source-and-fbx/projection.json` |
| 完整原版参考角色 + Sam 实际网格 | 184 控制器、609 投射点，CV 差异 0，Body 矩阵差异 7.11e-15；Skin、动画及节点身份保留；撤销重做、保存重开通过 | `validation/results/control-curve-projection-character/character.json` |
| 实际图形 Maya 的样式与手动缩放 | 11 操作通过，最大数值差异约 1.01e-12；44 类选择与原版一致；完整面板及调色控件创建通过 | `validation/results/control-curve-style-source/style.json` |
| 连通四指模型与检测→nCloth 拉直→再次扫描 | 2／2；四指曲线均识别，最大差异 4.95e-11，拉直和再次检测完整执行 | `validation/results/fit-auto-place-finger-pipeline-source/detection.json` |

完整参考角色的控制器测试验证本批曲线操作，不代表本批重新执行 Python Body 全套构建。手指夹具证明连续手部阶段，不能扩大成真实 Sam 全身 AutoPlace 成功；Sam 完整流程仍有未识别问题。Body 保持此前 70／71，本批没有重跑。

## 当前未完成与下一批

源码回查发现 `maya_one_joint_prop.py` 创建简化 Group／Rig／Main，而原版 `asOneJointProp` 创建 FitSkeleton 曲线、原版 Root 属性和 fat，执行完整 `asReBuildAdvancedSkeleton`，随后 Skin 和 Geometry 归属。应用层也错误读取用户 Smooth Bind 偏好，原版此操作明确使用 mi=3、dr=4、rui=false。这不是等价复刻，必须补完整 Root-only 构建链；不能仅调半径或以旧烟雾测试通过宣称完成。

新增只读原版参考采集入口 `validation/maya_original_one_joint_prop_reference.py`。实际图形 Maya 已取得完整参考和 `reference.mb`：场景 119 节点，控制集包含 Main、RootExtraX_M、RootX_M；变形骨骼位于 Group／DeformationSystem，Main 位于 MotionSystem／MainSystem，模型归属 Geometry。平移夹具 Root.fat=4，与原版 bboxMaxY／2 一致。这确认旧 Python 的 Group／Rig／Root_M 并不等价。先前 x=3 的夹具触发原版左侧 RootSide 校验，成功夹具按标准中线 x=0；没有修改原版校验。报告成功只证明原版参考可采集，不代表 Python 分支已修复。

后续实现应复用 `application/source_body_build.py::build_source_body_character` 的完整来源构建入口，避免再建立第二套单关节绑定图。该入口已允许无四肢来源链并处理原版 Root 图；仍须完成 Fit 创建、属性与曲线、Preparation 保存、Skin 固定选项、Geometry 归属和角色登记的一体化接入。

原版参考实际 Skin 最大影响数为 3、maintainMaxInfluences=false、normalizeWeights=1，唯一影响 Root_M；原版调用文本明确 dr=4。Maya 对该单影响 Skin 的 dropoff 查询返回 None，不能据此声称读回了 4，也不把查询不可用判成原版绑定失败；采集脚本区分源码参数与运行查询。

后续先补 One Joint Prop 完整原版链、全身 AutoPlace 成功流程及覆盖矩阵其他缺口，再冻结 Maya 行为。随后只做结果不变的性能／架构优化，最后实现 Blender 原生宿主与完整绑定框架；业务规则、默认参数、求解顺序和重建语义保持原版来源。
