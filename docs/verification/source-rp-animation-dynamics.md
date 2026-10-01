# 来源 RP 动画与原生驱动：代码接入记录

依据：AdvancedSkeleton 6.925 MEL 的 asAlignFKIK（10727–11215）、asSwitchFKIK（11216 起）、RP stretchy／antiPop／Lenght／Pole.lock（82895–83042）和 volume／Fatness（84265–84389）。原文件只读。

## 已写入主体

- SourceBodyRigPlan 保存最终 RP dynamics 计划。原生图在 Part／Inbetween solver 扩链、Foot handle 父级和 IKLocal 完成后创建；起点从真实来源父级／LegLock／内部 IKLocal 跟随，末端测量跟随真实 handle 父层。
- 抗弹跳与普通长度曲线采用原 SDK 取样点和切线；保留原版 0～10 stretchy、antiPop、Pole.lock、软范围 volume 以及 LenghtN、FatnessN 名称。伸长驱动完整 solver 链的局部位移；volume／Fatness 输出到 Body ScaleBlend，不对 solver joint 重复缩放。
- 来源 RP 匹配关系写入角色登记 v6，保留实际 FK／IK／Body／控制器／接收层／AlignIKTo。单姿态和区间转换读取保存关系，按实际标签与中点匹配，复用原生 Foot reverse Roll 和 IKHybrid 朝向顺序。
- 区间转换暂时断开直接时间动画输入以计算目标姿态，然后恢复输入；只写所选系统控制通道。保存原时间、选择与 autoKey 状态，模式阶梯写键并保留前一帧模式。
- 图数据保存在隐藏起点的锁定字符串中；登记恢复检查节点、连接、固定参数、SDK 取样值以及拉伸／体积输出。旧角色的重建策略依据已有 source.rp 通道决定是否创建 dynamics，保留旧合同。
- Root Motion 的登记重写保留所有来源 RP 与附加 Spline；FBX 完成登记前重映射实际 Body 路径。开放脚趾链的 AlignIKTo 使用实际 QToes 标记，不以倒数第二项猜测。

## 验证边界与后续

集中解析全部 Python 源文件，并检查新增数据类构造参数与差异格式；不导入或执行工程功能，不启动 Maya，不运行测试套件，不推送 GitHub。因此所有行为均标为“代码接入，Maya 未验收”。

Foot 的 toesAim／legAim 原版辅助矩阵与匹配分支仍需补齐；尚无当前场景证据支持复杂 QToes、非均匀 FK 缩放、OPM／非 OPM 与动画组合完全等价。历史 Spline 控制数量变化需要显式动画／图迁移。没有把本批局部接入视为全量 ADV 复刻完成。
