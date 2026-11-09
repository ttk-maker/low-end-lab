# 独立评测使用说明

运行中的查看地址：http://127.0.0.1:8765/audio-analysis/evaluation/index.html。

本版包含 8 个开发样本、8 个测试样本，每组 70 秒。由固定生成谱和种子合成，不使用 BTC 输出作标签。覆盖大小三、七和弦、跨窗口变化、快速换和弦、低音量、结束段、静音、大七/sus。它是独立于当前用户歌曲的合成回归集，不是独立人类标注的真实音乐基准；测试与开发的音色机制相似，仅根音与种子变化，泛化结论有限。

在 audio-analysis 目录，用安装后的 Python 运行：

```powershell
python evaluation/run.py --split dev --output evaluation/local-dev
python evaluation/run.py --split test --output evaluation/local-test
python evaluation/run_real.py --output evaluation/local-real.json
```

先使用 dev 调整参数，固定候选代码后再运行 test；不要根据测试集不断调参然后仍宣称它未见。保留每次代码/权重 SHA、参数、音频指纹与报告。本轮没有训练或微调权重。

指标：参考和预测区间精确求交，按秒数计算标签正确率、排除 X 后的覆盖率/选择性正确率；静音单列；边界按 0.2 秒一对一匹配给 precision/recall。未知计为不正确，区间更少不等于准确率更高。音乐部分单列，防止静音拉高总分。

真实素材入口在 real_manifest.json。新增条目要填 id、相对音频路径、split、reviewed、reviewer、rights，以及连续覆盖全曲的 reference：

```json
{"startSec":0,"endSec":4,"label":"C:maj"}
```

reviewed=false 的素材跳过，不能因标签空缺就用模型结果补真值。reviewed=true 必须有审核者与使用依据；参考标签应独立听辨，当前全曲计分不接受 X。真实歌曲准确率目前不可用（0 首已审核）。用户 MP3 只做回归检查；用户提供音频不代表获得公开再分发权。

旧版基线保存在 chords_baseline.py，不与新版共享改动的推理函数。模型架构与权重相同，本轮比较的是推理优化。生成样本在 fixtures/ 可回听；完整逐帧输出可以运行脚本重新生成。
