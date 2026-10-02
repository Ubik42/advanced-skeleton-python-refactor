# Boolean、Warp、CutUp 与 Control Mesh 来源对照

2026-10-02，本批恢复几何派生功能的原版业务顺序。依据为只读 ADV 6.925 MEL：Boolean 56746–56898、Warp 56899–57069、CutUp 54893–54991、ControlMesh 8658–8817、ControlMeshes 8818–8980、面部控制映射 9231–9305。原版 SHA256 保持 `828e6df4b7cabef3114f766af0e938b529e4b5599e22b014aa254a9695a3db02`。

Boolean 恢复逐盒求交、世界 BlendShape 烘焙、关节局部形状转换及不保持偏移的父/缩放约束。Warp 恢复 BoxWarp 命名、先约束再细分、原版完整细分参数、收缩组件、投射、面积过滤和多材质来源采样。二者共用宿主层的角色空间、显示层、来源可见性恢复与删除边界；共用代码不改变这些绑定规则。

ControlMeshes 保留原版 `skinPercent -ignoreBelow .001` 查询与原生组件转换顺序。原版在每个顶点重新清空累计权重，因而最终主导影响来自最后一个转换顶点；本批删除此前按整面求和的错误实现，没有替原版修正算法。还恢复 FK/Part/眼球/Face/Lip/Lid/父关节映射、最后一个 Skin 历史节点、outMesh 输入、全选面 DeleteComponent 的 nodeState=1、右侧 Face 控制法线与主控制器显示开关。镜像使用原生 closestPointOnMesh 的 outMesh 与 float3 采样。

CutUp 先创建所有 Control Mesh，再收集并转移真实 Shape；组建立在 Body 关节下，按 FK 定向后转入 CutUpGeometry 并接原版保持偏移的普通或 OPM 父约束。登记的 Python FK 控制器只转换宿主身份，原版面分配、关节和命名语义保持不变。公开 Control Mesh 的结束选择恢复并入创建事务，独立命名空间操作保持外部编辑空间。

集中运行的结果：

- 未修改 MEL 在图形 Maya 2024 采集 Boolean 4 件、Warp 3 件、CutUp 2 件；四组动画与 Python 逐顶点、拓扑和材质对照通过，Python 后台与图形 Maya 执行均通过，最大误差 `9.769962616701378e-15`，门槛仍为 `1e-4`。
- Warp/CutUp 追加创建、保存重开、删除与撤销重做通过。
- 原版 Boolean 重复创建本身会因同名路径歧义失败。Python 保留该失败分支，事务回滚生成物；不将其记成追加创建成功。验证器明确要求实际异常，不能用自身断言代替异常证据。
- Control Mesh 批量、普通左右镜像、右侧 Face 成员法线、Joint 控制器左右镜像四类对照通过，检查世界顶点、拓扑、材质、实际 UV、颜色与法线数组；最大数值差异 `5.960464477539063e-8`；这不是完整 Face 绑定验收。
- Python OPM Body 现有角色接入 CutUp，通过实际登记的 Shoulder/Elbow/Head FK 身份；两件切片由 Elbow 与 ElbowPart1 驱动，肘部动画移动约 3.7583。追加四件、保存重开、删除撤销重做以及既有 Skin UUID 保持通过；公开 Control Mesh 识别登记 FK 的左右语义，两侧创建与一次撤销重做通过。
- GeometryActor 独立角色、UnrelatedEditor 当前空间、外部模型 UUID：Boolean/Warp/CutUp 创建删除与撤销重做通过；公开 Control Mesh 两侧创建、一次 Undo/Redo 与空间恢复通过。

参考采集器：`validation/maya_original_geometry_operations.py`、`validation/maya_control_mesh_source_parity.py` 的 native 模式；Python 对照：`validation/maya_geometry_operations_parity.py`、`validation/maya_python_body_cut_up.py`、`validation/maya_geometry_operations_namespace.py`。结果保存在本机 `validation/results`，不发布参考资产。

本批完成上述标准输入链，不代表整个 Maya 重构完成。多来源 Warp 的复杂材质组合、全部面部影响命名、公开面板视觉与所有非标准输入仍未覆盖。Skeleton/Muscular/Mannequin、SkinLoops 自身 CutUp 另有路径，不借本批结果扩大覆盖。Body 沿用此前 70/71，左臂 IK 尚有约 0.00014226 差异；完整 AutoPlace、Face 其余分支与默认模型完整验收继续推进。性能/架构优化与 Blender Body+Face 迁移在 Maya 忠实复刻确认后顺序执行，Goal 保持活跃，不推送 GitHub。
