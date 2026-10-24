# AdvancedSkeleton Python 重构

按 AdvancedSkeleton 6.925 原版 MEL 重写 Maya 绑定工具。Python 可以拆分模块，绑定逻辑、节点关系、参数、权重规则和操作排布以原版为准。

**目前尚未完成全量复刻。** 标准身体绑定有完整运行基线，后续核心修改及其余功能还没有统一完成验收。当前状态只看 [工程状态](docs/工程状态.md)，开发顺序见 [开发计划](docs/开发计划.md)。旧版本检查数和早期演示不作为当前版本通过依据。

## 开发顺序

1. 完成并确认 Maya 版原版复刻，包括 Body、Face、蒙皮、动画、保存重开、重建及导出。
2. 在绑定业务行为不变的前提下，进行有实际收益的性能和架构优化。
3. 迁移到 Blender，落实原生骨骼、约束、控制、蒙皮、动画和面板。

当前仍在第一阶段，Blender 正式迁移尚未开始。

## 在 Maya 中打开

当前 Maya 宿主基线使用 Windows / Maya 2024 / Python 3.10。安装本工程后，在 Maya Script Editor 的 Python 页执行：

```python
import sys
sys.path.insert(0, r"D:\path\advanced-skeleton-python-refactor\src")
from adv_py.product.maya_panel import show_panel
show_panel()
```

把示例路径改为本机工程目录。使用本机 AdvancedSkeleton 6.925 安装中的控制器资产时，将 `ADV_6925_ICONS_FILE` 指向 `AdvancedSkeletonFiles/div/asIcons.ma`，或将其绝对路径写入 `~/.adv_py/as_icons_path.txt`。原版资产位于本机参考目录，仓库不附带原版 MEL、场景或图标。

面板按原版栏目组织。当前各操作的实现和确认程度不同，不能因按钮存在就视为完整复刻。完整默认模型外观和全部面板排布仍待确认。

## 工程组织

| 目录 | 职责 |
| --- | --- |
| `src/adv_py/core` | 数据、计算和原版规则 |
| `src/adv_py/application` | 操作流程与事务编排 |
| `src/adv_py/adapters` | Maya 场景、节点、动画和文件操作 |
| `src/adv_py/product` | 面板和命令入口 |
| `src/adv_migration` | 只读 MEL 清单分析，不负责运行绑定 |
| `tests` | 离线检查与宿主模拟 |
| `validation` | 保留的 Maya 验证脚本 |
| `local` | 忽略的本机源码、资产和临时工作 |

## 状态与证据

- [工程状态](docs/工程状态.md)：当前实现、已知差异和可信范围。
- [开发计划](docs/开发计划.md)：当前任务与收尾顺序。
- [原版操作待核对清单](docs/功能覆盖矩阵.md)：已登记的原版操作，不作为完成率。
- [原版公开功能来源](docs/原版公开功能来源.md)：原版功能参考。
- [验证入口](validation/README.md)：脚本及运行约束。

当前阶段开发已暂停。后续得到测试指令时，本任务只使用一个 Maya 实例，核实退出后继续；其他任务可以使用各自实例。生成结果写入忽略的 `validation/results/`，不跟踪进 Git。2026-10-24 的阶段更新包含尚未完成的 Face BlendShapes 对照，详细边界见 [工程状态](docs/工程状态.md)。
