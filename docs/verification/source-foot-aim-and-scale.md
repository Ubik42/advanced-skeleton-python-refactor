# 来源 Foot 瞄准、LegAim 与末端缩放：代码接入记录

依据为只读 AdvancedSkeleton 6.925 MEL：QToes/toesAim/liftRoll（82470–82624）、LegAim 与 asBlendedMatrixAim（82628–82714、25871 起）、RP 末端缩放（82804–82838）、Pole.lock 测量来源（83008–83042）、asAlignFKIK/asSwitchFKIK 的 QToes 反向瞄准、LegAim 朝向保留及 Pole 权重（10800–11425）。没有启动 Maya，没有运行功能测试，没有推送 GitHub。

## 本次主体接入

- QToes 不再仅支持 Hybrid 分支；单段与多段均生成 toesAim（默认 10，硬范围 0–10）、移动参考目标、主 IK 位移到 Main 的矩阵、Pole 上向量、首个 Foot 子关节的 aimMatrix、局部旋转过滤及 UnOffset 控制层。使用 solver 旋转之前的起点位移，避免把 start joint 的完整世界矩阵接回 Foot 求解形成循环。
- liftRoll 默认 10，软范围 0–10；距离经 Main Y 缩放归一化、减去初始距离后，由原 Fit 末端的旋转与 jointOrientZ 决定比例和方向。保留 liftRollMin/Max 隐藏属性及原版截断。Maya 2026 使用原 asCreateMultDL 的 multDL，较旧版本使用 multDoubleLinear。
- LegAim 根据实际父关节标签创建 FKOffset 内的瞄准层：legAim 默认 10，与 IK/FK 模式相乘；保留 Z 上向量、维持偏移矩阵、旋转过滤、原生 blendMatrix 和原版测量节点。单姿态与区间切换保留 LegAim 父 FK 控制器世界朝向，并登记相应动画通道。
- 插入层级后，同步改写 FK、Foot、机制及对齐参照、Spline、Root、Main 和保存布局策略；持久图记录也随后续插入、Root Motion 或 FBX 的 Body 根改挂更新。
- RP 末端直接读取主 IK 控制器局部缩放。非 OPM 的普通 Leg 使用 Y/Z/X，普通 Arm 使用 X/Z/Y，ikLocal 与 OPM 保持 X/Y/Z；这是原版 T-pose 规则，没有另创缩放求解。历史布局按保存标记保留。
- Pole.lock 非首段读取主 IK 控制器；末段保留原 MEL 对同侧 ConstrainToLeg 的明确场景查找。FK→IK 的 Pole 权重读取实际 FKOffset.tx 与 OPM 平移绝对值较大者，继承原 asGetAttrOPM 行为；不再固定用当前关节世界距离代替。
- 非对称 Fit 用 symmetry provenance 反查真正的源关节。独立左侧的 ikLocal、Foot Pivots、Foot 图标及 liftRoll 采样不再误读右侧设置；同名系统的 _NonSymmetry 分支归入同一 RP 系统，Spline 根据实际来源侧别分别读取控制数量。
- 无 FK 控制的末端保留实际机制身份，不再因查找控制器失败阻断整个角色登记；切换时不把该机制关节当作可编辑控制器，只有现有 FK 图确实不能表示目标姿态时回滚该次转换。

## 保存与范围

角色登记升级为版本 7，保留版本 1–6 读取；来源 RP 增加 LegAim 父控制器、缩放轴向与 Pole Offset 身份。原生瞄准和缩放图使用关闭字段集合的 JSON 记录，核对节点类型、固定值、实际连接和所属系统。Maya 自动生成的单位转换也记录其真实连接与系数。

这份记录表示代码已接入主体。当前 721 个 src Python 文件通过集中 AST 语法检查，新增导入模块及计划构造参数经过静态检查；没有调用项目函数或 Maya。这些检查不能证明真实绑定结果已与原版相等。

仍需继续完成历史 Spline 控制数量变化时的图和动画迁移、覆盖矩阵中的其他 Body/Preparation 差异，以及核心代码齐备后的 Maya 整链验收。FreeOrient 的非 X 位移分量、分段 Fatness 与复杂 FK 非均匀缩放仍须逐分支对照，不把本次接入记作全量完成。
