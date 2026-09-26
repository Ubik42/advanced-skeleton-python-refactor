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
- Maya 五指 Body 源在 Right Wrist 下建立 Thumb/Index/Middle/Ring/Pinky 各四个 Fit joints，显式选择 Middle 分支解算 Wrist 朝向；38 个源 joints 一次事务创建和朝向后，通用镜像 Body 用例生成 70 joints，其中左右手指共 40 个。五指父链、Finger 标签、YZ 镜像位置与行为朝向、重复构建拦截、选择保持，以及 Body/Fit 各自一次 Undo 均通过。
- Maya 双手 Hand FK 在 Wrist_R/L 下各建立一个零通道根，每指前三节生成 1→2→3 分层曲线控制，共 30 个 orientConstraint 输出。目标 rotate 可写/无输入预检、控制跟随指节、右 Index 真实姿态、左手隔离、重复构建拦截、ReBuild 依赖保护、选择保持和一次 Undo 后恢复安全均通过。
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
- Maya Leg Rig 在一个 Undo Chunk 内组合 mechanisms、FK controls、rotation/translation blend、Ankle/PV IK、模式显隐、双段 stretch、保持总长的 stretch bias、实时双段测距 knee pin 与双侧五级 Foot pivot；Ball pivot 驱动 Ankle IK 朝向，Toe pivot 驱动 Toes IK 朝向，真实 FK/IK/stretch/pin/roll-bank 输出、自动分段 `footRoll`、手动通道叠加、左右隔离、末阶段整体回滚和一次 Undo 清理均通过。
- Maya Character Rig 从同一份 Body/Fit 快照预演 Arm 与 Leg，在一个外层 Undo Chunk 中完成两套 limb 和统一 Global control；Global TRS 驱动 Body 与八个 limb 顶层根，正值等比 `globalScale` 同时连接九个根及 Arm/Leg 比例补偿。全局变换下 Arm/Leg stretch、Leg knee pin、选择保持、失败整体回滚和一次 Undo 完整清理均通过。
- Maya Leg FK→IK 匹配从当前弯腿 Body 姿态对齐 Ankle IK 世界帧与 Pole Vector，再切换同侧 blend；Hip/Knee/Ankle 位置、Ankle 朝向、左右隔离、显隐、选择保持和单次 Undo 均通过。
- Maya Leg FK→IK 匹配会先归零目标侧六个 Foot 通道，把 Ankle、Pole Vector 和三轴 Toe IK control 对齐到当前 Hip/Knee/Ankle/Toes FK 姿态，再切换同侧 blend；非中性 Toe FK 姿态、四关节位置与世界轴、左右隔离、显隐、选择保持和单次 Undo 均通过。
- Maya Leg IK→FK 匹配把 Hip/Knee/Ankle/Toes 四层 FK controls 依次对齐到当前 IK 姿态，并把 Hip–Knee、Knee–Ankle 的实际主轴段长传入 FK drivers 后切换同侧 blend；拉伸态四关节位置与世界轴、左右隔离、显隐、零 FK control 本地平移、选择保持和单次 Undo 均通过。
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

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_fit_skeleton_io_smoke.py validation\results\maya2024-fit-skeleton-io.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_fit_skeleton_merge_smoke.py validation\results\maya2024-fit-skeleton-merge.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_fit_skeleton_create_import_smoke.py validation\results\maya2024-fit-skeleton-create-import.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_skeleton_smoke.py validation\results\maya2024-body-skeleton.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_hand_fit_smoke.py validation\results\maya2024-body-hand-fit.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_hand_fk_controls_smoke.py validation\results\maya2024-body-hand-fk-controls.json

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

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_leg_stretch_smoke.py validation\results\maya2024-body-leg-stretch.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_leg_twist_decomposition_smoke.py validation\results\maya2024-body-leg-twist-decomposition.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_leg_volume_smoke.py validation\results\maya2024-body-leg-volume.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_leg_stretch_bias_smoke.py validation\results\maya2024-body-leg-stretch-bias.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_leg_knee_pin_smoke.py validation\results\maya2024-body-leg-knee-pin.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_character_global_smoke.py validation\results\maya2024-body-character-global.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_root_motion_smoke.py validation\results\maya2024-body-root-motion.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_root_motion_bake_smoke.py validation\results\maya2024-body-root-motion-bake.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_export_skeleton_smoke.py validation\results\maya2024-body-export-skeleton.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_export_skeleton_bake_smoke.py validation\results\maya2024-body-export-skeleton-bake.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_fbx_export_smoke.py validation\results\maya2024-body-fbx-export.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_long_mocap_fbx_smoke.py validation\results\maya2024-long-mocap-fbx.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_control_root_smoke.py validation\results\maya2024-mocap-control-root.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_control_namespace_smoke.py validation\results\maya2024-mocap-control-namespace.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_control_spine_smoke.py validation\results\maya2024-mocap-control-spine.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_control_limb_smoke.py validation\results\maya2024-mocap-control-arm.json arm

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_control_limb_smoke.py validation\results\maya2024-mocap-control-leg.json leg

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_control_four_limbs_smoke.py validation\results\maya2024-mocap-four-limbs-basic.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_control_four_limbs_smoke.py validation\results\maya2024-mocap-four-limbs-hand.json --hand

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_control_four_limbs_smoke.py validation\results\maya2024-mocap-upper-four-limbs-basic.json --upper

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_control_four_limbs_smoke.py validation\results\maya2024-mocap-upper-four-limbs-hand.json --upper --hand

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_fbx_to_character_controls_smoke.py validation\results\maya2024-fbx-to-character-controls.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_fbx_to_character_controls_smoke.py validation\results\maya2024-fbx-to-upper-character-controls.json --upper

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_full_fk_smoke.py validation\results\maya2024-mocap-full-fk-basic.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_full_fk_smoke.py validation\results\maya2024-mocap-full-fk-hand.json --hand

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_fbx_to_character_controls_smoke.py validation\results\maya2024-fbx-to-full-fk-basic.json --full

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_fbx_to_character_controls_smoke.py validation\results\maya2024-fbx-to-full-fk-hand.json --full --hand

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_full_fk_smoke.py validation\results\maya2024-mocap-full-ik-basic.json --ik

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_full_fk_smoke.py validation\results\maya2024-mocap-full-ik-hand.json --ik --hand

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_fbx_to_character_controls_smoke.py validation\results\maya2024-fbx-to-full-ik-basic.json --ik

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_fbx_to_character_controls_smoke.py validation\results\maya2024-fbx-to-full-ik-hand.json --ik --hand

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_full_fk_smoke.py validation\results\maya2024-mocap-full-body-ik-basic.json --spine-ik

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_full_fk_smoke.py validation\results\maya2024-mocap-full-body-ik-hand.json --spine-ik --hand

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_fbx_to_character_controls_smoke.py validation\results\maya2024-fbx-to-full-body-ik-basic.json --spine-ik

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_fbx_to_character_controls_smoke.py validation\results\maya2024-fbx-to-full-body-ik-hand.json --spine-ik --hand

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_variable_fk_smoke.py validation\results\maya2024-mocap-variable-fk-4.json 4

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_variable_fk_smoke.py validation\results\maya2024-mocap-variable-full-ik-1.json 1 --full-ik

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_variable_fk_smoke.py validation\results\maya2024-fbx-variable-full-ik-1.json 1 --full-ik --fbx

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_variable_fk_smoke.py validation\results\maya2024-mocap-variable-fk-4-hand.json 4 --hand

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_variable_fk_smoke.py validation\results\maya2024-mocap-variable-fk-8.json 8

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_variable_fk_smoke.py validation\results\maya2024-mocap-variable-spline-ik-4.json 4 --ik

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_variable_fk_smoke.py validation\results\maya2024-mocap-variable-spline-ik-8.json 8 --ik

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_variable_fk_smoke.py validation\results\maya2024-mocap-variable-full-ik-4.json 4 --full-ik

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_variable_fk_smoke.py validation\results\maya2024-mocap-variable-full-ik-8.json 8 --full-ik

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_variable_fk_smoke.py validation\results\maya2024-fbx-variable-full-ik-4-hand.json 4 --full-ik --hand --fbx

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_variable_fk_smoke.py validation\results\maya2024-fbx-variable-full-ik-8.json 8 --full-ik --fbx
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_variable_fk_smoke.py validation\results\maya2024-mocap-variable-scheduled-existing-fbx.json 4 --scheduled --fbx
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_variable_fk_smoke.py validation\results\maya2024-mocap-variable-scheduled-replace-fbx.json 4 --scheduled-replace --fbx
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_face_shapes_smoke.py validation\results\maya2024-face-shapes-rebuild.json
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_face_shapes_smoke.py validation\results\maya2024-face-performance.json
python validation\product_entry_smoke.py 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\results\maya2024-face-performance.ma validation\results\maya2024-product-entry.json
python validation\product_face_asset_smoke.py 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\results\maya2024-face-performance-unbuilt.ma validation\results\maya2024-product-face-asset.json
python validation\product_body_entry_smoke.py 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\results\pose30_final\character.ma validation\results\pose30_final\target.pose.json validation\results\animation30_final\animated.ma validation\results\maya2024-product-body-entry.json
python validation\architecture_boundary_audit.py validation\results\architecture-boundary.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_source_smoke.py validation\results\maya2024-mocap-source.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_mapping_smoke.py validation\results\maya2024-mocap-mapping.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_mocap_connection_smoke.py validation\results\maya2024-mocap-connection.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_character_hand_smoke.py validation\results\maya2024-body-character-hand.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_hand_pose_smoke.py validation\results\maya2024-body-hand-pose.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_hand_pose_io_smoke.py validation\results\maya2024-body-hand-pose-io.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_hand_pose_namespace_smoke.py validation\results\maya2024-body-hand-pose-namespace.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_hand_pose_keyframe_smoke.py validation\results\maya2024-body-hand-pose-keyframe.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_hand_pose_side_smoke.py validation\results\maya2024-body-hand-pose-side.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_hand_pose_mirror_smoke.py validation\results\maya2024-body-hand-pose-mirror.json

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_hand_pose_library_smoke.py validation\results\maya2024-body-hand-pose-library.json

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
- IK/FK 案例覆盖最小三关节 limb，并验证 Maya Arm/Leg 控制显隐、末端 IK 朝向、旋转/位移输出、包含 IK stretch/pin 段长传递的单侧双向匹配、Leg 上下段伸长量分配与 knee pin、每段两个轴向 twist helper，以及受 IK/FK 模式隔离的左右独立正交体积强度。完整 Character 入口已验证统一 Global TRS、等比缩放补偿、70 关节 Body 下 Hand controls 对 Arm FK/IK Wrist 的跟随，以及 Hand 聚合 curl/spread 与手动 FK 的叠加；非均匀缩放、shear、多总控空间和 World Match 尚未实现。
- Skin Bind 案例使用代码生成的 72 顶点圆柱臂段和 2 个 Lower Arm twist helpers，覆盖预演、真实变形、重复绑定拦截、选择保持和单次 Undo；不代表自动权重质量、复杂角色拓扑或已有蒙皮迁移已经完成。
- Skin Weight 案例在同类 72 顶点合成臂段上精确改写 3 个顶点，验证归一化结果、重复应用零修改、真实 twist 变形和单次 Undo 恢复原权重；尚未覆盖文件导入导出、批量网格或大规模权重性能。
- Skin Weight I/O 案例导出同一合成臂段的全部 72 个顶点，改写 3 点后由带摘要的 JSON 恢复，覆盖拒绝覆盖文件、重复导入零修改、单次 Undo 和临时目录清理；未覆盖名称重映射、网络盘或大型角色性能。
- Skin Weight Mapping 案例使用两套不同命名的 8 顶点网格、skinCluster 和 joint，通过 2 条显式 influence 双射导入 3 个变化顶点，验证源权重隔离、幂等、单次 Undo 和清理；不会自动推断 namespace 或关节对应。
- Skin Weight Mirror 案例在一个 8 顶点对称网格上使用 2 个显式顶点对和 3 条 influence 映射，覆盖中心身份映射、目标侧真实变形、源侧隔离、幂等与单次 Undo；不自动计算空间对称点。
- Skin Weight Geometry Mirror 案例读取同类 8 顶点网格的完整世界位置，自动生成 4 个严格 X 平面对称顶点对，再验证目标侧变形、源侧隔离、幂等、单次 Undo 与场景清理。该入口不支持非对称拓扑、近似最近点、拓扑映射或 influence 名称猜测。
- 关节标签案例是 Maya-only 第一阶段切片，Blender 暂不提供对应实现。
- Fit 元数据变更目前覆盖已进入 `FitJointMetadata` 的字段；约束目标、几何附着和曲线引导等关系型属性尚未进入合同。
- Fit 层级校验尚未定义镜像配对后缀；世界位置仅作为后续规则的输入快照，不据此猜测名称。
- FitSkeleton I/O schema v1 已用自行生成的 38 关节五指源验证路径无关导出、摘要复检、已有空容器导入、设置/标签/元数据/位置/行为轴恢复与一次 Undo；空场景路径还能在同一事务创建容器、六方向 Primary/Secondary enum、World Match bool、21 项设置和完整关节树。安全增量合并另从兼容的 18 关节基线只新增 20 个手指关节，并保持既有关节路径和 UUID。当前不覆盖已有轴属性或语义冲突，不改写场景 Up Axis，不重父级、不做删除式同步，也不迁移场景对象列表或 ReBuild 脚本文本。
- 容器设置用例不会创建或删除 FitSkeleton，也不会执行 pre/post ReBuild 脚本文本；容器生命周期与脚本执行策略需要独立切片。
- 容器创建只提供空的 FitSkeleton 入口；Root/Spine 需要单独调用基础模板用例，身体 limb 尚未包含。
- 最小兼容模板仍只有 `Root → Spine1 → Spine2`；全身源模板另有 18 关节基础版本和 38 关节五指版本。五指版本只定义身体与一侧可镜像手部，不包含面部、手掌变形层或控制系统。
- 位置编辑只写本地 translate，不自动解锁、断开驱动、重算 jointOrient 或更新 Fit 可视化几何。
- 朝向编辑支持唯一子级或调用方显式选择的直接分支子级；非零 rotate 和不可补偿后代会在预检阶段拒绝。
- 对称计划表达输出名称、父子拓扑、YZ 平面世界位置及镜像行为世界轴；当前尚未覆盖非均匀缩放、World Match 或自定义逐关节镜像平面。
- 原子 Body 构建和 ReBuild 已形成一次 Undo 黄金路径，并可从五指源生成 70 关节 Body；Hand 已有双侧 30 个分层 FK controls、30 个零通道 Pose 层，以及每侧全局/单指 curl 和全局 spread。Hand Pose schema v1 已验证无 Maya 路径导出、摘要复检、五个变化通道静态导入、当前帧原生 animCurve 写键、显式单侧恢复、左右镜像、重复执行零修改和单次 Undo；同一合成资产的 `RigA`/`RigB` 双引用验证还覆盖显式 namespace 解析、跨实例迁移和源实例隔离。命名预设库额外覆盖安全中文名称、原子保存、大小写冲突拒绝、规范名称查询、完整目录校验、单侧应用，以及场景 Undo 后文件仍保留。单侧与镜像只要求目标侧可写，源侧或非目标侧驱动保持不变；写键只接受未连接通道或 Maya 原生 animCurve，目标侧的约束、表达式和未知驱动会在事务前拒绝。预设重命名/删除/缩略图、动画区间 bake、切线策略和动画片段管理尚未实现。Arm 已覆盖完整 FK/IK 控制、切换、匹配、stretch、twist 与 volume，Leg 默认主流程已组合 mechanisms、FK/IK、blend、显隐、stretch bias、knee pin、twist/volume、五级 Foot pivot、自动 `footRoll` 和双向匹配。Character 入口用一个外层事务组合 Arm/Leg/Global，并在完整五指 Body 上自动纳入 Hand；30 关节 Body 保持兼容，残缺五指会被预检拒绝。自动角色发现、逐指 spread、完整变形系统或产品 UI 尚未实现。
- Root Motion 案例覆盖本工程 owned Body 的 Y-Up/Z-Up 平面位移与 yaw 实时驱动、选择保持和单次 Undo；Export Skeleton 案例覆盖 Root Motion 下完整 30 关节输出层级、实时世界姿态、来源/provenance、ReBuild 阻断与 Undo。统一 bake 案例再覆盖 Root Motion 三通道与 30×9 个 joint TRS 通道逐帧 linear keys、全部 Body 依赖移除、独立回放和 Undo 恢复；FBX 案例用显式 31-joint 选择写入临时文件，在专用临时 Undo 事务中规范发布名称并剥离内部属性，验证原场景/Undo 顶部恢复和文件摘要后拒绝覆盖发布，再由新场景回读确认无开发前缀、namespace、Fit/Body/control 或内部元数据泄漏。显式 Profile 再覆盖 FBX2018/2020、Y/Z Up、cm/m、binary/ASCII，复检 exporter 回读和文件头版本；默认保持场景轴与单位。尚未包含持久 export objectSet、曲线简化、更多线性单位、自动引擎 Profile 或游戏引擎专用骨名表。
- MoCap Source 案例只读检查调用方明确指定的 joint 根，要求连续 joint 父链、统一 namespace、唯一可移植名和直接 animation curve，并报告动画范围。当前不导入外部文件，不猜测厂商命名，不创建映射、约束、重定向或 bake。
- MoCap Mapping 案例把调用方显式 source/target 短名解析到已验证来源和 owned Body，检查一一对应、根通道、非根平移及最近映射祖先顺序。当前只生成只读计划，不创建约束、重定向或 bake，也不提供厂商自动映射。
- MoCap Connection 案例把已验证映射建立为 maintain-offset 临时约束，复检真实 source/target、输出所有权、连接瞬间姿态、跨帧驱动、显式断开与各自单次 Undo。当前不 bake、不导入文件、不提供厂商自动映射、Control Rig、UI 或 Blender 实现。
- provenance 只证明本工程写入的产物身份和声明数量；删除资格还必须通过当前 DAG 与外部连接安全评估，不能只凭标记直接删除。
- ReBuild 已覆盖当前 Body DAG 与直接外部 DG 连接，并具备单事务失败恢复；引用场景、未知插件节点、文件保存状态和带蒙皮/附件的数据迁移仍未实现，因此这些场景继续被拒绝。
- Arm FK 约束会被 ReBuild 安全评估视为外部依赖；当前正确工作流是在一次 Undo 中移除控制系统后再 ReBuild，控制器迁移/重建编排留给后续切片。
- Limb FK controls 与 RP IK controls 已通过双源 blend 输出到 Body，并完成控制显隐、含 stretch 段长传递的双向匹配、统一角色等比缩放和轴向 twist/volume helper；Hand FK controls 直接驱动 30 个 Body 指节，并具备 curl/spread 聚合属性及语义 Pose JSON 往返。Skin 已覆盖显式单网格绑定、稀疏权重写入/镜像、JSON 往返和路径映射；尚未实现动画 bake、自动 namespace/influence 推断、非对称空间配对或已有蒙皮迁移。

## MoCap 显式采样与 bake

```powershell
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' `
  validation\maya_mocap_bake_smoke.py `
  validation\results\maya2024-mocap-bake.json
```

自行生成来源与 owned Body，连接后将第 2–20 帧按步长 2 写为 18 条直接动画曲线和 180 个 linear keys。复检采样点局部值、世界姿态、完整键集合及切线；覆盖锁定/外部输出拒绝、失败回滚、单次 Undo、Redo、选择/时间恢复和删除来源后的独立回放。只保证采样点一致，不保证线性 Euler 插值在任意子帧等价于原约束；动画层、引用目标与历史依赖约束暂不支持。

## 躯干、颈头与整角色连接

```powershell
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' `
  validation\maya_body_torso_smoke.py validation\results\maya2024-body-torso.json
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' `
  validation\maya_body_torso_smoke.py validation\results\maya2024-body-torso-basic.json --basic
```

默认使用 70 关节五指 Body；`--basic` 使用 30 关节基础 Body。两者均验证 7 个 Torso FK 控制和 16 处四肢空间连接，以及 FK 传递、IK 目标保持、拉伸起点跟随、全局缩放、失败回滚与 Undo / Redo。首次初始化的 Maya 共享 IK solver 节点允许由宿主保留；角色节点和原 Body 姿态必须完整恢复。

## 脊柱 IK/FK 与双向匹配

```powershell
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' `
  validation\maya_body_spine_smoke.py validation\results\maya2024-body-spine.json
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' `
  validation\maya_body_spine_smoke.py validation\results\maya2024-body-spine-basic.json --basic
```

分别使用 70 / 30 关节自生成 Body，验证直立与弯曲姿态双向匹配、混合、独立腰部 roll、骨盆隔离、全局变换下姿态保持、非法输入拒绝、失败回滚与匹配 / 构建 Undo、Redo。运行时匹配阈值为全部 Body 世界矩阵逐元素 `1e-4`；详细误差保存在本机 JSON。


## 完整核心里程碑综合验收

在仓库根目录运行；下列文件均由代码生成场景，不读取 ADV 素材。纯 Python 回归集中运行一次，宿主脚本按相关工作批次选用。

```powershell
$env:PYTHONPATH = 'src'
py -3 -m unittest discover -s tests
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_control_curves_smoke.py validation/results/maya2024-control-curves.json
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_control_orientation_smoke.py validation/results/maya2024-control-orientation.json
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_control_world_match_hand_smoke.py validation/results/maya2024-control-world-match-hand.json
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_world_match_axis_math_smoke.py validation/results/maya2024-world-match-axis-math.json
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_complete_character_smoke.py validation/results/maya2024-complete-character.json
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_complete_character_smoke.py validation/results/maya2024-complete-character-basic.json --basic
```

综合脚本覆盖 Fit → Body → Spine / Torso / Arm / Leg / Hand / Global / 控制空间 → 显式蒙皮，核对权重和实际顶点变形。一次 Undo / Redo 必须恢复原有世界矩阵与网格位置，不能只以节点存在判断重做成功。蒙皮后注入失败必须移除整个新建角色，保留原有场景标记和选择。

外部原版示例场景可用 `maya_original_sample_inventory.py` 只读盘点：传入本机 `.ma`／`.mb` 路径和本地报告路径；脚本以 `executeScriptNodes=False` 打开场景，记录 Fit 关节、Body／控制数量和顶层层级，不改写来源文件。`sam.mb` 的本机报告显示 Y Up、厘米单位、41 个 Fit 关节、294 个总关节、141 个曲线控制 Transform 和 1 个网格。该盘点只证明原版资产结构，不代表重构框架已能直接导入或构建此资产。

`maya_original_fit_compatibility.py` 接受相同的场景与报告路径，读取原版 Fit 元数据、对称规划和 Body 预检。附加 `--isolated-build` 时，在隔离场景中移除原有 Rig、给缺失标签的 Fit 关节按名称补标签，再执行 Body 和 Character Rig 构建；`--isolated-skin` 额外保留原版网格的静态副本并绑定新的 Body；`--isolated-export` 再对控制器写 5 帧动画，构建、烘焙并发布独立骨架 FBX。三种模式只把结果保存到临时文件验证重开，不写入来源文件。`sam.mb` 的结果为 41 个 Fit → 74 个 Body，Arm／Leg／Torso／Global 和 30 个双侧 Hand FK 控制构建通过，30 个控制逐个通过驱动与 Undo。静态网格副本有 18,151 个顶点，绑定 74 个影响关节；总控平移驱动网格，Undo 与重开通过。右食指动画重开保持；发布 FBX 重导入有 75 个关节，右食指在第 1 帧与第 5 帧姿态不同。运行方式：

```powershell
$env:PYTHONPATH = 'src'
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_original_fit_compatibility.py 'C:\path\to\sam.mb' validation/results/maya2024-original-fit-compatibility.json --isolated-export
```

原版场景直接重建、原权重保留、网格随发布骨架打包及可见界面全链路仍待验。

局部机制定位使用 `maya_body_spine_smoke.py` 与 `maya_body_control_spaces_smoke.py`，输出路径作为第一个参数，`--basic` 切换为 30 关节。两者包含非法状态拒绝和失败回滚；空间脚本另外验证身体 / Global 跟随关系。结果写入已忽略的 `validation/results/`，不提交本机日志。


## 角色登记的独立进程重开验收

在仓库目录按顺序执行，两条命令各启动一个独立 Maya standalone 进程：

```powershell
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_character_registry_smoke.py validation/results/registry70 write
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_character_registry_smoke.py validation/results/registry70 read
```

30 关节案例将目录改为 `registry30`，两条命令均追加 `--basic`。write 阶段生成、登记、验证 Undo / Redo 后保存 `.ma`，read 阶段在新进程中只从场景登记恢复角色。覆盖只读解析、脊柱双向匹配、全部空间切换、输入连接污染与改名 / 损坏数据拒绝。首版仅支持完整控制组合、无 namespace、非引用的单角色。


## 全身姿态与新进程蒙皮恢复

使用新结果目录，write 阶段不会覆盖已有姿态文件；各命令在独立 Maya standalone 进程运行。

```powershell
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_character_pose_smoke.py validation/results/pose70_final write
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_character_pose_smoke.py validation/results/pose70_final read
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_character_pose_smoke.py validation/results/pose30_final write --basic
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_character_pose_smoke.py validation/results/pose30_final read --basic
```

首次运行用上述目录；再次完整运行应换新的结果目录。read 可单独复验已保存的扰动场景，它不会覆盖场景或姿态文件。

write 先捕获非中性姿态，再扰动全部登记控制与空间；read 从新进程恢复并比较完整 Body、控制、空间和网格。负例覆盖锁定、动画输入、动画层、不兼容绑定、写入异常和伪造 Body 参考。继续执行脊柱双向匹配与全部空间切换后，仍须能再次应用原姿态。旧接口兼容检查使用 `maya_body_hand_pose_io_smoke.py`。


## 全身动画与已有动画脊柱转换

使用新的结果目录；动画文件发布拒绝覆盖。先创建动画场景，再进行独立进程重开与脊柱转换：

```powershell
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_character_keyframe_smoke.py validation/results/keyframe70.json
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_character_animation_smoke.py validation/results/animation70_final write
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_character_animation_smoke.py validation/results/animation70_final read
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_character_spine_animation_smoke.py validation/results/animation70_final validation/results/spine-animation70-final.json
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_character_spine_animation_smoke.py validation/results/animation70_final validation/results/spine-animation70-final.json --reopen
```

30 关节用例将结果名中的 `70` 改为 `30`，单帧和片段脚本追加 `--basic`；脊柱脚本从已保存场景读取拓扑，无需额外参数。

单帧脚本覆盖 1 / 10 / 20 三帧、曲线归属、其他键值保留和整笔恢复。片段脚本覆盖 1–21 帧、步长 5 的五个采样，以及 0 / 30 帧已有键保留；重开后比较身体与实际蒙皮并继续编辑。脊柱脚本验证同一段动画双向转换、全部采样点世界姿态、独立求解器 Undo / Redo、共享求解器不变、失败回滚与非法外部消费拒绝。


## 四肢动画及补偿登记

先生成上节的 `animation70_final` 输入场景，再运行：

```powershell
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_character_limb_animation_smoke.py validation/results/animation70_final validation/results/limb-animation70-final.json
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_character_limb_animation_smoke.py validation/results/animation70_final validation/results/limb-animation70-final.json --reopen
```

30 关节使用相应输入目录。脚本从场景读取拓扑，无需 basic 开关。覆盖 32 个新通道、旧动画保留、登记与转换事务恢复、左右臂腿八种转换、实际蒙皮和新进程继续编辑。该批使用中性骨段长度与等比 Global 动画；动态拉伸组合的缺口见 [四肢动画开发记录](../docs/四肢动画开发记录.md)。


## 动态拉伸、体积与辅助骨骼蒙皮

输入使用四肢动画脚本保存的场景；各进程独立运行：

```powershell
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_character_stretch_matching_smoke.py validation/results/limb-animation70-final.ma validation/results/stretch-matching70
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_character_stretch_matching_smoke.py validation/results/limb-animation70-final.ma validation/results/stretch-matching70 --reopen
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_character_stretch_matching_smoke.py validation/results/limb-animation70-final.ma validation/results/stretch-matching70 --advanced
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_character_stretch_matching_smoke.py validation/results/limb-animation70-final.ma validation/results/stretch-matching70 --faults
```

默认流程建立辅助骨骼蒙皮探针，覆盖四肢上下段不同长度、双向转换、体积因子变化、撤销与回滚。reopen 重新读取场景并继续转换；advanced 使用自动拉伸、膝盖锁定、长度偏置和脚掌滚动；faults 检查外部输出、单位换算损坏及辅助骨骼错误读回。30 关节使用对应场景路径与新输出目录。
# 动画空间事件

`maya_character_space_animation_smoke.py` 使用上一批拉伸角色场景，检查头部与四肢五组来源切换、历史动画、未来事件、实际身体与辅助骨骼蒙皮、撤销重做以及版本 2 动画片段。默认模式同时加入全局平移、旋转、缩放和躯干旋转。

```powershell
& $mayapy validation/maya_character_space_animation_smoke.py validation/results/stretch-matching30-final/stretched.ma validation/results/space-animation30-final
& $mayapy validation/maya_character_space_animation_smoke.py validation/results/stretch-matching70/stretched.ma validation/results/space-animation70-final
& $mayapy validation/maya_character_space_animation_smoke.py validation/results/stretch-matching30-final/stretched.ma validation/results/space-animation30-final --reopen
& $mayapy validation/maya_character_space_animation_smoke.py validation/results/stretch-matching30-final/stretched.ma validation/results/space-animation30-final --faults
```

`--reopen` 在新进程检查保存结果，并继续切换、四肢及脊柱模式烘焙。`--faults` 检查跨空间全身写键、外部消费、非法曲线切线和写入异常回滚。输出目录中的场景与 JSON 均为忽略的运行产物，不覆盖已有受版本管理的历史结果。
## 多角色命名空间

`maya_character_namespace_smoke.py` 在同一场景生成 `hero` 的 30 关节角色与 `partner` 的 70 关节角色，检查完整构建 Undo / Redo、各自蒙皮与登记、全身动画和空间操作的角色隔离。

```powershell
& $mayapy validation/maya_character_namespace_smoke.py validation/results/namespace-character-final
& $mayapy validation/maya_character_namespace_smoke.py validation/results/namespace-character-final --reopen
& $mayapy validation/maya_character_namespace_smoke.py validation/results/namespace-character-final --verify
& $mayapy validation/maya_character_namespace_smoke.py validation/results/namespace-character-final --faults
& $mayapy validation/maya_character_namespace_smoke.py validation/results/namespace-character-final --references
```

默认模式生成 `characters.ma`；`--reopen` 给一方写入动画、空间事件和 FK/IK 转换并保存 `animated.ma`；`--verify` 在另一个进程比较保存结果，并继续操作另一角色。`--faults` 验证跨角色曲线拒绝和部分写入异常回滚。`--references` 以 `shot` 命名空间引用原场景，检查嵌套身份发现和引用节点只读边界。所有运行产物写入忽略目录。
## 重建保留快照与暂存 Rig

```powershell
& $mayapy validation/maya_character_preservation_smoke.py validation/results/namespace-character-final/animated.ma validation/results/character-preservation-final.json
& $mayapy validation/maya_character_rebuild_stage_smoke.py validation/results/namespace-character-final/animated.ma validation/results/rebuild-stage-final
& $mayapy validation/maya_character_rebuild_stage_smoke.py validation/results/namespace-character-final/animated.ma validation/results/rebuild-stage-final --faults
```

保留快照检查原生加权曲线及循环、完整稀疏蒙皮、附件属性与只读采集。暂存构建检查新 Rig 身份、绑定布局、源角色和另一角色不变、Undo / Redo；故障模式在 70 关节角色暂存扩展时注入异常，核对新 Rig 撤销和原数据完整。暂存场景为 `staged.ma`，不表示原位替换已经实现。
## 重建原生数据交接

```powershell
& $mayapy validation/maya_character_transfer_smoke.py validation/results/namespace-character-final/animated.ma validation/results/character-transfer-extended
& $mayapy validation/maya_character_transfer_smoke.py validation/results/namespace-character-final/animated.ma validation/results/character-transfer-extended --reopen
& $mayapy validation/maya_character_transfer_smoke.py validation/results/namespace-character-final/animated.ma validation/results/character-transfer70 --partner
& $mayapy validation/maya_character_transfer_smoke.py validation/results/namespace-character-final/animated.ma validation/results/character-transfer70 --partner --reopen
```

默认交接 30 关节角色，`--partner` 交接 70 关节角色。两者均加入加权曲线、循环设置、带动画与 Rig 矩阵输入的两级附件，核对保留对象身份、曲线和蒙皮内容、其他角色不变、Undo / Redo 与故障回滚。`--reopen` 比较保存场景中的身体、空间、实际网格和附件。该入口不删除旧 Rig，完整原位替换仍在开发中。
