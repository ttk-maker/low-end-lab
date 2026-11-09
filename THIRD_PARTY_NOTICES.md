# 第三方来源与许可

本项目是非盈利的贝斯乐理学习兴趣项目。非盈利意图不替代第三方许可、音频使用授权或 API 计费规则。本次源码上传没有替项目作者选择新的整体开源许可证；公开可见也不自动授予任意再分发权。

- **Beat This!**：[CPJKU/beat_this](https://github.com/CPJKU/beat_this)，使用官方 small0 权重。许可副本见 `outputs/audio-analysis/models/LICENSE-BeatThis.txt`。权重不随 Git 仓库上传，由安装器下载。
- **BTC**：[jayg996/BTC-ISMIR19](https://github.com/jayg996/BTC-ISMIR19)。项目内的适配代码及 MIT 许可保存在 `outputs/audio-analysis/vendor/btc/`，修改说明见 `provenance.json`。权重不随 Git 上传。
- **GTZAN**：含真实歌曲片段；公开下载不等于原曲可自由再分发。本仓库只提供下载/评测适配代码与统计结果，不打包音频。
- **GuitarSet**：[Zenodo 3371780](https://zenodo.org/records/3371780)，CC BY 4.0。下载使用时保留作者署名及上游引用要求。
- **POP909-CL**：[作者仓库](https://github.com/AndyWeasley2004/POP909-CL-Dataset)。使用其发布许可与引用要求，MIDI 发布不包含原商业歌曲音频授权。
- **FluidSynth / TimGM6mb**：评测按需下载合成器与 SoundFont；不随源码上传。TimGM6mb 的 Debian 版权记录为 GPL-2。
- **Qwen / 百炼**：可选外部 API 服务，使用者自行配置账号与凭据，按服务条款计费。仓库不包含任何有效 API Key。

其他 Python 依赖遵循各自上游许可证。论文、数据集及乐理参考来源见 `outputs/` 中的资料文档。
