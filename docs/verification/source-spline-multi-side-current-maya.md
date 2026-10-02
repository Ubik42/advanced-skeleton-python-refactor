# 多系统 Spline、镜像与独立左侧：当前 Maya 记录

## 2026-10-02 UTC 追加批次：起点体积、数量重建、两关节分支

以下为当前结果；本文后面的 23／48 是修复起点体积前的历史记录。

- 原版 MEL 84296–84344 仅跳过名为 Root 的体积起点，不能跳过每条侧边 Spline 的起点。新增 `source_start_volume`，同步接入节点清单、创建、审计、保存与重建；旧登记缺字段时保留旧图布局。诊断确认求解起点和首 IK 输出已匹配，差异来自缺失的体积权重，不是 IKfake0 父帧。
- 四系统 OPM 布局严格对照现在为 **108 Body／Part × 48 用例全部通过**，阈值仍为 `1e-4`，最大误差 `4.9029043744930334e-5`。包含三条侧链分别操作及四系统同时操作。完整构建、Skin／动画往返、保存重开、FBX、保留 Skin／动画 UUID 的重建和撤销重做通过。
- SplineTail_L、SplineSolo_L 分别完成控制器数量 3→5→3；Skin／曲线 UUID、权重、成员集合、保存重开、撤销重做、删除控制器的动画曲线保留及用户集合更新通过，其余系统数量保持不变。数量指标为原 Fit 控制数量，原版默认 2 会生成 3 个实际控制器。
- 重建归属比较按完整连接边界配对登记内外的原生 unitConversion，避免 Maya 自动编号变化误判其他 Bendy 图。扭转局部绑定帧只对有限的 16 个矩阵元素允许 `1e-10` 重组误差，并继续要求全部 TRS／shear 锁定；没有放宽原版动态对照阈值。
- 新增两 Body 关节链分支：含 Part 时按实际扩展链使用完整扭转，不含 Part 时使用原版简单扭转；两种都保留中间控制跟随。图版本 28／29 表示简单扭转加独立中间跟随，旧版本仍保留。78 Body＋19 Part 的完整构建／重建通过；SplineTwig_L 控制数量 2→4→2 的完整保留流程通过。

当前产物均在 `validation/results/`：

| 内容 | 产物 |
| --- | --- |
| 四系统最终体积修复场景／生命周期 | `biped-source-spline-start-volume/` |
| 四系统严格 48／48 | `original-spline-start-volume-pose.json` |
| 两个独立左侧数量重建 | `spline-multi-count-SplineTail_L/`、`spline-multi-count-SplineSolo_L/` |
| 两关节场景／生命周期 | `biped-source-spline-two-joint/` |
| 两关节严格对照 | `original-spline-two-joint-pose.json` |
| 简单两关节数量重建 | `spline-two-joint-count-SplineTwig_L/` |
| 传统非 OPM 对照 | `original-spline-nonopm-baseline-pose.json` |

尚未通过的核心缺口：

1. 两关节布局严格对照 44／48，四个 Main 非均匀缩放组合失败，最大 `0.2777948188515939`，集中在侧链 FK 末端；普通弯曲、扭转和伸展通过。原版末端 FKX 没有对应普通 FK 控制器，Python 多了一层补偿接收。尝试改读机制骨骼能修无 Part 的 Twig，却使有 Part 的 Stem 及三关节布局出现差异，因此该改法已撤回，最终代码不包含它；应分别还原原版末端 FKX 的真实父链，不按关节数猜接收层。
2. 传统非 OPM 四系统能构建，严格对照只有 12／48，最大 `1.420383721524784`。需完整补独立 IKScaler、Body／Part 的约束与缩放接收，不能用 OPM 通过结果代替此分支验收。
3. 标准 biped 前批严格对照仍为 46／47，left_arm_ik 的 `0.00014226263` 差异未在本批修复。

下一批优先处理上述实际场景图缺口，再推进其余原版覆盖；整体 ADV 未完成，Goal 保持活跃，不推送 GitHub。

## 前一批记录

2026-10-02 UTC，Maya 2024。原版 ADV 6.925 MEL 保持只读；本批继续修复主体图，没有推送 GitHub。

输入是原版 biped 的副本，增加 Tail 三关节链及其镜像、Solo 独立左侧三关节链。Solo 的 Fit 起点设置 noMirror；新增链分别插入 1、2 个 Inbetween。共 Spine_M、SplineTail_R、SplineTail_L、SplineSolo_L 四个系统，81 Body＋27 Part。

本批修复：

- MEL 81349–81367 的扭转模式按包含 Part 的实际求解骨链判断。镜像左侧 dForwardAxis＝1，独立 noMirror 左侧保持 0；不能只根据 `_L` 后缀选择方向。
- 来源 FK 基部保留原始绑定朝向；IKSp 与末端控制参考读取实际 Body／Part 绑定帧。逐段长度保留镜像链的负 tx。
- 多系统名称转换保留 Side／Role 枚举类型，避免 scoped plan 退化成普通字符串。
- 模式 Reverse 用锁定的 message 连接记录系统归属，避免最后一个旧约束被矩阵图替换时被 Maya 清除。旧保存图没有该属性时仍兼容原审计。
- 侧链额外 FK 基部是原控制器下的接收层，不重复应用 Fit 的缩放补偿。这修正了 Main 非均匀缩放时侧链 FK 子关节约 0.199 的位置偏差。
- 保存记录新增显式扭转模式与方向字段，严格解码，旧记录缺字段时按原图规则恢复。

最终代码的完整运行产物：

- `validation/results/biped-source-spline-multi-current/`：四系统构建／重建场景、JSON、FBX。
- `validation/results/biped-source-spline-side-current/`：标准 biped 对应产物。
- `validation/results/original-spline-multi-reference/`：未改 MEL 构建的四系统参考场景。MEL SHA256：`828e6df4b7cabef3114f766af0e938b529e4b5599e22b014aa254a9695a3db02`。
- `original-spline-multi-current-pose.json`、`original-spline-side-current-pose.json`：逐关节矩阵误差。

四系统生成 3087 个登记通道，标准 biped 为 2271 个。两者构建、局部 Skin、姿态／动画文件往返、Global 变形、保存重开及带 Skin FBX 均通过。两者均已通过保留 Skin／动画曲线 UUID 的原位重建、撤销重做和重建场景重开，运行日志末尾均为 PASS。

严格阈值维持 `1e-4`：

| 输入 | 范围 | 通过情况 | 剩余差异 |
| --- | --- | --- | --- |
| 标准 biped | 90 关节 × 47 用例 | 46／47 | left_arm_ik，约 0.00014226263 |
| 四 Spline 系统 | 108 关节 × 48 用例 | 23／48 | 三条侧链 IK 的首关节旋转，以及对应 Main 非均匀缩放组合 |

四系统的中性、普通身体操作、Spine 分支、侧链 IK 中性与非伸展，以及只切换 Spine IK 的 Main 非均匀缩放组合通过。侧链弯曲最大差异约 0.00113525，侧链 IK＋Main 非均匀缩放约 0.02102525。汇总仍为 failed，不能把通过数量当作全 ADV 完成比例。

下一项直接补侧链起点的 IKfake0／IKParentConstraint 父参考与真实求解帧，连同首输出、缩放和重建一起处理。MEL 80747–80810 中 IKfake0 接替求解链首关节；81572–81695 中首 Arc up 与首 Sp Follow 读取它。不能额外插入静止变换节点冒充此行为。该未通过改法已撤回，最终代码不包含它。多系统数量变化组合与覆盖矩阵其余缺口仍未完成，Goal 保持活跃。
