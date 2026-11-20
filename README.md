# video2txt

把值得反复学习的视频和音频转成可搜索、带时间戳的文字稿，方便整理笔记、分析观点，以及回到原片核对内容。项目从 B 站视频开始，其他来源可以沿用同一套命令和输出格式。

输入视频链接或本地音视频即可转写。脚本默认从音轨开始，用 faster-whisper 在本机识别文字和时间，再用独立模型恢复中文标点。

## 支持的来源

| 来源 | 处理方式 |
| --- | --- |
| B 站标准视频链接 | 通过 B 站专用接口读取音轨，支持通过 `?p=2` 选择分 P |
| YouTube、Vimeo、Dailymotion、抖音、TikTok、小红书等 | 由 yt-dlp 解析单条视频链接，实际可用性取决于链接和平台访问条件 |
| 音视频直链 | 可访问的 HTTP 或 HTTPS 媒体链接可以直接传入 |
| 本地文件 | 转写音视频，或导入 SRT、VTT |

可查询 yt-dlp 官方支持列表。站点出现在列表中表示上游提供解析器，实际能否读取字幕或音轨还取决于具体视频。[yt-dlp 支持的站点](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)

## 安装

需要 Python 3.10 或更高版本。在 `transcribe.py` 所在目录运行以下命令。

```bash
python -m pip install -U -r requirements.txt
```

首次使用会下载语音识别模型，中文转写还会缓存约 72 MB 的标点模型。语音识别默认使用 CPU 和 `base` 模型。模型下载完成后，本地媒体可以离线转写。

处理 YouTube 链接时，请按 yt-dlp 的说明安装支持的 JavaScript 运行时。脚本默认使用 Deno，也可用 `--js-runtime node` 选择已安装的兼容 Node.js。[yt-dlp JavaScript 配置指南](https://github.com/yt-dlp/yt-dlp/wiki/EJS)

## 使用

将占位链接换成目标视频的分享链接。省略 `--language` 时，脚本会在语音识别阶段自动检测语言。

```bash
python transcribe.py "https://www.bilibili.com/video/BVxxxxxxxxxx/" --language zh
python transcribe.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

转写本地视频，或把已有字幕整理成文字稿。

```bash
python transcribe.py "input.mp4" --language zh
python transcribe.py "captions.srt" --language zh
```

默认在 `transcripts/` 下生成两个 UTF-8 文件。

| 文件 | 用途 |
| --- | --- |
| `.txt` | 按短段落阅读和搜索，每段开头带时间戳。标点稀少时，逐条保留识别短段 |
| `.srt` | 保留每条字幕的起止时间，可导入播放器或剪辑软件 |

## 常用选项

| 参数 | 作用 |
| --- | --- |
| `--language zh` | 指定中文。省略时自动识别音频语言 |
| `--prefer-subtitles` | 有平台字幕时优先导入，缺字幕时转写音轨 |
| `--model small` | 使用较大的模型，可尝试改善识别效果，也会增加下载量和转写时间 |
| `--out-dir transcripts` | 指定输出目录 |
| `--name sample` | 指定输出文件名。重新运行时会更新同名文件 |
| `--js-runtime node` | 将 yt-dlp 使用的 JavaScript 运行时从 Deno 改为 Node.js |
| `--punctuation off` | 沿用语音识别结果中的标点 |
| `--punctuation-model model.int8.onnx` | 使用已下载的 sherpa-onnx 标点模型 |

运行 `python transcribe.py --help` 可查看完整参数。

## 字幕和标点

中文转写会把若干相邻识别段一起送给 CT-Transformer 恢复标点。脚本校验文字和顺序，再把新增标点放回原来的时间段。转写时间依然以语音识别段为单位。标点模型无法运行时，TXT 仍按短段输出。

链接解析失败时，可以用本地音视频继续处理。主动导入字幕时，平台或文件里的标点和时间范围会被保留。

## 依赖

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [sherpa-onnx 标点模型](https://k2-fsa.github.io/sherpa/onnx/punctuation/pretrained_models.html)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
