"""Restore Chinese punctuation while retaining the original transcript text."""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import tarfile
from tempfile import TemporaryDirectory
from urllib.request import urlopen


MODEL_NAME = "sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12-int8"
MODEL_URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/punctuation-models/{MODEL_NAME}.tar.bz2"
MODEL_FILENAME = "model.int8.onnx"
MARKS = frozenset("，。？！；：、,.?!;:")
SENTENCE_END = ("。", "？", "！", ".", "?", "!")
CHINESE_MARKS = str.maketrans(",.?!;:", "，。？！；：")


def join_text(left: str, right: str) -> str:
    if re.search(r"[A-Za-z0-9,;:.!?]$", left) and re.match(r"[A-Za-z0-9]", right):
        return f"{left} {right}"
    return left + right


def text_and_marks(text: str) -> tuple[str, dict[int, str]]:
    characters = []
    marks = {}
    for character in text:
        if character in MARKS:
            if characters:
                marks[len(characters)] = character
        elif not character.isspace():
            characters.append(character)
    return "".join(characters), marks


def restore_lines(lines: list[str], predict, *, ends_at_pause: bool) -> list[str]:
    """Project the model's additions onto the original timed lines."""
    text = ""
    for line in lines:
        text = join_text(text, line)
    original, existing = text_and_marks(text)
    if not original:
        return lines
    predicted, marks = text_and_marks(predict(text))
    if predicted != original:
        return lines
    if not ends_at_pause and marks.get(len(original), "").endswith(SENTENCE_END):
        marks.pop(len(original))

    restored = []
    position = 0
    for line in lines:
        output = []
        for index, character in enumerate(line):
            output.append(character)
            if character in MARKS or character.isspace():
                continue
            position += 1
            if position not in marks or position in existing:
                continue
            following = line[index + 1:index + 2]
            if re.fullmatch("[A-Za-z0-9]", character) and re.fullmatch("[A-Za-z0-9]", following):
                continue
            output.append(marks[position].translate(CHINESE_MARKS))
        restored.append("".join(output))
    return restored


def get_model(cache_dir: Path) -> Path:
    target = cache_dir / MODEL_NAME / MODEL_FILENAME
    if target.is_file():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".punctuation-", dir=target.parent) as temporary:
        staged = Path(temporary) / MODEL_FILENAME
        with urlopen(MODEL_URL, timeout=30) as response, tarfile.open(fileobj=response, mode="r|bz2") as archive:
            for member in archive:
                if member.name.lstrip("./") != f"{MODEL_NAME}/{MODEL_FILENAME}" or not member.isfile():
                    continue
                with archive.extractfile(member) as model, staged.open("wb") as output:
                    shutil.copyfileobj(model, output)
                break
        if not staged.is_file():
            raise ValueError("标点模型压缩包内没有找到模型文件。")
        staged.replace(target)
    return target


def load_predictor(model: Path, threads: int):
    import sherpa_onnx

    if not model.is_file():
        raise ValueError("指定的标点模型文件不存在。")
    config = sherpa_onnx.OfflinePunctuationConfig(
        model=sherpa_onnx.OfflinePunctuationModelConfig(
            ct_transformer=str(model), num_threads=min(threads, 4)
        )
    )
    return sherpa_onnx.OfflinePunctuation(config).add_punctuation
