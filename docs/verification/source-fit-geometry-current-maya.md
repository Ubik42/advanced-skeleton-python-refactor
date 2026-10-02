# FitGeometry、PolyBoxes 与 BoxSkin 来源对照

2026-10-02，本批用未修改的 ADV 6.925 MEL 在 Maya 2024 图形程序生成参考，再比较 Python 入口。输入为已有原版 biped/Bendy 三段角色场景；这项验证隔离几何业务，不替代 Python Body 整体构建或默认角色外观验收。

来源段落为 `asFitGeometry` 7694–7950、Aim 分派 7254–7269、`asCreateFromFitGeometry` 56262–56391、`asCreatePolyBoxes` 56606、足底处理 56661、`asCreateBoxSkin` 57070–57190、镜像 57429。只读 MEL SHA256 保持 `828e6df4b7cabef3114f766af0e938b529e4b5599e22b014aa254a9695a3db02`。

本批恢复了原版几何生成路径：27 个 Fit 骨段的 Box/Cylinder/Sphere/Bone、实际模板骨骼、距离与分段缩放、Flare、RP/普通 Aim 和 Fit 手工朝向更新；PolyBoxes 复制真实预览，按 Body 关节存在性选择普通/Part/左右侧，沿原版 Parent Constraint 的普通或 OPM 分支跟随。Fit 编辑栏目新增显示类型、间距和更新入口，面板实际点击与排布视觉未验收。

BoxSkin 保留原版逐 Shape 缩小、逐件临时 SkinCluster、批量复制与合并、DeformSet 选择顺序、原生最大影响数 3/衰减 4/保留未用影响，以及 object-space outMesh 的最近顶点采样。中间 Shape 也参与原版缩放遍历：有两个 Shape 的盒体缩小两次，之后也按原版的 1.052632 还原两次，不能按 Transform 去重。自动补建盒体后的权重遍历使用实际生成顺序。

足跟移动保留原版当前组件选择及相对 Move，因而继承 Maya 软选择。原版参考的软选择开启、距离 5、体积衰减；对照程序记录并使用相同设置，没有修改业务算法或测试阈值。Z 场景按原版暂时切换 Group/Y、处理足底再恢复 Group/Z。由已有 Y 角色旋转出来的 Z 输入在原版也不保证最终四点世界高度为零，因此回读检查几何完整性，原版顶点比较单独严格执行。

已通过的集中验证：

- 27 个 Fit 段、39 个盒体预览、39 个圆柱的 CV，以及 53 个球体/骨骼 Mesh 的世界顶点。
- 72 个最终盒体与原版一一对应；biped 的 Y/Z 足部处理与原版逐顶点比较。
- 576 个 BoxSkin 顶点、全部影响集和 Skin 设置；所有权重差异为 0。
- Main 平移、非均匀缩放、Shoulder、Elbow、Root 五组实际动画姿态。
- 预览单次 Undo/Redo（Fit 属性、既有关节 UUID/朝向一并恢复），BoxSkin 删除 Undo/Redo，保存重开，删除旧盒体后自动补建/清理。
- GeometryActor 独立角色、当前 UnrelatedEditor 编辑空间、外部几何 UUID 保持；预览 Undo/Redo 与 BoxSkin 创建通过。

全量最大误差为 `1.9073486328125e-6`，原比较门槛仍为 `1e-4`。原版采集器为 `validation/maya_original_geometry_reference.py`，Python 对照为 `validation/maya_geometry_source_parity.py`；相应图形 Maya 启动脚本一并保留。结果位于 `validation/results/original-geometry-reference/reference.json` 与 `validation/results/geometry-source-parity/parity.json`。

这不是所有 Geometry 或整个 ADV 已完成的结论。Boolean、Warp、CutUp 的替代路径仍需恢复原版；Cylinder/Skeleton 公开最终几何入口、Ctrl 修改键分支、FitMode/PoleVector 联动及所有非标准输入未覆盖。Body 沿用此前 70/71，Sam 完整 AutoPlace、Face 其余分支和默认模型外观验收仍待完成。性能/架构优化和 Blender（Body+Face）迁移继续在 Maya 复刻确认后顺序开展。Goal 保持活跃，本批不推送 GitHub。
