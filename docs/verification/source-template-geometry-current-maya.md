# Skeleton、Muscular 与 Mannequin 来源生成链

2026-10-02，按未修改 ADV 6.925 MEL 恢复三条原版模板几何业务链。依据：asRlaChild 26125、asGetAxis 26208、asgetCharHeight 55630、asSetOrientOffsetFromAxis 55655、asCreateSkeleton 55677–56253、asCreateMuscular 56381–56597、asCreateMannequin 57198–57410、asMirrorGeometry 57429。原版 SHA256 保持 `828e6df4b7cabef3114f766af0e938b529e4b5599e22b014aa254a9695a3db02`。

Mannequin 使用 Main.height、原生 DeformSet 顺序及 asRlaChild 的中心与优先子关节判定。恢复腕部 MiddleFinger1、足跟标签/0.87 系数、原生临时 Parent/Aim 定向、左侧肢体负缩放和法线、所有 Finger 名称尺寸判定，以及固定 Skin 参数。原版 Delete 保留 shaderMannequin/SG；此前错误删除材质的实现已纠正。导入模板先进入创建事务，再建立结果，清理只删除原始导入节点 UUID，复制的 Shape 保留。

Skeleton 恢复具名骨形按实际 Body 关节存在性选择，指骨/掌骨/Generic 按 DeformSet 顺序创建。Generic 通过已连接 BoneSC 判断是否已被来源蒙皮覆盖，避免为 Part 再造骨形。脊柱 Skin 沿 Head 父链收集到 Root，包含真实 Part；恢复 Carpal、足掌父影响、原版足跟前置判定、模板专用替换和轴向参数。

本批纠正三个会阻止完整运行的遗留问题：继承的 `_influences` 属性遮住同名方法，改为 `_bone_influences`；Scapula BlendShape 只传原版 Mesh Shape，避免辅助层级不匹配；SoftMod/晶格只处理 Mesh Shape，保留辅助定位曲线。胸部 SoftMod 保留原版枢轴和 Root→Head 的半径。使用 Maya 节点删除回调只读观察原版 SoftMod，定位了缺少枢轴设置的差异，没有重写或替换原版过程。

Muscular 顺序为导入→建立 Wrap→匹配骨形的世界 BlendShape→ExternalOblique 特例→删除 Wrap 保留 CV→逐影响逐 CV 的 SkinPercent 写入→镜像/Loft→删除模板 Root。此前先匹配骨形再创建 Wrap 会丢失基准形态，现已纠正。影响映射可回退到存在的 Body Root，而非限制在 Skeleton 的骨形列表。保留逐次规范化写入，不将重复映射的权重改成聚合求和。对侧曲线先按原版解锁，保留原生 copySkinWeights 和 Loft reverse；Delete 只删除原版四个组/层，撤销此前依赖历史名称清单广泛删除的做法。

集中验证结果：

- Mannequin：102 件，普通/另一组 Main 轴/既有材质三类输入，五组动画；世界顶点、拓扑、影响、全部权重、Skin 设置和材质对照通过，最大差异 `1.9721522630525295e-31`。
- Skeleton：73 件骨形、五组动画；另加无 fat、只有 fatFront、只有 fatWidth 的三个自定义关节，共 76 件。保留源码比例变量的继承规则，以及 Pelvis 对所有 Root 右侧子关节依次处理。双向镜像含目标 scaleX 锁定分支通过；最大差异 `1.4876988529977098e-14`。
- Muscular：103 条来源曲线、20 组对侧肌肉，曲线/Loft CV、影响顺序、全部权重及四组动画通过；最大差异 `1.5091103477971e-8`。这项来源对照从原版 Skeleton 场景起步，Python 全链接入另行验证。
- 三者保存重开、删除撤销重做通过；Mannequin 材质保留与原版一致。所有对照门槛保持 `1e-4`。
- Python OPM 身体角色全链：114 件 Mannequin、88 件 Skeleton、103 条肌肉曲线/20 组镜像；实际肘部动画驱动 Ulna，既有 Skin UUID 保留、保存重开与删除撤销重做通过。
- GeometryActor 独立角色与 UnrelatedEditor 当前空间：三条完整生成链、删除/撤销/重做、外部模型 UUID 和编辑空间保持通过。
- 图形 Maya 的真实面板中，展开 Body 的对应 Geometry 栏目，通过鼠标事件点击三类 Create/Delete 按钮；生成 102/73/103+20，撤销重做通过。截图保存在本机 `validation/results/template-geometry-panel/panel.png`。这不是整个 ADV 面板视觉一致的结论。

采集器为 `validation/maya_original_mannequin_reference.py`、`validation/maya_original_skeleton_geometry_reference.py`、`validation/maya_original_muscular_reference.py`；对照为 `validation/maya_template_geometry_parity.py`、`validation/maya_muscular_parity.py`；接入与面板验证为 `validation/maya_python_body_template_geometry.py`、`validation/maya_template_geometry_panel.py`。结果和 Maya 场景留在本机 `validation/results`，不发布原版资产。

整体复刻仍未完成。马/猫骨形、FaceJoint 下颌 Cluster、全部自定义轴/非标准模板组合等分支没有借标准角色结果宣称验收。本批修改马/猫对应静态选择与替换规则，真实模板运行仍待开展。Body 沿用此前 70/71；完整 AutoPlace、Face 其余分支和默认模型整体展示仍需推进。顺序保持：完成 Maya 忠实复刻→不改变绑定业务的性能/架构优化→Blender Body+Face。Goal 活跃，不推送 GitHub。
