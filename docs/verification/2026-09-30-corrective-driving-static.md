# Corrective Shapes 与 Driving Systems 静态接入记录

2026-09-30。本批没有启动 Maya，没有执行测试套件，也没有调用新写的构建、编辑、烘焙或测试动画命令；未推送 GitHub。

679 个包内 Python 文件、1030 个工程 Python 文件通过语法解析；183 个 Maya 类的 C3 继承顺序可解。组合 DrivingSystems／Corrective 宿主可解析 1129 个方法；新增宿主内部方法调用和显式关键字参数检查无缺口；新增命令均已声明角色命名空间边界。Pose 的 Corrective Shapes／Driving Systems 操作标签与实际详情组可以静态对应。末次新增修正后再次集中做语法与差异检查。

本批 Corrective 包含普通目标创建、编辑、应用、反算、镜像、过渡 SDK、SoftMod 保存恢复、退出、目录与批量烘焙；Curve-Based Deformations 包含 SkinCage／Slider 准备、九点曲线及五影响蒙皮、解绑／重绑、单轴与多轴测试动画命令、Loft／Wrap 局部网格、烘焙和清理。

Driving Systems 包含原版驱动目录、SDK 控制层、现有 SDK 写入入口、镜像、软范围、Graph、静音与退出。asDsCreate 自动创建和 asDsEdit 完整时间轴编辑／EditApply／Cancel／对称预览尚未补齐，开发计划已将其设为接下来的核心工作。

此记录仅证明静态代码接入。原生 invertShape、旧版矩阵反算、过渡 BlendShape 删除、Wrap、Slider／SkinCage 复用、单轴与多轴变形结果、Undo／Redo 和保存重开均须后续真实 Maya 验收；不能据此宣称全量复刻或行为等价已经完成。
