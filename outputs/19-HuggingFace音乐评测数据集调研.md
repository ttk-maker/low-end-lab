# Hugging Face 音乐性能评测数据集调研

核查日期：2026-11-09。对象：当前 LOW END LAB v0.7.0，Beat This! small0、BTC 170 类及新增节奏/和弦后处理。目的：寻找可以量化性能的数据，而不是仅增加试听素材。

本轮访问了 Hugging Face 数据集 API、文件目录、数据卡及可用的数据预览，并交叉查阅原作者仓库和数据发布页；抽查了参考标签、分段元数据与小型 MIDI 文件。没有批量下载音频，没有运行新一轮模型准确率评测，没有改动生产代码、项目校正或已有评测清单。动态网页与镜像内容可能更新；机器可读登记表记录了检索时的仓库 revision。

## 结论

优先组合是 **GTZAN 音频＋原始逐拍标注、GuitarSet 原始 JAMS＋麦克风音频、POP909-CL 去除答案轨后渲染的音频**。三者分别覆盖跨风格节奏、真实音色和弦与长曲可控和声。第二阶段补充 GAPS 的真实长演奏，并在录音对齐和许可落实后引入 JAAH/Harmonix。

没有任何一个已核查的 HF 数据集，可以不经适配就同时证明：真实三四分钟乐队录音、拍号转换、swing、复杂爵士和弦、静音和教学建议全部准确。必须分模块测试，再进行端到端测试。

| 优先级 | 数据集与入口 | 实际内容 | 最适合测什么 | 关键限制 |
|---|---|---|---|---|
| P0 | [GTZAN](https://huggingface.co/datasets/marsyas/gtzan) | 1,000 段约 30 秒音频、10 类风格；HF 本体主要是风格标签 | 拍点、第一拍、半速/倍速错误、跨风格节奏 | 需配外部逐拍标注；不能证明长曲稳定 |
| P0 | [GuitarSet 镜像 A](https://huggingface.co/datasets/jhartquist/guitarset)、[镜像 B](https://huggingface.co/datasets/taohu/guitarset) | 360 段真实吉他演奏、音频与和弦/节拍/音符标注 | 和弦根音与类型、换和弦边界、伴奏与旋律干扰 | 短片段；区分谱面标注和演奏推导标注；Beat This 已见过该数据来源 |
| P0 | [POP909-CL](https://huggingface.co/datasets/Itsuki-music/POP909-CL-Dataset) | 专家复核和弦轨、MIDI、拍号/调性/首拍修正；元数据 906 首 released | 小节内和弦转换、七和弦、转位、弱起、可控长曲 | 需要渲染；必须移除 CHORDS 答案轨；不是原始商业录音 |
| P1 | [GAPS](https://huggingface.co/datasets/xavriley/GAPS) | 真实古典吉他音频、MusicXML、对齐 MIDI、同步点 | 长曲时间定位、自由速度、谱面位置到音频的映射 | 需适配对齐；没有现成可靠的逐区间和弦答案；版本数量存在差异 |
| P1 | [Harmonix 镜像](https://huggingface.co/datasets/Archit00/harmonix-mirror) | 912 首流行曲的人工拍点、第一拍、小节号及功能段落标注 | 完整曲目的节奏、小节和段落 | 镜像未含 WAV/MP3/FLAC；需要对应录音；属于 Beat This 训练来源 |
| 专项 | [Slakh2100 镜像](https://huggingface.co/datasets/projectlosangeles/Slakh2100) | 合成多轨混音、独立乐器轨与对齐 MIDI | 贝斯/鼓干扰、混音密度、消融测试、以后贝斯转录 | 非人工和弦答案；体积大、镜像许可表述不一，优先官方小版本 |

## 1. GTZAN：当前最合适的节奏独立基准入口

HF 数据卡列出 1,000 段、每段约 30 秒，覆盖 blues、classical、country、disco、hiphop、jazz、metal、pop、reggae、rock。可见音频归档大小约 1.226 GB。HF 的 `genre` 不是逐拍参考答案。

配套使用 [Beat This! annotations v1.1](https://github.com/CPJKU/beat_this_annotations/tree/v1.1/gtzan/annotations/beats)。本次实际数到 **999 个 `.beats` 文件**，不能预设音频 1,000 条均有有效标注；导入时取 ID 交集并记录缺失原因。v1.1 对应提交 `890407d158078527ab396b49fea3c8a83e5734ee`。

抽查 `gtzan_jazz_00000.beats` 可见类似 `1.514\t1` 的“秒数＋小节内拍位”，因此可以独立评估第一拍，而非将首个检出拍强行设为第一拍。该样例末尾还出现约 24 ms 的异常相邻标注间距，说明参考标注也要做质量检查；应隔离、标注疑点，不能根据模型预测自动重写真值。

最重要的适配优势：[Beat This 官方说明](https://github.com/CPJKU/beat_this#available-models)明确写出 `small0/1/2` 和 `final0/1/2` 在训练时排除了 GTZAN。对于当前 small0，它比 GuitarSet/Harmonix 更适合做未参与该模型训练的数据集评估。仍需检查跨数据集相同录音和今后的测试集调参泄漏。

特别排除：[DynamicSuperb/MARBLEBeatTracking_GTZAN-Rhythm](https://huggingface.co/datasets/DynamicSuperb/MARBLEBeatTracking_GTZAN-Rhythm) 有 200 个测试样例、约 265 MB，但本次通过预览 API 核查的 `label` 是 `{'beat': 69, 'downbeat': 17}`。这是计数任务，不能计算逐拍误差、第一拍相位或累计漂移。

许可：HF GTZAN 卡片没有补全音频许可信息。标注仓库的 MIT 文件不能被解释成所有原曲录音都可以公开再分发。项目应分发下载/索引清单与测试结果，而不将商业录音打入分享包。

## 2. GuitarSet：适合先建立真实音色的和弦回归

原始数据有 6 位乐手、5 种风格（Jazz、Bossa Nova、Funk、Rock、Singer-Songwriter）、伴奏和独奏两种模式，共 360 段接近 30 秒的演奏。不是 360 首完全不同作品：材料来自有限的和声进行及其风格/速度变体，因此拆分时要同时考虑乐手、曲目/和声模板和录音版本。

HF 镜像 A 提供结构化 `chords`、`beats_s` 和四种音频采集；本次目录总计约 8.71 GB。镜像 B 的卡片保留 `chords`、`beats`、`jams`，以及麦克风/混合拾音两路音频，压缩量约 1.864 GB；其 first-rows 预览接口当前返回 501 扫描大小限制，不能据此说数据集不能下载。

更省空间的官方获取方式是 [Zenodo GuitarSet v1.1.0](https://zenodo.org/records/3371780)：只下载 `audio_mono-mic.zip`（约 657 MB）和 `annotation.zip`（约 39 MB），合计约 **696 MB**。官方发布为 **CC BY 4.0**，比某些镜像卡片的许可缺失更清楚。

标注来源必须保留。[mirdata 的 GuitarSet 加载器说明](https://github.com/mir-dataset-loaders/mirdata/blob/master/mirdata/datasets/guitarset.py)明确区分：

- `instructed / leadsheet`：给演奏者的数字谱面和弦。
- `performed / inferred`：依据演奏音符推导，并使用谱面的分段与根音。

这与镜像 A 的简短“manually verified”描述不是同一粒度的信息。不能把所有标签都记作独立人工逐秒听辨。建议优先选 `comp` 伴奏片段，分别报告谱面和弦匹配与演奏音符推导标签匹配；`solo` 片段单列为“旋律与和声上下文”的压力测试。

还需处理原作者公开的两处音符时间偏移、一处重复音符勘误。镜像 A 表示已修复 notes，不能因此假设所有 beat/chord 字段也作了相同修正。原始 JAMS 有小节内拍位；简化的 `beats_s` 只有时间，做第一拍评测需要补回原始字段。

模型重叠：GuitarSet 出现在 [Beat This 标注来源](https://github.com/CPJKU/beat_this_annotations)中，因此对 small0 应标为训练来源内回归。BTC 原仓库列出的训练数据是 Isophonics、Robbie Williams、UsPop2002，没有列 GuitarSet；可作为和弦外部候选，但这还不是所有录音零重叠的证明。

## 3. POP909-CL：最贴合小节和弦逻辑的可控材料

[HF 仓库](https://huggingface.co/datasets/Itsuki-music/POP909-CL-Dataset)与[原作者仓库](https://github.com/AndyWeasley2004/POP909-CL-Dataset)均可访问。抽查实际 `POP909_processed/metadata.csv`：909 行，其中 **906 released、3 missing**。README 解释缺失曲目为 553、367、658，并说明 10 首带有特殊情况 flags。

实际 `POP909_chord_labels/001.csv` 包含 `offset_qb, root, quality, bass, local_key`，能表达根音、三和弦/七和弦与转位。专家人工标注的是和弦轨，最终和弦符号由音级集合模板生成；拍号等修正也包含自动检测后复核的流程，不应描述为每个字段均完全人工产生。

建议作为端到端的合成演奏测试：

1. 从 processed MIDI 取演奏轨 MELODY、BRIDGE、PIANO，**移除 CHORDS 参考答案轨**。不能额外合成一条完全正确的和弦铺底来帮助识别。
2. 读取速度事件、PPQ、拍号、弱起与 shift 信息，构建谱面位置到渲染音频秒数的映射。
3. 单独导出参考和弦、小节与拍点，渲染测试音频时不得让模型读取这些答案。
4. 使用多种有许可的音源生成音色版本；同一作品的所有音色/速度版本放在同一数据划分中。
5. 保留复杂标签，不支持的词汇标为超出模型词表；不能把七和弦简化为三和弦后仍称其为完整和弦识别准确率。

时间陷阱：README 指出一个 POP909 网格 beat 是 480 ticks、0.6 秒，但不同拍号下 `ticks_per_beat` 不同（480/960，092 特殊为 320）。不能把所有文件的 beat 都当作四分音符，也不能把此 MIDI 时间直接对齐同名原曲商业录音。

仓库提供 MIT 许可文件；原作品、上游 MIDI 与渲染音源的使用范围分别核对。这里的可控合成评测成绩必须与真实录音成绩分开。当前 BTC 早于该修订集，仍不能排除相同作品出现在其他训练集。

## 4. GAPS：真实长演奏补充，先处理版本与对齐

[GAPS](https://huggingface.co/datasets/xavriley/GAPS)卡片介绍 300 段、14 小时、超过 200 位演奏者的古典吉他真实录音，包含对齐 MIDI 和 MusicXML。实际当前目录列出 **404 个 WAV**；元数据有 **401 行**，其中 `train=270`、`test=30`、未指定 split 为 101。数据卡与新增文件显然不完全同步，导入不能简单相信一个总数。

已抽查 `syncpoints/001_mvswc.json`，确实包含成对同步位置；元数据还有 scorehash、cropped_duration、timesig 等字段。必须先确认同步坐标单位、裁剪前后时间基准、重复段/反复记号与音符对齐；不能把录音的默认 MIDI tempo 当作人工节拍标注。只有检验通过的片段才计分。

最适合验证真实演奏三到四分钟内的时间映射、自由速度与长程稳定性。它没有现成的完整和弦标签，不能直接替代和弦准确率集。卡片标 MIT；音频来自不同演奏者和来源，研究与分享录音时还应保留来源和逐项权限依据。先抽取少量 manifest 完整的片段，不建议全库下载。

## 5. Harmonix 与 JAAH：分别补结构、补真实爵士和声

Harmonix 原作者给出 912 首西方流行乐的人工节拍、第一拍、功能段落标注。HF 镜像实际有 912 个 JAMS、原始文本标注和脚本，没有 WAV/MP3/FLAC。它适合长曲小节/段落回归，但必须拿到与标注版本一致的录音；同名不同母带、前导静音、现场版都可能制造假的模型漂移。官方另提供谱图，不等于我们的波形输入管线可直接使用。

另一个 HF 仓库 `m-a-p/harmonixset_bigvgan` 只有归档与 corrected JSONL、没有说明卡。没有验证其音频生成/对齐及许可，暂不作为首选真值数据。合成或声码器重建不能消除原始训练素材重叠。

本轮 HF 检索未找到可明确核验的 JAAH 标准镜像，但[原作者 JAAH 页面](https://mtg.github.io/JAAH/)与[仓库](https://github.com/MTG/JAAH)公开：**113 首爵士、17,600 个和弦区间**，提供 JSON/LAB 标注与特征。它比只有类别标签的数据更贴合爵士和声目标，但本轮没有取得对应完整录音，不计为“可立即开跑”。Beat This 的标注来源也包含 JAAH，且说明对拍点作过修正并补充第一拍，因此节奏测试同样需标明训练来源重叠。

## 6. 适合补充但不宜直接当核心准确率答案的 HF 数据

| 数据集 | 本次实际核查 | 正确用途 |
|---|---|---|
| [MusicBench](https://huggingface.co/datasets/amaai-lab/MusicBench) | beat/chord/key 是从音频自动提取；大量增强音频与文字描述 | 文本音乐理解或伪标签训练、一致性检查；不能当独立人工准确率真值 |
| [Chordonomicon](https://huggingface.co/datasets/ailsntua/Chordonomicon) | 666,000+ 和弦进行与段落等元数据，无逐秒对应音频 | 和声进行、段落结构、乐理问答测试；不能测音频识别准确率 |
| [Chord Llama](https://huggingface.co/datasets/Chord-Llama/chord_llama_dataset) | 改写 MusicXML/YAML 的前后半段续写数据 | 符号音乐生成；不是音频和弦识别测试 |
| [DynamicSuperb 和弦分类](https://huggingface.co/datasets/DynamicSuperb/ChordClassification_AcousticGuitarAndPiano) | 200 项；抽查 label 为 major，任务是 major/minor 二分类 | 轻量自检；不能验证根音、七和弦、转位或时间边界 |
| [MAESTRO FLAC 镜像](https://huggingface.co/datasets/DreamyWanderer/MAESTRO-v3.0-FLAC) | 真实钢琴录音与对齐 MIDI 文件 | 音符转录、真实长音频压力测试；音符时间不等于拍点或人工和弦标签 |
| [Slakh 镜像](https://huggingface.co/datasets/projectlosangeles/Slakh2100) | 多轨合成音频与 MIDI；完整归档约 104 GB | 贝斯音量、鼓填充、遮蔽等可控消融；MIDI 推导和弦需单列参考来源 |
| [Chords1217](https://huggingface.co/datasets/m-a-p/Chords1217) | 存在音频与 train/val/test JSONL，但仓库 gated | 申请后再核查标注来源；要求认可学术机构身份，单纯个人非盈利不自动满足条件 |

Slakh 官方许可为 CC BY 4.0，部分 HF 镜像标为 CC BY-NC-SA 4.0；优先使用[官方版本](http://www.slakh.com/)并记录来源。可先用 [BabySlakh](https://zenodo.org/records/4603870)，实际归档约 883 MB。注意官方指出旧版本有 MIDI 重复问题，应按修订版划分而非按音频文件随机拆分。抽查的 `tvergho/slakh` 是 1,539 行 stem/instrument 任务包装，卡片没有 MIDI 字段，不能当完整 Slakh 直接套用。

## 与本项目接入时的评测设计

按以下顺序实施，避免把节奏错位误归因于和弦模型：

1. **参考数据质量检查**：固定 revision、音频 SHA-256、标签来源和单位，检查越界/非单调时间、异常间距、已知错误、缺失区间和录音版本。未知或无标注不等于静音；N 也不必然表示物理静音。
2. **节奏单独评测**：GTZAN 用逐拍时间与原始第一拍；分别报告 Beat This 原始输出和新后处理，不只比较最后的 BPM。
3. **和弦模块单独评测**：GuitarSet/POP909-CL 提供参考小节网格，隔离节奏模型错误，再看 BTC 与小节后处理。
4. **端到端评测**：只把音频交给系统，使用预测节奏＋预测和弦，与独立参考比较。
5. **长曲与混音专项**：POP909-CL 的长曲渲染；GAPS 对齐核验后的真实长演奏；Slakh 控制贝斯、鼓、其它声部的混音。不能把 30 秒片段简单重复拼成 4 分钟后宣称真实长曲通过。

建议首批规模：GTZAN 按风格分层抽 100 段作为公开诊断集；GuitarSet 先取 30–60 段伴奏；POP909-CL 先取 20–30 首，包含三和弦、七和弦、转位和小节内换和弦。可用于调参的诊断集与冻结测试集必须分开；既然某个样例指导过改动，就不再把它报告为从未见过的独立测试。以上数量是建议配置，尚未实际采样或运行。

节奏报告至少包含：beat/downbeat F1（70 ms，另报更严容差）、CMLc/CMLt、AMLc/AMLt、逐分钟有符号误差、最长连续正确区间、小节首拍错误、半速/倍速错误、错误输出的静音拍数。AML 指标允许部分拍层歧义，不能只拿 AML 高分宣称小节坐标正确。

和弦报告至少包含：时长加权根音、maj/min、三和弦、七和弦指标；精确标签与模型支持词汇内指标；换和弦边界 precision/recall；同和弦段的误拆分率；一小节两和弦漏检；未知覆盖率与已输出部分的准确率。无标注和超词表部分单独列出，不能删除困难样本来改善总分。

所有成绩分开标注真实录音/渲染音频、参考网格/预测网格、训练来源内/未列入训练来源、开发诊断/冻结测试。按曲目计算宏平均，并保留按时长加权结果，避免长曲或简单持续和弦主导总分。

## 费用与交付状态

上述公开仓库的数据检索通常不需要付费 API Key；下载 HF 公共数据通常也不需要 Key，限流时可使用免费 HF token。gated 数据要求用户自己的账号资格与条款接受，token 不能绕过权限。本地模型跑评测无需调用 Qwen，也没有按次 LLM API 费用；主要成本是存储、带宽和计算时间。

已交付本报告和 `music-evaluation-datasets-2026-11-09.json`，后者包含 15 个 HF 仓库的 revision、文件概况、推荐状态、训练重叠备注和来源哈希。原始检索快照在工作目录保留。没有将来源不明标签自动写进当前系统的 reviewed=true 清单。
