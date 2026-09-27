# 后台宿主验证

Preparation / Model Check：`maya_model_check_smoke.py` 构造带父级平移、非默认枢轴和构建历史的对称模型，确认报告内容、临时节点清理与场景修改标志；移动一个顶点后确认对称问题及顶点选中。公开 `sam.mb` 的 18,151 顶点 `model:body` 另经 Maya 2024 实测，变换、历史、对称问题均为 0，检查阶段约 8.8 秒。打开公开文件时禁用脚本节点执行。

```powershell
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_model_check_smoke.py
```

Preparation / Rig 引用模型：`maya_preparation_reference_smoke.py` 生成模型文件与空模型文件，检查空文件失败清理、两个独立命名空间、`Hi` 显示层、绑定场景保存重开，以及修改源模型后重新载入引用。Maya 原生文件引用不进入 Undo 队列；测试不把显示层的 Undo 误判为引用撤销。

同一用例还检查指定 `model`／`model1` 命名空间的重新加载、替换、移除：空文件替换失败后恢复原引用，保留未删除对象的 Preparation/Skin 记录，移除时清理对应记录并保留另一引用，已有 Skin 时拒绝替换和移除。`maya_preparation_reference_manage_visible.py` 在 Maya 图形窗口实际点击四个入口并保存面板截图。Maya 文件引用操作不保证 Undo，验收以失败恢复和保存重开为准。

```powershell
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_preparation_reference_smoke.py
```

Preparation / Rig 的 Skin／All／左右眼对象记录：`maya_preparation_objects_smoke.py` 从同一模型文件引用四件网格，在 Fit 创建前保存四组输入，重开后读回并重新选中；创建 FitSkeleton 后检查原版字符串属性，以及单次 Undo／Redo 和再次重开。

`maya_one_joint_prop_smoke.py` 从一件 Skin、两件 All 引用网格创建单关节道具：检查 Skin＋All 去重、FitSkeleton 原版对象字段、Root_M 与 Main、两套 Skin 的控制位移、故障回滚、Undo／Redo 和重开。`maya_one_joint_prop_visible.py` 在 Maya 图形窗口实际点击记录 Skin、记录 All 和构建入口，并保存面板截图。原版完整控制层仍需逐项对照。

`maya_face_pre_inputs_smoke.py` 在 Maya 2024 验证 Mask 面选择、原版式四条引导曲线的上下层世界范围、Face／All Head 记录、单影响 Skin、EyeBall Fit 的位置／比例、错误输入、Undo／Redo 和保存重开。`maya_face_eye_rig_smoke.py` 在已登记 Body 的 Head_M 下，以两件独立引用眼球生成全局及单侧 Aim 控制、两个 Face 辅助眼关节和两套 Skin；检查右眼独立动作不影响左眼、全局动作驱动双眼、Body 登记保持、故障回滚、Undo／Redo、保存重开及含眼球 Skin 的 FBX 重导入。`maya_face_eye_rig_visible.py` 在图形窗口点击 Face / Pre 的 Mask、Face、All Head、左右眼记录、Face / Fit 的 EyeBall，以及双眼构建入口，保存状态和截图。

`maya_face_eyelid_fit_smoke.py` 在自建 Face 网格上选择三个闭合右眼边环，Main 加选两个眼角顶点、Inner 加选一个眼角顶点，依次生成上下曲线与管面；Inner 从 Outer／Inner 边界间提取含 Main 的面片，生成隐藏区域网格与向外偏移的预览网格，保存来源面选择。用例检查断环及离环端点拒绝、面数与源网格不变、边与端点重选、Inner 单次 Undo／Redo，以及带 Skin 场景的保存重开。`maya_face_eyelid_left_smoke.py` 在同一 Face 网格的两片不等大眼圈上分别建立右侧 16 边、左侧 20 边三层 Fit；检查 `NonSym`／`NonSymSide`、左右节点隔离、左侧 Inner Undo／Redo、重开后切回右侧重选。`maya_face_eyelid_fit_visible.py` 在 Maya 图形窗口点击两侧 EyeBall、三层眼睑及非对称侧别入口，保存面板、视口和重开状态。完整头部生产拓扑尚未覆盖。

```powershell
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_preparation_objects_smoke.py
```

引用模型到完整 Body：`maya_preparation_to_skinned_body_smoke.py` 从公开 Sam 静态场景导出主体和配件为独立模型引用，记录 Preparation/Skin，再从 41 关节 Fit 构建双 Skin 角色。覆盖第二套 Skin 后故障回滚、控制器驱动网格、一次构建 Undo／Redo、保存重开、1／5 帧含网格 FBX 发布与重导入，且引用源文件哈希保持不变。

`maya_preparation_to_skinned_body_visible.py` 在 Maya 图形窗口实际点击引用模型、记录 Skin 和留空网格框的 Body 构建入口；输出面板截图、状态及重开检查到 `validation/results/preparation-visible/`。`maya_referenced_model_update_probe.py` 在临时副本上更新引用源：只移动顶点时权重读取有效；三角化一个面且顶点数不变、或细分使顶点增加后，Maya 虽保留 Skin 节点，带绑定拓扑指纹的权重读取均会拒绝沿用旧权重。旧场景没有指纹，不在此检测范围内。

`maya_referenced_skin_rebind_smoke.py` 在临时副本上先采集旧网格及权重，修改引用源拓扑，再将拆旧 Skin、重绑和表面转移作为一次撤销事务。覆盖同顶点数改面、增加 5 个顶点、零裁剪容差失败回滚、Undo／Redo、保存重开；`maya_referenced_skin_rebind_visible.py` 在 Maya 图形窗口点击导出源资产与重绑入口并保存截图。源资产必须在引用源拓扑更新前保存；未预存时不会从已失效的旧 Skin 推测权重。

```powershell
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_standard_fit_skinned_build_smoke.py 'C:\path\to\sam.mb' validation/results/maya2024-standard-fit-visible-source.mb --prepare
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_preparation_to_skinned_body_smoke.py validation/results/maya2024-standard-fit-visible-source.mb
```

四肢 `_50` 体积父节点及肘／膝 A/B 加权关节对照：先导出原版驱动导向，再分别运行以下两个用例。`_50` 用例覆盖双侧六部位共 12 个中间父节点的静止、FK 动作、来源父链核对、故障回滚和重开。肘／膝用例在同一父链上构建 8 个带 SDK 曲线的加权关节，以肘 `80°`、膝 `-110°` 对比原版动作；两者均检查撤销／重做和 Body 登记。

```powershell
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_original_volume_joint_graph.py 'C:\path\to\sam.mb' validation/results/maya2024-original-volume-joint-graph.json
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_original_volume_half_parent_smoke.py 'C:\path\to\sam.mb' validation/results/maya2024-original-volume-joint-graph.json validation/results/maya2024-original-volume-half-parent.json
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_original_bend_volume_smoke.py 'C:\path\to\sam.mb' validation/results/maya2024-original-volume-joint-graph.json validation/results/maya2024-original-bend-volume.json
```

膝部 C／D 体积关节对照：先导出原版驱动导向，再运行 `maya_original_knee_volume_smoke.py`。脚本重建四肢 `Part` 链和双侧四个膝部辅助关节，用 FK 膝控制器 `-110°` 动作比较原版世界矩阵，并检查父关节姿态预检、事务回滚、撤销／重做、保存重开和角色登记。

```powershell
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_original_volume_joint_graph.py 'C:\path\to\sam.mb' validation/results/maya2024-original-volume-joint-graph.json
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_original_knee_volume_smoke.py 'C:\path\to\sam.mb' validation/results/maya2024-original-volume-joint-graph.json validation/results/maya2024-original-knee-volume.json
```

胸部／肩胛体积关节对照：先用 `maya_original_volume_joint_graph.py` 导出本机原版驱动导向，再运行 `maya_original_chest_volume_smoke.py`。后者在相同 Fit 重建的新角色中创建双侧 `ChestAJoint` 和 `ScapulaAJoint`，比较静止及肩胛 Y／Z 轴 12° 动作的关节世界矩阵，同时检查来源骨架不匹配、故障回滚、撤销／重做、保存重开及角色登记。

```powershell
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_original_volume_joint_graph.py 'C:\path\to\sam.mb' validation/results/maya2024-original-volume-joint-graph.json
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_original_chest_volume_smoke.py 'C:\path\to\sam.mb' validation/results/maya2024-original-volume-joint-graph.json validation/results/maya2024-original-chest-volume.json
```

原版 RootA 体积关节对照：`maya_original_root_volume_smoke.py` 从公开示例场景读取左右 `RootAJoint` 的原始局部变换，在同一 Fit 重建的新角色中生成两个有权重的辅助关节。对比静止世界矩阵，验证总控位移、注入故障后的回滚、撤销／重做、保存重开及 Body 登记。`maya_original_volume_joint_graph.py` 可单独导出全部 40 个体积关节的原始驱动层级和 SDK 上游节点；输出均放在忽略目录。

```powershell
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_original_root_volume_smoke.py 'C:\path\to\sam.mb' validation/results/maya2024-original-root-volume.json
```

公开示例角色的四肢分段对照：`maya_original_limb_part_smoke.py` 读取本机 `sam.mb`，禁用脚本节点执行，比较 12 个有权重的 `Part1/Part2` 关节在静止、FK 单轴与混合旋转、FK 非等比缩放、可调扭转、全 IK 位移、Fatness 和体积保持中的结果；同时检查中途故障回滚、一次撤销／重做、保存重开和角色登记。原版 FK／IK 数值 `10` 对应本项目数值 `1`。结果写入忽略目录，不提交原资产或本机路径。

```powershell
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_original_limb_part_smoke.py 'C:\path\to\sam.mb' validation/results/maya2024-original-limb-part.json
```

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

外部原版示例场景可用 `maya_original_sample_inventory.py` 只读盘点：传入本机 `.ma`／`.mb` 路径和本地报告路径；脚本以 `executeScriptNodes=False` 打开场景，记录 Fit 关节、Body／控制数量、层级和 Skin 的每个影响关节权重质量，不改写来源文件。权重质量指该关节在所有顶点上的权重之和，用于估计名称映射丢失的影响，不代表顶点数。`sam.mb` 的本机报告显示 Y Up、厘米单位、41 个 Fit 关节、294 个总关节、141 个曲线控制 Transform 和 1 个网格。原 Skin 有 121 个影响关节，其中 68 个不在当前 74 关节 Body 的同名集合内，承载总权重质量的 41.40%。该盘点不代表重构框架已能保留原版蒙皮。

`maya_original_fit_compatibility.py` 接受相同的场景与报告路径，读取原版 Fit 元数据、对称规划和 Body 预检。附加 `--isolated-build` 时，在隔离场景中移除原有 Rig、给缺失标签的 Fit 关节按名称补标签，再执行 Body 和 Character Rig 构建；`--isolated-skin` 额外保留原版网格的静态副本并绑定新的 Body；`--isolated-export` 再对控制器写 5 帧动画，构建、烘焙并发布独立骨架 FBX。三种模式只把结果保存到临时文件验证重开，不写入来源文件。`sam.mb` 的结果为 41 个 Fit → 74 个 Body，Arm／Leg／Torso／Global 和 30 个双侧 Hand FK 控制构建通过，30 个控制逐个通过驱动与 Undo。静态网格副本有 18,151 个顶点，绑定 74 个影响关节；总控平移驱动网格，Undo 与重开通过。右食指动画重开保持；发布 FBX 重导入有 75 个关节，右食指在第 1 帧与第 5 帧姿态不同。运行方式：

```powershell
$env:PYTHONPATH = 'src'
& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation/maya_original_fit_compatibility.py 'C:\path\to\sam.mb' validation/results/maya2024-original-fit-compatibility.json --isolated-export
```

原版场景直接重建、原权重保留、网格随发布骨架打包及可见界面全链路仍待验。

`maya_original_registered_build_smoke.py` 在原版场景的未保存隔离副本中移除旧 Rig，然后通过完整角色产品用例启用“按关节名补全缺失标签”。`sam.mb` 构建并登记 74 个 Body 关节和 30 个 Hand FK 控制，Fit 标签与位置不变；单次 Undo、Redo 和保存重开通过。此脚本验证产品构建入口，来源文件保持不变。

`maya_original_fit_document_roundtrip.py` 从原版嵌套 Fit 容器兼容导出文档，在空 Maya 场景导入，比较 41 关节文档语义与 Root 高度偏移，再构建并登记 74 关节角色。单次 Undo 只移除新角色，导入的 Fit 保留；Redo 和保存重开通过。该路径避免旧 Rig 的同名节点冲突，但不携带原版网格或蒙皮。

`maya_original_skin_driver_inventory.py` 以相同的场景和报告路径参数只读清查原 Skin 中未被新 Body 同名覆盖的影响关节，记录父关节、平移／旋转／缩放输入以及约束目标和权重。`sam.mb` 中的 68 个关节全部有驱动连接；18 个分段、40 个体积、10 个手指末段辅助关节分别承载 4,729.15、2,685.66、100 的权重质量。该清查用于设计后续驱动重建，不构成蒙皮迁移验收。

`maya_original_segment_graph.py` 从原版 18 个有权重的 `Part1/Part2` 关节向上读取三层 Maya 节点连接，用于区分四肢矩阵／扭转／体积驱动与脊柱、颈部 FK／IK 约束驱动。`maya_original_mesh_roundtrip.py` 使用内部静态网格导出／导入用例，将原版网格带进 Fit 文档构建的新角色场景，核对逐顶点世界坐标和保存重开。该导入使用 Maya 文件命令，不能单次撤销；原权重尚未迁移，不能当作完整 Skin 工作流。

同一网格往返脚本还构建轴向 6 个 `Part1/Part2` 变形关节，比较原版默认位置，检查颈部控制驱动、单次 Undo／Redo、保存重开与 74 关节角色登记。辅助关节带独立标记，不进入 Body 拓扑计数；无标记额外关节仍被登记验证拒绝。原版关节朝向、缩放和动作后的网格顶点尚未对照。

`maya_original_finger_helper_inventory.py` 只读记录原版十根手指 `_00` Transform、Finger3 Body 关节和 `_50` 影响关节的层级、矩阵及驱动。`maya_original_finger_mid_smoke.py` 从原版 Fit 重建角色并生成十个 `_50` 关节，核对默认位置、控制器动作、单次 Undo／Redo、保存重开与角色登记。全身镜像轴修正后，68 个同名 Body 关节的静止世界矩阵最大分量差约 `2.2e-6`；新 Body 独有的六个足部关节另列，不纳入同名对照。十根手指 `_50` 的 12° 控制动作与原版矩阵最大分量差小于 `0.003`。该用例仍不覆盖原权重与动作后的网格顶点。

体积关节验收使用原版 `sam.mb`：先运行 `maya_original_volume_joint_graph.py`、`maya_original_angle_driver_graph.py` 和 `maya_original_axial_part_graph.py` 生成本地导向 JSON；再运行 `maya_original_angle_sampler_smoke.py`、`maya_original_angle_volume_smoke.py` 对照角度采样与 22 个关节的 FK 动作。`maya_original_all_influences_smoke.py` 依次接收场景、体积导向、角度导向、轴向导向和报告路径，同场景组装所有辅助关节，核对 Skin 的 121 个影响关节名称、40 个体积关节静止矩阵和六个轴向 Part 的 FK 姿态。脚本均以 `executeScriptNodes=False` 只读打开原版资产，结果写入 `validation/results/`；此处未迁移原权重或验证网格顶点。

`maya_original_axial_part_graph.py` 从原版场景只读记录六个轴向 Part 关节、FK／IK 中间关节、位置与朝向混合节点的世界矩阵、父链和输入连接。完整组装报告的 `axial_rest_matrix_differences` 与 `axial_extra_pose_matrix_errors` 分别核对静止和 FK 动作；后者覆盖三控制器 X／Z 单轴及组合姿态。原版动态 HipSwing、FK／IK 混合、缩放和网格顶点尚未覆盖。

`maya_original_skin_121_smoke.py` 依次接收 `sam.mb`、体积／角度／轴向导向 JSON 和报告路径。在同一场景复制原版网格并去除复制件历史，重建 121 个影响关节，按顶点和影响关节名迁移原 Skin 的全部权重。`TransferDenseSkinWeights` 使用可撤销的 Maya 命令批量写入；报告检查权重、静止顶点、UV／材质连接、整条迁移链的一次撤销／重做、保存重开，以及 Root、Neck、Spine、双髋、右肩和右肘的 16 组单轴及组合动作的顶点和关节矩阵差。运行后可用 `maya_original_skin_121_reopen.py` 在独立 Maya 进程中读取报告和生成的 `.mb`，复查 18,151 顶点、121 影响关节、权重哈希、UV、材质连接和 74 个 Body 关节登记。当前 16 组动作的逐顶点最大差为 `1.91e-6 cm`；轴向 IK／缩放、动画曲线、命名空间、引用与完整界面迁移仍待验。

`maya_original_guide_capture_smoke.py` 在当前 Maya 场景中调用产品导向采集器，与原先独立生成的体积、角度、轴向 JSON 逐项比较。`maya_original_skin_migration_smoke.py` 使用同样场景和三份导向进行错误导向预检与两处整链故障回滚，再从 `MayaPanelController.original_skin_migrate` 的自动采集入口执行成功迁移，验证关节数、静止顶点、单次撤销／重做和保存重开。面板按钮和原版式 `Body / Build` 路由由两项离屏用例检查；`maya_original_skin_migration_visible.py` 在 Maya 图形窗口中点击同一入口，支持根命名空间、普通命名空间和引用来源产生的新角色命名空间，检查迁移后自动选中目标角色并保存界面截图，并对迁移后的 Root Y 20° 网格逐顶点比较。`maya_original_skin_migration_multiskin_smoke.py` 加入一套独立引用的 Skin，检查来源选择歧义、待替换容器内引用的预检拒绝，以及无关引用在迁移、Undo／Redo、保存重开后保持原权重。`maya_original_skin_migration_related_skins_smoke.py` 为同一原版 Rig 添加第二件 8 顶点配件，检查两套 Skin 一次迁移、权重与动作结果、故障整体回滚、撤销／重做和重开。`maya_original_skin_migration_namespace_smoke.py` 将公开角色导入 `Sam` 命名空间并保存，从面板控制层的命名空间选择入口执行成功迁移，验证目标节点归属、权重、Root 动作逐顶点结果、故障回滚、单次 Undo／Redo、命名空间设置恢复与重开。`maya_referenced_skin_migration_smoke.py` 把 `sam.mb` 作为 `Sam` 引用载入，从面板控制层构建本地 `Sam_AdvPy` 副本；核对来源引用不变、121 关节原权重、Root 1／5 帧关键帧和逐顶点动作、故障回滚、单次 Undo／Redo 与重开。来源引用仍是保存场景的依赖，撤销后保留空目标命名空间供重做使用。`maya_referenced_skin_migration_related_skins_smoke.py` 在引用骨架上添加本地 8 顶点衣物 Skin，验证同 Rig 两套 Skin 一次迁移、衣物原件隐藏、各自权重与 Root 动作、故障整体回滚、Undo／Redo 和重开。`maya_original_skin_migration_animation_smoke.py` 给 Root、右肘和右髋原控制器写入时间曲线及加权固定切线，对照迁移前后的曲线和第 1／3／5／7／9 帧世界顶点，并检查未知带键控制器预检拒绝、撤销／重做及重开。

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
`maya_migrated_scene_export_smoke.py` 读取已迁移的单 Skin 与双 Skin 引用来源场景，调用面板控制层导出独立 `.mb`，重开验证无文件引用、权重和第 5 帧顶点位置、74 个 Body 登记，并确认来源场景与选择不变。
`maya_standard_fit_skinned_build_smoke.py` 从公开 `sam.mb` 只读导出 Fit 与静态网格，在空场景中用产品控制层一次构建主体和配件双 Skin；验证故障回滚、总控驱动、Undo／Redo、重开及命名空间构建。新权重由 Maya Closest Distance 生成，不是原版权重迁移。
同脚本的 `--prepare` 模式生成未构建的隔离 `.mb`，供 `maya_standard_fit_full_chain_visible.py` 在 Maya 2024 图形窗口依次点击 Body 构建、Pose 写键和 Export 发布；后者检查绑定场景重开和 FBX 重导入的 75 关节、2 套 Skin 及 RootMotion 位移。`maya_skinned_fbx_roundtrip_smoke.py` 从保存的双 Skin 动画场景发布 FBX，检查来源权重未变、18,151＋8 顶点重导入、逐影响权重差、1／5 帧采样世界点差，以及重导入骨架驱动网格变形；本机 FBX 往返最大单项权重差为 0.001884；另在第 5 帧增加左膝 FK 20° 动作，复建发布骨架后对照局部网格变形。`maya_standard_fit_skinned_build_smoke.py` 还检查 `Hero` 命名空间双 Skin 发布的无前缀骨架／网格名、顶点数、RootMotion 位移、原场景恢复和根命名空间重名拒绝；第二次发布同时启用无损线性曲线策略与 Euler Filter。`maya_fbx_republish_smoke.py` 从已发布的双 Skin 场景改键并连续发布，核对新 FBX 动作、有／无旧发布层时的导出失败回滚、单次 Undo／Redo 及额外节点与外部连接拒绝。`product_maya_adv_layout_offscreen.py` 逐入口确认被点击的栏目只显示目标参数组。
完整头部 Face Fit 验收：`maya_official_face_topology_inventory.py` 统计输入 `.mb`／`.obj` 中的网格边界环；官方 Sam 主体只有颈部两圈各 6 边边界，没有眼眶开口或独立眼球。`maya_face_head_topology_smoke.py` 接受一件头部 OBJ、一件含左右两个独立眼球 shell 的 OBJ 和报告路径；在 Maya 2024 中从头部眼区邻接面片提取左右 Outer／Main／Inner 闭环，运行 Face Pre 与 Face Fit 控制层，验证重选、Inner 撤销／重做及保存重开。本机完整三角面头部样本为 1,258 顶点、2,492 面，左右分别得到 24／21／10 边闭环、106 个眼睑区域面与 246 个预览面。FaceSetup 输入预检在 Complete 档列出缺失口鼻眉部 Fit；Skip Above+Below Eyes 档确认左右 8 个 Fit、Face Skin 和 Head 关节齐全，Include 设置撤销／重做与重开通过。眼区阶段从左右 Main／Outer 上下 Fit 曲线复制 8 条工作曲线，建立 82 个分段关节与 8 个控制器，为 150 个顶点写入原 Skin；关节静止点与对应 Fit 曲线点误差为 0。右 Main 上、左 Main 下和右 Outer 上控制各移动 0.05 cm 后，工作曲线中段控制点随动，目标侧网格最大位移 0.040786／0.034260／0.015129 cm，对侧不动；控制归零后工作曲线与网格复位。权重写入后故障注入恢复原 Skin，单次 Undo／Redo、第 1／5 帧写键与保存重开通过。`product_maya_panel_offscreen.py` 验证 Include、输入检查和眼睑构建的面板派发。输入样本不随公开工程分发；可替换为符合相同输入条件的本地 OBJ。同一脚本还验证左右 `ctrlEye` 的 0–10 眨眼、Main 中央开口从 0.083310／0.083436 cm 收到 0.003192／0.002979 cm、双侧网格位移 0.049919／0.049908 cm、对侧隔离、复位以及左眼 blink 动画保存重开。脚本先建立独立双眼 Aim、关节和 Skin；没有这一步时，眼睑构建在写入前拒绝。右眼 Aim 上移 0.1 cm 使眼球关节旋转 -12.070724°，Main 上弧工作曲线移动 0.017240 cm，右侧网格最大移动 0.014063 cm，左侧不动；水平 Aim 移动 0.1 cm 时右眼关节旋转 31.552040°，曲线 X 位移 0.045065 cm；fleshy=0 和 blink=10 均使纵向跟随归零，眼球控制与眼睑动画保存重开通过。同脚本末尾传入 `symmetric` 时只建立右侧 Fit，再调用面板同一路由把右侧 55 个环顶点映到左侧真实顶点和边；最大镜像距离 0.009195 cm，小于 0.011691 cm 容差。左侧 EyeBall、三层眼睑和区域网格一次镜像事务创建，Undo／Redo 后继续建立 82 个眼睑关节并验证动作、保存重开；`symmetric-auto` 模式只保留右侧 Fit，先建立双眼控制，再点击眼睑构建；构建按钮自动镜像左侧 Fit 并写入 82 个关节和 Skin。权重写入后故障注入、单次 Undo／Redo 均同时回滚／恢复镜像 Fit 与绑定，动画保存重开通过。普通模式仍用左右独立 Fit。此样本没有眼眶开口，不验证眼睑解剖位置或原版闭合形态；当前构建仍不代表完整 FaceSetup。

真实眼孔样本：`maya_official_face_topology_inventory.py` 还可只读导入 FBX 检查网格边界。`maya_face_asset_extract_obj.py` 从本机 Adam FBX 提取静态面罩和左右巩膜到忽略的测试目录；面罩 3,052 顶点、6,028 面，左右各有一条 16 边眼孔。`maya_face_head_topology_smoke.py` 检测眼孔边界并向外选取独立 Main／Outer 环；两侧分别得到 Inner／Main／Outer 16／17／17 边、各 67 个眼睑区域面，眼区构建得到 88 个关节、160 个加权顶点。双侧闭合、眼球跟随、单侧隔离、故障回滚、Undo／Redo 和动画保存重开在 Maya 2024 通过。临时 OBJ 与 FBX 原件不进入仓库。该面罩不满足对称镜像容差，使用非对称双侧 Fit；它不代表完整头部或原版视觉形态验收。

同一 Adam 面罩可用 `complex-skin` 模式运行 `maya_face_head_topology_smoke.py`：场景增加一套独立配件 Skin，Face Skin 增加一名受外部 `multiplyDivide` 节点驱动的影响关节。用例对照配件逐权重快照与外部连接，覆盖眼睑写权重故障回滚、成功构建、Undo／Redo 和保存重开；重开后修改驱动输入，Face 网格目标顶点 Y 位移 0.049988 cm。该模式不验证多级约束或动画层。

完整头部眼孔样本：本机 Chal 头部有 4,255 顶点、4,301 面和两条各 24 边的眼孔。`maya_face_asset_extract_obj.py` 可从只读 FBX 提取头部与双眼静态 OBJ；源资产不入仓库。`maya_face_head_topology_smoke.py` 的第五个参数可将绑定完成、尚未写入测试动画的中性 Maya 场景复制到指定路径。`maya_face_aperture_closure_audit.py` 从此场景读取真正的 Inner 孔边界，比较每侧横向 5%～95% 的 19 个位置在张眼与 blink=10 时的上下孔沿间距；当前右侧最大剩余比例 0.020565，左侧 0.034457。检查会先把两侧 blink 归零，避免前一侧的闭眼状态污染后一侧。`maya_face_pose_snapshot_obj.py` 将 Maya 评估后的头部和左右眼球分别写为张眼／闭眼 OBJ，`maya_face_pose_snapshot_visible.py` 在图形 Maya 中重载并生成 PNG。`maya_face_eye_occlusion_audit.py` 从正面向头部和眼球投射 91 条采样射线，比较最近交点的深度；当前张眼时两侧各 61 个点可见眼球，闭眼后右侧仍有 37 个、左侧 38 个，故验收失败。孔沿间距通过不能代替眼球遮挡验收。临时 OBJ、场景、报告与 PNG 均放在忽略的 `validation/results/` 下。
