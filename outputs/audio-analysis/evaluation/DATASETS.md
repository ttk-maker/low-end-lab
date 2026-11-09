# 数据集评测操作说明（Windows PowerShell）

此工具独立于网页生产项目；不会写入 `audio-analysis/data/`，不会调用 Qwen，不会训练模型。完整接入与结果说明见 `outputs/20-数据集接入与训练资源评估.md`。

从本项目根目录运行：

```powershell
# 先进入你克隆或保存项目的根目录。
$evalPython = '.\work\audio-env\Scripts\python.exe'
if (-not (Test-Path $evalPython)) {
    $evalPython = '.\outputs\audio-analysis\.venv\Scripts\python.exe'
}

# 已安装的新增依赖；不需要重复安装或升级生产依赖。
# 新电脑先安装主程序，再执行：
# & $evalPython -m pip install -r outputs/audio-analysis/evaluation/requirements.txt

# 重新取得/验证数据并导入；已有数据会复用。
& $evalPython outputs/audio-analysis/evaluation/prepare_datasets.py

# 适配器测试。
& $evalPython outputs/audio-analysis/evaluation/test_dataset_adapters.py

# 诊断集评测。POP909 自动按需生成音频，首次运行较慢。
& $evalPython outputs/audio-analysis/evaluation/run_datasets.py gtzan --task rhythm --limit 10
& $evalPython outputs/audio-analysis/evaluation/run_datasets.py guitarset --task chord --limit 10
& $evalPython outputs/audio-analysis/evaluation/run_datasets.py pop909 --task rhythm --limit 4
& $evalPython outputs/audio-analysis/evaluation/run_datasets.py pop909 --task chord --limit 3

# 更新汇总与保留检查。
& $evalPython outputs/audio-analysis/evaluation/summarize_datasets.py
```

`--limit 0` 表示选定分组的全部可用条目。默认只跑 `diagnostic`。诊断报告逐曲落盘，并保存预先选定的 ID；进程中断时可查看已经完成的条目。目前重跑同一数据集/任务会重新推理并覆盖同名汇总，因此重要基线应先复制存档。GuitarSet 在首轮后加强了跨速度/调性模板隔离，首轮选择 ID 以已经保存的报告为准，重新执行的 10 条选择可能不同。

只有版本与开发集参数锁定后，才使用 `--split frozen_test` 运行正式留出评测，例如：

```powershell
& $evalPython outputs/audio-analysis/evaluation/run_datasets.py gtzan --task rhythm --split frozen_test --limit 0
```

报告路径：`outputs/audio-analysis/evaluation/dataset-import-2026-11-09/`。源文件/模型输出缓存路径：`work/evaluation-datasets/`。清单的相对路径以清单所在目录为基准；整项目移动时请保持这两棵目录的关系。CPU 测试无需远程 GPU、API Key 或云模型费用。

POP909 并发限制：不要同时对同一尚未生成音频的曲目启动两个评测进程；先完成一次生成。906 首未全部合成，全部运行会逐首产生音频和包含帧分数的 JSON，空间和时间需求明显增加，请先检查磁盘余量。GTZAN 原始 AU、FLAC 与压缩包均保留，未经用户要求不自动清理。

解释分数时须区分参考网格（`stableOracleGrid`）和预测网格（`stablePredictedGrid`）；只有后者反映完整系统。`status=complete` 表示程序完成，准确性是否达标要看指标。GuitarSet 并非 Beat This! 的上游独立测试集，POP909 合成录音也不是原曲混音域。
