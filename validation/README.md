# 后台宿主验证

本目录使用自行生成的 `two_joint_plan()` 与 `ik_fk_limb_plan()`，不读取或复制 AdvancedSkeleton 资产。验证过程不打开 Maya/Blender UI，也不连接用户现有会话。

## 当前验证内容

- 创建两个关节和两个控制对象；
- 保持 Root -> Tip 层级与世界矩阵；
- 以非零 aim 与本地 Y-roll 验证 Maya jointOrient 和 Blender bone roll；
- 创建 parent 与 orient 两种约束；
- 再次构建同名计划时，在修改场景前由预检拦截；
- 调用宿主事务的 `rollback_last()` 后不留下节点或 Armature；
- 测试进程退出后没有新增宿主 PID 存活。
- 三关节 limb 的 FK 控制可改变末端姿态；切到 IK 后末端到达目标。
- IK/FK blend 驱动有效，并在回滚后同时清理两套 Blender Armature。
- Maya 关节标签支持标准类型与自定义文本，输入预检失败不产生部分修改，单次 Undo 可恢复。
- Maya Fit joint 元数据审计可读取常用动态属性、报告互斥配置，并保持场景未修改。
- Maya Fit joint 声明式变更支持只读预览、单事务应用、构建后复检和一次 Undo 恢复。
- Maya FitSkeleton 层级采集返回稳定的完整 DAG 快照，构建前校验可发现多根、重复短名和非 joint 中间父级，且读取不污染场景。
- Maya FitSkeleton 容器设置支持只读缺失预览、单事务增量补齐、已有值保护、构建后复检和一次 Undo 恢复；保存的 ReBuild 脚本文本不会被执行。
- Maya FitSkeleton 容器创建会跟随场景 Y/Z Up，保持当前选择，并在一个 Undo Chunk 内创建圆环和完整设置；同名节点只触发预检拒绝。
- Maya 自生成 Root/Spine 基础模板支持 Y/Z Up、显式段长、场景级重名预检、标准标签、层级复检和一次 Undo；不读取授权安装中的模板资产。
- Maya Fit joint 位置编辑支持显式批量 Patch、锁定/不可写轴预检、Root 中心约束、事务后层级复检和一次 Undo。
- Maya 简单单子链朝向支持 X-Aim/Y-Secondary、Up 平行回退、锁定预检、后代位置补偿、末端保护、幂等复检和一次 Undo。
- Maya 自生成上半身可在场景零修改时预演 14 关节层级与 11 个朝向，并用一个 Undo 完成创建、显式分支朝向和完整复检。
- Maya 全身源拓扑由 6 个中心关节、4 个 Right 臂关节和 8 个 Right 腿/足关节组成，预演 18 关节和 12 个朝向，并由一次 Undo 完整创建或移除。
- Maya 对称分析把 18 个 Fit 源关节只读展开为 6 个 `_M`、12 个 `_R` 和 12 个 `_L` 构建实例，并验证 `noMirror/noMirrorLeft` 的父链继承。
- Maya 基础 Body skeleton 把 30 个对称实例在一个 Undo Chunk 中物化为 joint DAG，并复检 side、标签、拓扑、位置、中性朝向与 Fit 源保护。
- Maya Body 朝向把源 Fit 世界轴写入 M/R joints，并为 L joints 反射 X/Y 行为轴后重建右手 Z 轴；写入后恢复全部位置，支持幂等规划和一次 Undo。
- Maya 原子 Body 构建在一个 Undo Chunk 内完成 30 joints 的物化与朝向；任一阶段失败会移除整棵新建骨架，一次 Undo 同样只移除 Body 并保留 Fit 输入。
- Maya Body provenance 在根 joint 写入并锁定 owner、产物类型、schema、Fit 来源和 joint 数量；只读审计能识别当前合同及数量不匹配，且不修改场景。
- Maya ReBuild 安全评估核对 Body joint/DAG 集合与父链，并分类读取 animation、constraint、skinCluster 和普通外部连接；计划外 attachment 或连接会阻止替换。
- Maya 原子 Body ReBuild 在删除前复核全部计划快照，只忽略旧 Body 自身造成的同名冲突；新树构建或复检失败会恢复旧树，一次 Undo 也能恢复替换前 UUID 和位置。
- Maya 双臂 FK 从当前 Body 世界帧建立 Shoulder/Elbow/Wrist 的 6 个 NURBS 控制、offset 层级和 orientConstraint；控制可改变真实关节姿态，一次 Undo 会完整移除控制系统并恢复 Body ReBuild 安全状态。
- Maya 双臂机制链从 Body 世界帧建立左右各一套 FK/IK Shoulder→Elbow→Wrist 驱动链；12 个 joint 的来源连线、零 rotate、链间独立运动、一次 Undo 和 ReBuild 安全恢复均通过。
- Maya 双腿机制链复用可变长度 limb 合同，从 Body 世界帧建立左右各一套 FK/IK Hip→Knee→Ankle→Toes→ToesEnd 驱动链；20 个 joint 的来源连线、零 rotate、链间独立运动、失败回滚、一次 Undo 和 ReBuild 安全恢复均通过。
- Maya Arm FK mechanism controls 在构建前核对 Body provenance 和机制链快照，6 个控制只驱动 Arm FK driver joints；真实姿态、Body/IK 隔离、选择保持及控制层/机制层分步 Undo 均通过。
- Maya Leg FK mechanism controls 复用可变长度控制合同，为左右 Hip/Knee/Ankle/Toes 建立 8 个 NURBS controls；零通道、FK driver 连线、Toes 真实输出、Body/IK 隔离、选择保持和两层 Undo 均通过。
- Maya 双腿 RP IK 为左右 IK mechanisms 建立 Ankle/Pole Vector controls、ikRPsolver Handle 与 Ankle 朝向约束；笔直腿备用轴、真实目标求解、Body 隔离、选择保持和分层 Undo 均通过。
- Maya Leg IK/FK 输出用左右独立属性和 reverse 节点驱动 8 个 Body 双源旋转约束及 Knee/Ankle 的 4 个位移约束；Toes FK 输出、FK/IK、0.5 权重、侧向隔离、选择保持和单次 Undo 均通过。
- Maya Leg 模式显隐在 FK=0 时只显示同侧 Hip FK 层级，在 IK=1 时只显示 Ankle/PV 层级；左右隔离、只读预演、选择保持和单次 Undo 均通过。
- Maya Leg Rig 在一个 Undo Chunk 内组合 mechanisms、FK controls、rotation/translation blend、Ankle/PV IK、模式显隐与双侧五级 Foot pivot；真实 FK/IK/roll-bank 驱动、左右隔离、Foot 末阶段整体回滚和一次 Undo 清理均通过。
- Maya Leg FK→IK 匹配从当前弯腿 Body 姿态对齐 Ankle IK 世界帧与 Pole Vector，再切换同侧 blend；Hip/Knee/Ankle 位置、Ankle 朝向、左右隔离、显隐、选择保持和单次 Undo 均通过。
- Maya Leg IK→FK 匹配把 Hip/Knee/Ankle/Toes 四层 FK controls 依次对齐到当前固定链长 IK 姿态，再切换同侧 blend；四关节位置与世界轴、左右隔离、显隐、零 FK 本地平移、选择保持和单次 Undo 均通过。FK→IK 会拒绝尚无 IK 等价表示的非中性 Toe FK 姿态。
- Maya 双臂 RP IK 创建 Wrist/Pole Vector 曲线控制、ikRPsolver Handle 与 poleVectorConstraint；可达目标求解、Body 隔离、选择保持和单次 Undo 均通过。
- Maya Arm IK/FK 输出用左右独立属性和 reverse 节点驱动 6 个 Body 双源约束；FK、IK、0.5 权重、侧向隔离、选择保持与单次 Undo 均通过。
- Maya 完整 Arm Rig 在一个 Undo Chunk 内组合 mechanisms、FK、blend 与 RP IK；后段失败整套回滚，成品一次 Undo 后 Body/Fit 保留且 ReBuild 再次安全。

## 本机命令

```powershell
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_smoke.py validation\results\maya2024.json

& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --factory-startup --python validation\blender_smoke.py -- validation\results\blender5.2.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_limb_smoke.py validation\results\maya2024-limb.json

& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --factory-startup --python-exit-code 1 --python validation\blender_limb_smoke.py -- validation\results\blender5.2-limb.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_joint_labels_smoke.py validation\results\maya2024-joint-labels.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_fit_metadata_smoke.py validation\results\maya2024-fit-metadata.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_fit_metadata_edit_smoke.py validation\results\maya2024-fit-metadata-edit.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_fit_hierarchy_smoke.py validation\results\maya2024-fit-hierarchy.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_fit_settings_smoke.py validation\results\maya2024-fit-settings.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_fit_container_smoke.py validation\results\maya2024-fit-container.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_fit_template_smoke.py validation\results\maya2024-fit-template.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_fit_position_smoke.py validation\results\maya2024-fit-position.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_fit_orientation_smoke.py validation\results\maya2024-fit-orientation.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_upper_body_fit_smoke.py validation\results\maya2024-upper-body-fit.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_fit_symmetry_smoke.py validation\results\maya2024-fit-symmetry.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_skeleton_smoke.py validation\results\maya2024-body-skeleton.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_orientation_smoke.py validation\results\maya2024-body-orientation.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_oriented_body_skeleton_smoke.py validation\results\maya2024-oriented-body-skeleton.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_provenance_smoke.py validation\results\maya2024-body-provenance.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_rebuild_safety_smoke.py validation\results\maya2024-body-rebuild-safety.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_replace_smoke.py validation\results\maya2024-body-replace.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_arm_fk_smoke.py validation\results\maya2024-body-arm-fk.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_arm_mechanisms_smoke.py validation\results\maya2024-body-arm-mechanisms.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_leg_mechanisms_smoke.py validation\results\maya2024-body-leg-mechanisms.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_leg_fk_mechanisms_smoke.py validation\results\maya2024-body-leg-fk-mechanisms.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_leg_ik_smoke.py validation\results\maya2024-body-leg-ik.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_leg_blend_smoke.py validation\results\maya2024-body-leg-blend.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_leg_visibility_smoke.py validation\results\maya2024-body-leg-visibility.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_leg_rig_smoke.py validation\results\maya2024-body-leg-rig.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_leg_fk_to_ik_smoke.py validation\results\maya2024-body-leg-fk-to-ik.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_leg_ik_to_fk_smoke.py validation\results\maya2024-body-leg-ik-to-fk.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_leg_foot_smoke.py validation\results\maya2024-body-leg-foot.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_arm_fk_mechanisms_smoke.py validation\results\maya2024-body-arm-fk-mechanisms.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_arm_ik_smoke.py validation\results\maya2024-body-arm-ik.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_arm_blend_smoke.py validation\results\maya2024-body-arm-blend.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_arm_rig_smoke.py validation\results\maya2024-body-arm-rig.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_arm_visibility_smoke.py validation\results\maya2024-body-arm-visibility.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_arm_ik_wrist_smoke.py validation\results\maya2024-body-arm-ik-wrist.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_arm_fk_to_ik_smoke.py validation\results\maya2024-body-arm-fk-to-ik.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_arm_ik_to_fk_smoke.py validation\results\maya2024-body-arm-ik-to-fk.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_arm_translation_blend_smoke.py validation\results\maya2024-body-arm-translation-blend.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_arm_stretch_smoke.py validation\results\maya2024-body-arm-stretch.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_arm_twist_smoke.py validation\results\maya2024-body-arm-twist.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_arm_twist_decomposition_smoke.py validation\results\maya2024-body-arm-twist-decomposition.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_arm_volume_smoke.py validation\results\maya2024-body-arm-volume.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_skin_bind_smoke.py validation\results\maya2024-skin-bind.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_skin_weights_smoke.py validation\results\maya2024-skin-weights.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_skin_weight_io_smoke.py validation\results\maya2024-skin-weight-io.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_skin_weight_mapping_smoke.py validation\results\maya2024-skin-weight-mapping.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_skin_weight_mirror_smoke.py validation\results\maya2024-skin-weight-mirror.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_skin_weight_geometry_smoke.py validation\results\maya2024-skin-weight-geometry.json
```

正式自动化运行时应使用隐藏的独立进程、记录 PID、设置超时，并只终止本次启动的进程。结果 JSON 记录宿主版本、PID、耗时、预检和回滚结论。

## 当前限制

- 这是数据 API / standalone 验证，不包含 GUI 生命周期。
- Blender 基础约束当前只接受一个 source，且要求 `maintain_offset=False`。
- `control` 在 Maya 中是带标记属性的 transform，在 Blender 中是 Empty；曲线形状尚未进入跨 DCC 合同。
- 当前案例覆盖平移、骨骼 aim 与本地 Y-roll；非均匀缩放和镜像矩阵尚未验证。
- IK/FK 案例覆盖最小三关节 limb，并验证 Maya 双臂控制显隐、Wrist IK 朝向、旋转/位移输出、包含 IK stretch 段长传递的单侧双向匹配、显式全局比例补偿、每段两个轴向 twist helper，以及受 IK/FK 模式隔离的左右独立体积强度；完整角色总控层级尚未实现。
- Skin Bind 案例使用代码生成的 72 顶点圆柱臂段和 2 个 Lower Arm twist helpers，覆盖预演、真实变形、重复绑定拦截、选择保持和单次 Undo；不代表自动权重质量、复杂角色拓扑或已有蒙皮迁移已经完成。
- Skin Weight 案例在同类 72 顶点合成臂段上精确改写 3 个顶点，验证归一化结果、重复应用零修改、真实 twist 变形和单次 Undo 恢复原权重；尚未覆盖文件导入导出、批量网格或大规模权重性能。
- Skin Weight I/O 案例导出同一合成臂段的全部 72 个顶点，改写 3 点后由带摘要的 JSON 恢复，覆盖拒绝覆盖文件、重复导入零修改、单次 Undo 和临时目录清理；未覆盖名称重映射、网络盘或大型角色性能。
- Skin Weight Mapping 案例使用两套不同命名的 8 顶点网格、skinCluster 和 joint，通过 2 条显式 influence 双射导入 3 个变化顶点，验证源权重隔离、幂等、单次 Undo 和清理；不会自动推断 namespace 或关节对应。
- Skin Weight Mirror 案例在一个 8 顶点对称网格上使用 2 个显式顶点对和 3 条 influence 映射，覆盖中心身份映射、目标侧真实变形、源侧隔离、幂等与单次 Undo；不自动计算空间对称点。
- Skin Weight Geometry Mirror 案例读取同类 8 顶点网格的完整世界位置，自动生成 4 个严格 X 平面对称顶点对，再验证目标侧变形、源侧隔离、幂等、单次 Undo 与场景清理。该入口不支持非对称拓扑、近似最近点、拓扑映射或 influence 名称猜测。
- 关节标签案例是 Maya-only 第一阶段切片，Blender 暂不提供对应实现。
- Fit 元数据变更目前覆盖已进入 `FitJointMetadata` 的字段；约束目标、几何附着和曲线引导等关系型属性尚未进入合同。
- Fit 层级校验尚未定义镜像配对后缀；世界位置仅作为后续规则的输入快照，不据此猜测名称。
- 容器设置用例不会创建或删除 FitSkeleton，也不会执行 pre/post ReBuild 脚本文本；容器生命周期与脚本执行策略需要独立切片。
- 容器创建只提供空的 FitSkeleton 入口；Root/Spine 需要单独调用基础模板用例，身体 limb 尚未包含。
- 当前基础模板只有 `Root → Spine1 → Spine2`，用于 Python Fit 工作流验证；不包含完整身体、左右肢体、手指或面部结构。
- 位置编辑只写本地 translate，不自动解锁、断开驱动、重算 jointOrient 或更新 Fit 可视化几何。
- 朝向编辑支持唯一子级或调用方显式选择的直接分支子级；非零 rotate 和不可补偿后代会在预检阶段拒绝。
- 对称计划表达输出名称、父子拓扑、YZ 平面世界位置及镜像行为世界轴；当前尚未覆盖非均匀缩放、World Match 或自定义逐关节镜像平面。
- 原子 Body 构建和 ReBuild 已形成一次 Undo 黄金路径；Arm 已覆盖完整 FK/IK 控制、切换、匹配、stretch、twist 与 volume，Leg 默认主流程已把五关节 mechanisms、四层 FK controls、Ankle/PV IK、含 Toes 的旋转/位移 blend、模式显隐和 Heel/Outer/Inner/Toe/Ball pivot 组合成原子 Rig；独立 Toe IK、Foot 输出朝向、自动分段 footRoll、腿部 stretch/twist、手指控制、完整变形系统或产品 UI 尚未实现，因此不是最终 Body rig。
- provenance 只证明本工程写入的产物身份和声明数量；删除资格还必须通过当前 DAG 与外部连接安全评估，不能只凭标记直接删除。
- ReBuild 已覆盖当前 Body DAG 与直接外部 DG 连接，并具备单事务失败恢复；引用场景、未知插件节点、文件保存状态和带蒙皮/附件的数据迁移仍未实现，因此这些场景继续被拒绝。
- Arm FK 约束会被 ReBuild 安全评估视为外部依赖；当前正确工作流是在一次 Undo 中移除控制系统后再 ReBuild，控制器迁移/重建编排留给后续切片。
- FK controls 与 RP IK controls 已通过双源 blend 输出到 Body，并完成控制显隐、含 stretch 段长传递的双向匹配、全局比例补偿、轴向 twist/volume helper、显式单网格 Skin Bind、稀疏顶点权重写入/镜像、JSON 往返和路径映射；尚未实现动画 bake、角色总控层级、自动 namespace/influence 推断、非对称空间配对或已有蒙皮迁移。
