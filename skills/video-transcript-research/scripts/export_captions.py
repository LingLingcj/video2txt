"""Export original or converted SRT and a readable timestamped TXT from a caption file."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from textwrap import fill


@dataclass(frozen=True)
class Cue:
    start_ms: int
    end_ms: int
    text: str


def read_timed_json(content: str, duration_ms: int | None) -> tuple[list[Cue], bool]:
    data = json.loads(content)
    if isinstance(data, dict):
        transcript = data.get("transcript", data)
        data = transcript.get("segments") if isinstance(transcript, dict) else transcript
    if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
        raise ValueError("Timed JSON must contain a list of caption objects.")

    for row in data:
        if type(row.get("startMs")) is not int or not isinstance(row.get("text"), str):
            raise ValueError("Each caption needs an integer startMs and a text field.")
        if row.get("endMs") is not None and type(row["endMs"]) is not int:
            raise ValueError("endMs must be an integer when supplied.")
    starts = [row["startMs"] for row in data]
    if starts != sorted(starts):
        raise ValueError("Timed JSON must be ordered by startMs.")

    cues = []
    inferred = False
    following_start = None
    for index in range(len(data) - 1, -1, -1):
        row = data[index]
        start = row["startMs"]
        if index + 1 < len(data) and starts[index + 1] > start:
            following_start = starts[index + 1]
        end = row.get("endMs")
        if end is None:
            inferred = True
            end = following_start if following_start is not None else start + 4000
            if duration_ms is not None:
                end = min(end, duration_ms)
        cues.append(Cue(start, end, row["text"]))
    return list(reversed(cues)), inferred


def read_captions(path: Path, duration_ms: int | None) -> tuple[list[Cue], bytes | None, bool]:
    data = path.read_bytes()
    content = data.decode("utf-8-sig")
    extension = path.suffix.lower()
    if extension == ".json":
        cues, inferred = read_timed_json(content, duration_ms)
        return cues, None, inferred
    if extension not in {".srt", ".vtt"}:
        raise ValueError("Use an SRT, VTT, or timed JSON input file.")

    import pysubs2

    try:
        subtitles = pysubs2.SSAFile.from_string(content, format_=extension[1:])
    except pysubs2.exceptions.Pysubs2Error as error:
        raise ValueError(f"Could not read the caption file: {error}") from error
    cues = [Cue(cue.start, cue.end, cue.plaintext) for cue in subtitles]
    return cues, data if extension == ".srt" else None, False


def timestamp(milliseconds: int, *, precise: bool = False) -> str:
    seconds, fraction = divmod(milliseconds, 1000)
    hour, remainder = divmod(seconds, 3600)
    minute, second = divmod(remainder, 60)
    value = f"{hour:02d}:{minute:02d}:{second:02d}"
    return f"{value},{fraction:03d}" if precise else value


def reading_blocks(cues: list[Cue]) -> list[tuple[int, str]]:
    blocks = []
    start = end = 0
    paragraph = ""
    visible = [cue for cue in cues if cue.text.strip()]
    with_punctuation = sum(bool(re.search(r"[。？！、，；：,.?!]", cue.text)) for cue in visible)
    short_lines = with_punctuation * 20 < len(visible)
    for cue in visible:
        text = " ".join(cue.text.split())
        separator = "" if re.search(r"[\u3400-\u9fff]$", paragraph) and re.match(r"[\u3400-\u9fff]", text) else " "
        combined = (paragraph + separator + text).lstrip()
        elapsed = cue.start_ms - start
        length_limit = 100 if re.search(r"[\u3400-\u9fff]", combined) else 220
        if paragraph and (
            short_lines or text.startswith(">>") or cue.start_ms - end >= 1800
            or len(combined) > length_limit or elapsed >= 15000
            or (elapsed >= 5000 and paragraph.endswith((".", "?", "!", "。", "？", "！")))
        ):
            blocks.append((start, paragraph))
            paragraph = ""
            combined = text
        if not paragraph:
            start = cue.start_ms
        paragraph, end = combined, cue.end_ms
    if paragraph:
        blocks.append((start, paragraph))
    return blocks


def render_srt(cues: list[Cue]) -> bytes:
    entries = []
    for cue in cues:
        text = "\n".join(line.strip() for line in cue.text.splitlines() if line.strip())
        if text:
            start = timestamp(cue.start_ms, precise=True)
            end = timestamp(cue.end_ms, precise=True)
            entries.append(f"{len(entries) + 1}\n{start} --> {end}\n{text}")
    return ("\n\n".join(entries) + "\n").encode("utf-8")


def export(args: argparse.Namespace) -> tuple[Path, Path]:
    stem = args.name or args.input.stem
    if re.search(r'[<>:"/\\|?*\x00-\x1f]', stem) or stem.endswith((" ", ".")) or Path(stem).is_reserved():
        raise ValueError("Choose a plain output filename for --name.")
    if args.duration is not None and (not math.isfinite(args.duration) or args.duration <= 0):
        raise ValueError("--duration must be a positive number of seconds.")
    duration_ms = round(args.duration * 1000) if args.duration is not None else None
    cues, native, inferred = read_captions(args.input, duration_ms)
    if any(not 0 <= cue.start_ms < cue.end_ms for cue in cues):
        raise ValueError("Each cue needs a valid, positive duration.")
    if any(a.start_ms > b.start_ms for a, b in zip(cues, cues[1:])):
        raise ValueError("Caption start times are out of order.")
    blocks = reading_blocks(cues)
    if not blocks:
        raise ValueError("No non-empty captions were found.")

    header = [args.title or stem]
    if args.source:
        header.append(f"Source — {args.source}")
    if args.provenance:
        header.append(f"Caption origin — {args.provenance}")
    if inferred:
        header.append("Timing — some SRT cue ends were estimated from the published start times.")

    paragraphs = [
        f"[{timestamp(start)}] {fill(text, width=88, break_on_hyphens=False)}"
        for start, text in blocks
    ]
    document = "\n".join(header) + "\n\n" + "\n\n".join(paragraphs) + "\n"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    srt, txt = (args.out_dir / f"{stem}.{extension}" for extension in ("srt", "txt"))
    with TemporaryDirectory(prefix=".captions-", dir=args.out_dir) as temporary:
        temporary = Path(temporary)
        staged_srt, staged_txt = temporary / srt.name, temporary / txt.name
        staged_srt.write_bytes(native if native is not None else render_srt(cues))
        staged_txt.write_text(document, encoding="utf-8")
        staged_srt.replace(srt)
        staged_txt.replace(txt)
    return srt, txt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="SRT, VTT, or timed JSON file")
    parser.add_argument("--out-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--name", help="output filename stem, including any desired language suffix")
    parser.add_argument("--title")
    parser.add_argument("--source", help="original recording URL")
    parser.add_argument("--provenance", help="source track type or transcript publisher")
    parser.add_argument("--duration", type=float, help="recording duration in seconds for start-only JSON")
    args = parser.parse_args()
    try:
        files = export(args)
    except (ValueError, OSError, ImportError) as error:
        parser.exit(1, f"Export failed: {error}\n")
    for path in files:
        print(path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
