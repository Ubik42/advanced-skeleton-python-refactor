# AdvancedSkeleton Python 重构工程

这是一个面向本机已授权 AdvancedSkeleton 安装的私有研究与迁移工程。长期目标是把绑定意图表达为 DCC 无关的 Python 数据与用例，再通过独立适配器落到 Maya 和 Blender。当前阶段先分析单体 MEL，并建立不会绑定到 `maya.cmds` 的最小核心合同。

## 当前完成

- 不复制或提交 AdvancedSkeleton 原始源码，仅通过命令行读取本机路径。
- 提取 MEL 顶层过程、行号、规模、参数、调用关系、全局变量和动态 `eval` 风险。
- 生成 JSON 清单和中文 Markdown 体检报告。
- 提供 DCC 无关的 `RigPlan`、预检、构建编排和构建后复检合同。
- 提供可执行的内存宿主，以及 Maya/Blender 适配器入口。
- 提供受限的 Legacy Bridge，供未来 Python 功能在 Maya 内调用尚未迁移的 MEL 过程。
- 记录目标架构、迁移顺序、验收策略和许可边界。

## 最短使用路径

```powershell
cd D:\3D\_tools\advanced-skeleton-python-refactor
py -3 -m pip install -e .
adv-migrate inventory D:\Downloads\AdvancedSkeleton\AdvancedSkeleton.mel --output reports
```

运行不依赖 Maya 的最小测试：

```powershell
py -3 -m unittest discover -s tests -v
```

输出文件默认被 Git 忽略，因为它们可能包含专有过程名、源码路径和结构信息。

## 项目边界

本工程不是 AdvancedSkeleton 的开源镜像或替代产品，不包含原始 MEL、模板、图标、场景或文档，也不应公开发布由原始源码派生的实现。使用与修改仍受本机 AdvancedSkeleton 许可协议约束。

详细设计见 [迁移架构](docs/迁移架构.md)、[跨 DCC 路线](docs/跨DCC路线.md) 与 [社区调研](docs/社区调研.md)。第一次本机扫描识别到 1,052 个顶层过程、55 个 MEL 全局变量和 151 个含动态 `eval` 的过程；完整报告留在本机 `reports/`，不进入版本库。
