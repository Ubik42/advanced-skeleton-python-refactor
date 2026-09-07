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
- Maya FK mechanism controls 在构建前核对 Body provenance 和机制链快照，6 个控制只驱动 FK driver joints；真实姿态、Body/IK 隔离、选择保持及控制层/机制层分步 Undo 均通过。

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

& 'C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe' validation\maya_body_arm_fk_mechanisms_smoke.py validation\results\maya2024-body-arm-fk-mechanisms.json
```

正式自动化运行时应使用隐藏的独立进程、记录 PID、设置超时，并只终止本次启动的进程。结果 JSON 记录宿主版本、PID、耗时、预检和回滚结论。

## 当前限制

- 这是数据 API / standalone 验证，不包含 GUI 生命周期。
- Blender 基础约束当前只接受一个 source，且要求 `maintain_offset=False`。
- `control` 在 Maya 中是带标记属性的 transform，在 Blender 中是 Empty；曲线形状尚未进入跨 DCC 合同。
- 当前案例覆盖平移、骨骼 aim 与本地 Y-roll；非均匀缩放和镜像矩阵尚未验证。
- IK/FK 案例覆盖最小三关节 limb，不代表 twist、拉伸、镜像和无缝匹配已完成。
- 关节标签案例是 Maya-only 第一阶段切片，Blender 暂不提供对应实现。
- Fit 元数据变更目前覆盖已进入 `FitJointMetadata` 的字段；约束目标、几何附着和曲线引导等关系型属性尚未进入合同。
- Fit 层级校验尚未定义镜像配对后缀；世界位置仅作为后续规则的输入快照，不据此猜测名称。
- 容器设置用例不会创建或删除 FitSkeleton，也不会执行 pre/post ReBuild 脚本文本；容器生命周期与脚本执行策略需要独立切片。
- 容器创建只提供空的 FitSkeleton 入口；Root/Spine 需要单独调用基础模板用例，身体 limb 尚未包含。
- 当前基础模板只有 `Root → Spine1 → Spine2`，用于 Python Fit 工作流验证；不包含完整身体、左右肢体、手指或面部结构。
- 位置编辑只写本地 translate，不自动解锁、断开驱动、重算 jointOrient 或更新 Fit 可视化几何。
- 朝向编辑支持唯一子级或调用方显式选择的直接分支子级；非零 rotate 和不可补偿后代会在预检阶段拒绝。
- 对称计划表达输出名称、父子拓扑、YZ 平面世界位置及镜像行为世界轴；当前尚未覆盖非均匀缩放、World Match 或自定义逐关节镜像平面。
- 原子 Body 构建和 ReBuild 已形成一次 Undo 黄金路径；当前控制范围只到双侧 Shoulder/Elbow/Wrist FK，尚无腿/手指控制、IK、FK/IK 切换、变形系统或蒙皮，因此不是最终 Body rig。
- provenance 只证明本工程写入的产物身份和声明数量；删除资格还必须通过当前 DAG 与外部连接安全评估，不能只凭标记直接删除。
- ReBuild 已覆盖当前 Body DAG 与直接外部 DG 连接，并具备单事务失败恢复；引用场景、未知插件节点、文件保存状态和带蒙皮/附件的数据迁移仍未实现，因此这些场景继续被拒绝。
- Arm FK 约束会被 ReBuild 安全评估视为外部依赖；当前正确工作流是在一次 Undo 中移除控制系统后再 ReBuild，控制器迁移/重建编排留给后续切片。
- FK controls 已接入 FK mechanism；IK mechanism 仍处于绑定姿态，尚未创建 IK Handle、Pole Vector，也尚未把 FK/IK 双源结果混合到 Body。
