# 多系统 Spline、镜像与独立左侧：当前 Maya 记录

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
