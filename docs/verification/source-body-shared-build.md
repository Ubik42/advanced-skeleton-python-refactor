# 来源骨架共用主体构建：2026-09-30

依据：AdvancedSkeleton 6.925 `asFBXRig` 创建并标记 Fit 后调用 `asReBuildAdvancedSkeleton`（参考 MEL 第 77469 行）。导入层不应另建 FK／简化 IK 系统。

本次代码接入：

- FBX 导入调用 `BuildRegisteredBodyCharacter` 的来源骨架分支，删除宿主原来的独立 Main、FK 和三关节 IK 创建代码。
- 来源分支复用 Body 朝向构建、通用 FK、FKX／Sub／Extra、肢体机制、RP IK、FK／IK 混合、Main、Global 跟随、Aim、缩放补偿、来源通道锁定和选择集。
- 肢体读取现有 `fit_joint_ik_info`，沿原标签查询继承起止关节、重复系统后缀及完整父链。RP 求解不再仅接受三关节；中点采用原查询的索引。本文不把 Spine／Spline 标记算为来源分支已经支持。
- FK／IK 显隐乘入原 Sub／Extra 曲线开关，保留子控制变换，No Control 曲线不重新显现。根 FK 局部缩放与 Main 比例通过共同总控计划相乘。
- FBX 动画约束、烘焙、回接原蒙皮骨架和曲线投射使用真实控制器映射；投射的原名称规则仍按原语义名称判断。
- 登记在烘焙和可选 Root Motion 改挂之后创建；允许原生时间动画曲线，保留烘焙前绑定矩阵，更新改挂后的关节路径及控制空间根。
- 非标准、缺少 Root／Chest 描述的直接 Fit 构建可以进入来源分支；已有标准躯干描述的入口保持原主体编排。

## 尚未完成的范围

来源分支不能据此等同于原版通用构建的全部功能。明确需要继续补：通用 Root／Chest 及数字标签 Spine／Spline；来源分支的 Part／Inbetween／Bendy 与相应变形驱动；新来源计划在角色重建、区间姿态匹配和动画发布中的恢复。标准角色中已有的这些实现不能作为来源分支已接通的证据。

本次没有启动 Maya，没有运行场景测试，没有推送 GitHub。静态语法和宿主方法声明核对仅说明代码结构能被解析、调用的方法已有实现，不证明 Maya 绑定运行结果。Goal 继续进行中。

静态核对：685 个源文件可解析；来源主体编排调用的 20 个宿主方法均有声明；`git diff --check` 通过。未运行 Python 功能测试或 Maya 场景。
