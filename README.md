# video2txt

把值得反复学习的视频和音频转成可搜索、带时间戳的文字稿，方便整理笔记、分析观点，以及回到原片核对内容。项目从 B 站视频开始，其他来源可以沿用同一套命令和输出格式。

脚本优先读取平台提供的字幕。没有可用字幕时，它会获取音轨，并用 faster-whisper 在本机转写。也可以直接导入本地音视频或已有的 SRT、VTT 字幕。

## 支持的来源

| 来源 | 处理方式 |
| --- | --- |
| B 站标准视频链接 | 优先使用 B 站专用接口，支持通过 `?p=2` 选择分 P |
| YouTube、Vimeo、Dailymotion、抖音、TikTok、小红书等 | 由 yt-dlp 解析单条视频链接，实际可用性取决于链接和平台访问条件 |
| 音视频直链 | 可访问的 HTTP 或 HTTPS 媒体链接可以直接传入 |
| 本地文件 | 转写音视频，或导入 SRT、VTT |

可查询 yt-dlp 官方支持列表。站点出现在列表中表示上游提供解析器，实际能否读取字幕或音轨还取决于具体视频。[yt-dlp 支持的站点](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)

## 安装

需要 Python 3.10 或更高版本。在 `transcribe.py` 所在目录运行以下命令。

```bash
python -m pip install -U -r requirements.txt
```

首次使用语音识别时会下载模型。默认使用 CPU 和 `base` 模型。模型下载完成后，本地媒体可以离线转写。

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
| `.txt` | 按段落阅读、搜索和分析，每段开头带时间戳 |
| `.srt` | 保留每条字幕的起止时间，可导入播放器或剪辑软件 |

## 常用选项

| 参数 | 作用 |
| --- | --- |
| `--language zh` | 指定中文。省略时自动识别音频语言 |
| `--force-asr` | 跳过平台字幕，直接转写音轨 |
| `--model small` | 使用较大的模型，可尝试改善识别效果，也会增加下载量和转写时间 |
| `--out-dir transcripts` | 指定输出目录 |
| `--name sample` | 指定输出文件名。重新运行时会更新同名文件 |
| `--js-runtime node` | 将 yt-dlp 使用的 JavaScript 运行时从 Deno 改为 Node.js |

运行 `python transcribe.py --help` 可查看完整参数。

## 字幕和标点

已有字幕沿用原有标点。音频转写时，模型会根据句意和语音线索预测标点。长句、专有名词和引用片段可以结合时间戳回听核对。

如果字幕只显示在视频画面里，脚本会通过音轨生成文字稿。链接解析失败时，可以用已有的本地音视频或字幕文件继续处理。

## 依赖

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
