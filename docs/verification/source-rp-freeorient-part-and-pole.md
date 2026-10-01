# 来源 RP：FreeOrient、Part 缩放和 Pole 代码接入

依据为只读 AdvancedSkeleton 6.925 MEL：80507–80521（Body FK/IK 矩阵）、80607–80634（UnTwister）、80832–80913（Pole 与直链/之字链）、82728–82765（ScaleBlend）、82895–83048（RP 拉伸）、84370–84379（Fatness）和 10928–10942（长度匹配）。

本批贯通核心计划、主构建、Maya 宿主、保存登记和重建策略：

- 新 RP 图按原版只驱动 solver 的 tx；FreeOrient 的 ty/tz 保留原值。Lenght 乘作者 tx，Pole.lock 混入按侧别及 NonSymmetry 签名的实际距离。stretchy 和 antiPop 使用 setRange 的 0–10 → 0–1 映射。
- 两关节 RP 不再被三关节门槛丢弃，主构建、solver 扩链、动画登记和匹配均可描述无中间关节的系统。该分支的两条曲线使用线性 preInfinity，允许缩短。
- Pole 用原版长度权重基线、全骨链长度和直链局部 Y 偏移。直链设置 preferredAngleZ=-90；多关节之字链保留原版 twist=180 修正。Inbetween 重建 Handle 时保留此 twist。源分支直接使用这套定位，避免先被旧通用定位的限制拒绝。
- 每个 RP Inbetween 使用自己的 Fatness 和体积来源。非 OPM 接 Body.scale；OPM 用 ScaleCM、BodyBM、BodyMM 和实际父逆矩阵，归零本地 TRS/JO，避免 FK 世界矩阵中的缩放被重复乘入。
- UnTwister 从末端实际 FKX 取旋转，包括 Sub 和相邻 Part 的重接层。全部 Part 锚点完成后才接扭转。OPM 将加权角度插入 Part 矩阵；非 OPM 仍用 orientConstraint.offsetX。
- 原生隐式单位转换纳入生成节点身份；RP 图保存真实连接和转换系数。Root Motion 与 FBX 改挂 Body 后，同步改写 RP 锁定图记录中的 Body 输出和父逆矩阵地址。
- 新长度匹配使用 FK 主控制器位置与 tx 分母。末端 IK 定位使用实际 FKX，包含 Sub。tx 为零的 FreeOrient 可以构建和登记，但原版除法无法定义长度匹配；转换前明确拒绝该操作，不伪造长度。
- 保存标记区分新图和旧角色布局；缺少新标记的历史角色重建保留旧 Pole、位移、Part 缩放和 UnTwister 来源。

集中静态解析及构造字段检查通过；没有导入项目、运行功能测试或启动 Maya，没有推送 GitHub。以上均为“代码接入，Maya 未验收”。

仍需继续处理历史 Spline 控制数量变化的图/动画迁移、主 Body OPM 与复杂非均匀缩放的逐分支等价性，以及覆盖矩阵中的其余明确差异；不能据本批宣布全量 ADV 复刻完成。
