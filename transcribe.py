"""Write a timestamped TXT transcript and SRT subtitles for one video or audio file."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from html import unescape
from pathlib import Path
import json
import os
import re
import shutil
import sys
from tarfile import TarError
from tempfile import TemporaryDirectory
from textwrap import fill
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen

from restore_punctuation import MARKS, SENTENCE_END, get_model, join_text, load_predictor, restore_lines

BILIBILI_API = "https://api.bilibili.com"
BILIBILI_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36"


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


def status(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def plain_text(value: str) -> str:
    return " ".join(unescape(re.sub(r"</?[^>]+>", "", value)).split())


def parse_captions(content: str, extension: str) -> list[Cue]:
    import pysubs2

    format_name = "srt" if extension == "srt" else "vtt"
    subtitles = pysubs2.SSAFile.from_string(content.lstrip("\ufeff"), format_=format_name)
    cues = [Cue(item.start / 1000, item.end / 1000, plain_text(item.plaintext)) for item in subtitles]
    return sorted((cue for cue in cues if cue.text and 0 <= cue.start < cue.end), key=lambda cue: cue.start)


def base_language(tag: str) -> str:
    tag = tag.lower().replace("_", "-").removeprefix("ai-")
    primary = tag.split("-")[0]
    return "zh" if primary in {"zho", "cmn", "chi"} else primary


def subtitle_candidates(info: dict, language: str):
    source_language = info.get("language") if language == "auto" else language
    for name, label in (("subtitles", "平台字幕"), ("automatic_captions", "平台自动字幕")):
        tracks = info.get(name) or {}
        preferred = []
        for tag, formats in tracks.items():
            if not re.fullmatch(r"(?:ai-)?[a-zA-Z]{2,3}(?:[-_][a-zA-Z0-9]+)*", tag):
                continue
            if source_language and base_language(tag) != base_language(source_language):
                continue
            if not source_language and name == "automatic_captions" and not tag.endswith("-orig"):
                continue
            preferred.append((tag, formats))

        preferred.sort(key=lambda track: (
            not track[0].endswith("-orig"),
            track[0].lower() not in {"zh", "zh-cn", "zh-hans", "ai-zh"},
        ))
        for tag, formats in preferred:
            for extension in ("srt", "vtt"):
                for track in formats:
                    if track.get("ext") == extension:
                        yield track, tag, label


def read_platform_subtitles(downloader, info: dict, language: str):
    from pysubs2.exceptions import Pysubs2Error
    from yt_dlp.networking import Request
    from yt_dlp.networking.exceptions import RequestError

    for track, tag, label in subtitle_candidates(info, language):
        try:
            content = track.get("data")
            if content is None:
                headers = {**(info.get("http_headers") or {}), **(track.get("http_headers") or {})}
                with downloader.urlopen(Request(track["url"], headers=headers)) as response:
                    content = response.read().decode("utf-8-sig")
            cues = parse_captions(content, track["ext"])
        except (KeyError, ValueError, OSError, Pysubs2Error, RequestError) as exc:
            status(f"字幕 {tag} 无法读取，尝试下一个字幕或音轨。{exc}")
            continue
        if cues:
            return cues, tag, label
    return None


def fetch_json(url: str, headers: dict) -> dict:
    with urlopen(Request(url, headers=headers), timeout=25) as response:
        return json.load(response)


def bilibili_api(endpoint: str, parameters: dict, headers: dict) -> dict:
    response = fetch_json(f"{BILIBILI_API}{endpoint}?{urlencode(parameters)}", headers)
    if response["code"] != 0:
        raise ValueError(f"B 站接口 {endpoint} 返回 {response['code']}，{response.get('message', '')}")
    return response["data"]


def bilibili_subtitles(parameters: dict, headers: dict, language: str):
    player = bilibili_api("/x/player/wbi/v2", parameters, headers)
    tracks = (player.get("subtitle") or {}).get("subtitles") or []
    tracks.sort(key=lambda track: (bool(track.get("ai_type")), track.get("lan") != "zh-CN"))
    for track in tracks:
        tag = track.get("lan") or "und"
        if language != "auto" and base_language(tag) != base_language(language):
            continue
        if not track.get("subtitle_url"):
            continue
        try:
            subtitle = fetch_json(urljoin(BILIBILI_API, track["subtitle_url"]), headers)
            cues = [Cue(item["from"], item["to"], plain_text(item["content"])) for item in subtitle["body"]]
        except (KeyError, ValueError, OSError) as exc:
            status(f"字幕 {tag} 无法读取，尝试下一个字幕或音轨。{exc}")
            continue
        cues = [cue for cue in cues if cue.text and 0 <= cue.start < cue.end]
        if cues:
            return sorted(cues, key=lambda cue: cue.start), tag, "B 站字幕"
    return None


def resolve_bilibili(identifier: str, part: int, directory: Path, args):
    canonical_url = f"https://www.bilibili.com/video/{identifier}/"
    headers = {"User-Agent": BILIBILI_AGENT, "Referer": canonical_url}
    key = {"bvid": identifier} if identifier.startswith("BV") else {"aid": int(identifier[2:])}
    details = bilibili_api("/x/web-interface/view", key, headers)
    page = next((item for item in details["pages"] if item["page"] == part), None)
    if page is None:
        raise ValueError(f"视频没有 P{part}。")
    title = details["title"]
    source = f"https://www.bilibili.com/video/{details['bvid']}/"
    if len(details["pages"]) > 1:
        title = f"{title} P{part} {page['part']}"
        source = f"{source}?p={part}"
    parameters = {"bvid": details["bvid"], "cid": page["cid"]}
    if args.prefer_subtitles:
        try:
            subtitles = bilibili_subtitles(parameters, headers, args.language)
        except (ValueError, OSError) as exc:
            status(f"无法读取 B 站字幕列表，尝试获取音轨。{exc}")
        else:
            if subtitles:
                return title, source, *subtitles

    status("正在从 B 站获取音轨。")
    playback = bilibili_api("/x/player/playurl", {**parameters, "fnval": 4048, "qn": 64}, headers)
    audio_tracks = (playback.get("dash") or {}).get("audio") or []
    if not audio_tracks:
        raise ValueError("B 站未返回此视频的公开音轨。")
    track = max(audio_tracks, key=lambda item: item.get("bandwidth", 0))
    urls = [track.get("baseUrl") or track.get("base_url"), *(track.get("backupUrl") or track.get("backup_url") or [])]
    media = directory / "audio.m4a"
    error = None
    for url in dict.fromkeys(filter(None, urls)):
        try:
            with urlopen(Request(url, headers=headers), timeout=30) as response, media.open("wb") as output:
                expected_size = response.headers.get("Content-Length")
                shutil.copyfileobj(response, output)
            actual_size = media.stat().st_size
            if actual_size and (expected_size is None or actual_size == int(expected_size)):
                break
            error = OSError("音轨长度与服务器返回的长度不一致。")
        except OSError as exc:
            error = exc
    else:
        raise ValueError(f"B 站音轨下载失败。{error or ''}")
    cues, language = recognize(media, args)
    return title, source, cues, language, f"本地语音识别（{Path(args.model).name}）"


def resolve_video(url: str, directory: Path, args):
    parsed = urlsplit(url)
    if parsed.hostname in {"bilibili.com", "www.bilibili.com", "m.bilibili.com"}:
        match = re.fullmatch(r"/video/(BV[A-Za-z0-9]+|av[0-9]+)/?", parsed.path)
        if match:
            part = int(parse_qs(parsed.query).get("p", ["1"])[0])
            status(f"正在读取 B 站投稿 {match[1]}，P{part}。")
            return resolve_bilibili(match[1], part, directory, args)

    import yt_dlp

    options = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "outtmpl": str(directory / "audio.%(ext)s"),
        "quiet": True,
        "noprogress": True,
        "socket_timeout": 25,
        "retries": 3,
        "js_runtimes": {args.js_runtime: {}},
    }
    status(f"正在读取 {parsed.hostname} 的视频信息。")
    metadata_options = {**options, "writesubtitles": args.prefer_subtitles,
                        "writeautomaticsub": args.prefer_subtitles}
    with yt_dlp.YoutubeDL(metadata_options) as downloader:
        info = downloader.extract_info(url, download=False)
        if not info or "entries" in info:
            raise ValueError("请提供单个视频的链接。多分 P 视频可在链接中指定 ?p=页码。")
        title = info.get("title") or info["id"]
        source = info.get("webpage_url") or url
        if args.prefer_subtitles:
            result = read_platform_subtitles(downloader, info, args.language)
            if result:
                cues, language, method = result
                return title, source, cues, language, method

    status("正在获取音轨。")
    with yt_dlp.YoutubeDL(options) as downloader:
        downloaded = downloader.process_ie_result(info, download=True)
        media = Path(downloader.prepare_filename(downloaded))
    if not media.is_file():
        raise ValueError("音轨下载结束后未找到媒体文件。")
    cues, language = recognize(media, args)
    return title, source, cues, language, f"本地语音识别（{Path(args.model).name}）"


def punctuate_cues(cues: list[Cue], predict) -> list[Cue]:
    restored = []
    start = 0
    size = 0
    for index, cue in enumerate(cues):
        size += len(cue.text)
        is_last = index == len(cues) - 1
        pause = is_last or cues[index + 1].start - cue.end >= 0.9
        if not (pause or size >= 200):
            continue
        batch = cues[start:index + 1]
        lines = restore_lines([item.text for item in batch], predict, ends_at_pause=pause)
        restored.extend(Cue(item.start, item.end, text) for item, text in zip(batch, lines))
        start, size = index + 1, 0
    return restored


def recognize(media: Path, args) -> tuple[list[Cue], str]:
    from faster_whisper import WhisperModel
    from opencc import OpenCC

    compute_type = "float16" if args.device == "cuda" else "int8"
    status(f"正在加载 {args.model} 模型（{args.device}）。")
    model = WhisperModel(args.model, device=args.device, compute_type=compute_type,
                         cpu_threads=args.threads, download_root=args.cache_dir)
    segments, info = model.transcribe(
        str(media),
        language=None if args.language == "auto" else base_language(args.language),
        vad_filter=True,
        beam_size=5,
    )
    status(f"开始转写，音频时长 {timestamp(info.duration, milliseconds=False)}。")
    captions = []
    next_update = 60
    for segment in segments:
        content = segment.text.strip()
        if content and segment.end > segment.start:
            captions.append(Cue(segment.start, segment.end, content))
        if segment.end >= next_update:
            status(f"已处理到 {timestamp(segment.end, milliseconds=False)}。")
            next_update = (int(segment.end) // 60 + 1) * 60
    if info.language == "zh":
        convert = OpenCC("t2s").convert
        captions = [Cue(cue.start, cue.end, convert(cue.text)) for cue in captions]
        if captions and args.punctuation != "off":
            from huggingface_hub.constants import HF_HOME

            try:
                status("正在从识别文本恢复中文标点。首次运行可能下载标点模型。")
                cache = Path(args.cache_dir or HF_HOME).expanduser() / "video2txt"
                model_path = args.punctuation_model or get_model(cache)
                restored = punctuate_cues(captions, load_predictor(model_path, args.threads))
                changed = sum(before.text != after.text for before, after in zip(captions, restored))
                status(f"已为 {changed} 个时间段补充标点。")
                captions = restored
            except (EOFError, ImportError, OSError, RuntimeError, TarError, ValueError) as exc:
                status(f"标点恢复失败，输出原识别文字及其时间段。{exc}")
    return captions, info.language


def timestamp(seconds: float, *, milliseconds: bool) -> str:
    total_ms = round(seconds * 1000)
    whole, fraction = divmod(total_ms, 1000)
    hours, remainder = divmod(whole, 3600)
    minutes, second = divmod(remainder, 60)
    value = f"{hours:02d}:{minutes:02d}:{second:02d}"
    return f"{value},{fraction:03d}" if milliseconds else value


def transcript_paragraphs(cues: list[Cue]) -> list[str]:
    marked = sum(any(mark in MARKS for mark in cue.text) for cue in cues)
    short_lines = marked * 20 < len(cues)
    paragraphs = []
    start = end = 0.0
    paragraph = ""
    for cue in cues:
        combined = join_text(paragraph, cue.text)
        if paragraph and (short_lines or len(combined) > 100 or cue.end - start > 15
                          or cue.start - end >= 1.5 or paragraph.endswith(SENTENCE_END)):
            paragraphs.append((start, paragraph))
            combined = cue.text
            paragraph = ""
        if not paragraph:
            start = cue.start
        paragraph, end = combined, cue.end
    if paragraph:
        paragraphs.append((start, paragraph))
    return [f"[{timestamp(start, milliseconds=False)}] {fill(text, width=72, break_on_hyphens=False)}"
            for start, text in paragraphs]


def write_outputs(cues: list[Cue], title: str, source: str, language: str, method: str,
                  directory: Path, name: str | None) -> tuple[Path, Path]:
    if not cues:
        raise ValueError("没有识别到可输出的语音或字幕。")
    basename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name or title).strip(" .")[:120] or "transcript"
    if Path(basename).is_reserved():
        basename = f"_{basename}"
    directory.mkdir(parents=True, exist_ok=True)
    txt, srt = (directory / f"{basename}.{extension}" for extension in ("txt", "srt"))

    text = [title, f"来源 {source}", f"生成方式 {method}｜语言 {language}"]
    subtitles = []
    for index, cue in enumerate(cues, 1):
        times = f"{timestamp(cue.start, milliseconds=True)} --> {timestamp(cue.end, milliseconds=True)}"
        subtitles.append(f"{index}\n{times}\n{cue.text}\n")

    with TemporaryDirectory(prefix=".transcript-", dir=directory) as temporary:
        transcript = "\n".join(text) + "\n\n" + "\n\n".join(transcript_paragraphs(cues))
        for destination, content in ((txt, transcript), (srt, "\n".join(subtitles))):
            staging = Path(temporary) / destination.name
            staging.write_text(content + "\n", encoding="utf-8")
        for destination in (txt, srt):
            (Path(temporary) / destination.name).replace(destination)
    return txt, srt


def main() -> int:
    parser = argparse.ArgumentParser(description="把视频或音频转成带时间戳的 TXT 和 SRT。")
    parser.add_argument("source", help="单个视频的 HTTP(S) 链接，本地媒体文件，或本地 SRT/VTT")
    parser.add_argument("--out-dir", type=Path, default=Path("transcripts"))
    parser.add_argument("--name", help="输出文件名，不含扩展名")
    parser.add_argument("--language", default="auto", help="auto 自动识别，或指定 zh、en 等")
    parser.add_argument("--model", default="base", help="faster-whisper 模型名或本地模型目录")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--threads", type=int, default=min(os.cpu_count() or 4, 8))
    parser.add_argument("--cache-dir", help="faster-whisper 模型缓存目录")
    parser.add_argument("--js-runtime", choices=("deno", "node"), default="deno",
                        help="yt-dlp 用于 YouTube 等网站的 JavaScript 运行时")
    parser.add_argument("--punctuation", choices=("auto", "off"), default="auto",
                        help="中文转写后恢复标点，或保留识别模型给出的标点")
    parser.add_argument("--punctuation-model", type=Path, help="使用本地的 sherpa-onnx 标点模型文件")
    subtitle_mode = parser.add_mutually_exclusive_group()
    subtitle_mode.add_argument("--prefer-subtitles", action="store_true", help="有平台字幕时优先导入")
    subtitle_mode.add_argument("--force-asr", dest="prefer_subtitles", action="store_false", help=argparse.SUPPRESS)
    parser.set_defaults(prefer_subtitles=False)
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("--threads 必须大于零")

    try:
        if urlsplit(args.source).scheme in {"http", "https"}:
            args.out_dir = args.out_dir.resolve()
            args.out_dir.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(prefix=".transcribe-", dir=args.out_dir) as directory:
                title, source, cues, language, method = resolve_video(args.source, Path(directory), args)
        else:
            local = Path(args.source).resolve(strict=True)
            title, source = local.stem, local.name
            if local.suffix.lower() in {".srt", ".vtt"}:
                cues = parse_captions(local.read_text(encoding="utf-8-sig"), local.suffix.lower()[1:])
                language, method = args.language, "导入字幕"
            else:
                cues, language = recognize(local, args)
                method = f"本地语音识别（{Path(args.model).name}）"
        for destination in write_outputs(cues, title, source, language, method, args.out_dir, args.name):
            print(destination.resolve())
    except Exception as exc:
        status(f"处理失败：{exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
