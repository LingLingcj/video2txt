# Extraction and export

## Start with captions

Use the exact, single-video URL. Look for a subtitle or transcript export on the original page, including the organizer's published timed data. Verify the video ID and timing against the clip. A prose summary can help locate a talk, but it cannot supply caption times.

For a supported video site, use the installed yt-dlp with configuration disabled to avoid importing unrelated local settings. List the tracks before selecting a language. On YouTube, `en` can be a publisher track, `en-orig` is the original-language automatic English track when offered, and translated tracks can use the same language label. Check the track list in each case.

```bash
python -m yt_dlp --ignore-config --no-playlist --list-subs "VIDEO_URL"
python -m yt_dlp --ignore-config --no-playlist --skip-download --write-subs --sub-langs "en" --sub-format "srt/vtt" -o "work/captions.%(ext)s" "VIDEO_URL"
python -m yt_dlp --ignore-config --no-playlist --skip-download --write-auto-subs --sub-langs "en-orig" --sub-format "srt/vtt" -o "work/captions.%(ext)s" "VIDEO_URL"
```

Run the download command matching the chosen track. Where YouTube needs a JavaScript runtime, follow [yt-dlp's runtime setup](https://github.com/yt-dlp/yt-dlp/wiki/EJS). For example, select an already installed compatible Node.js with `--js-runtimes node`. A warning about media formats does not establish that caption extraction failed. Check the actual file and cue coverage. If the direct route fails, check the organizer's published export or another official edition before switching to audio.

## Export and verify

`scripts/export_captions.py` accepts SRT, VTT, or timed JSON. SRT input is copied byte for byte. The reading copy groups adjacent cues and keeps their words in order. VTT and JSON are converted to SRT. The script requires Python 3.10 or newer. Install `pysubs2` in the working environment for SRT or VTT input.

```bash
python "<skill-folder>/scripts/export_captions.py" "work/captions.en.srt" \
  --title "Recording title" --source "VIDEO_URL" \
  --provenance "Publisher-provided English captions" --out-dir "outputs" --name "recording.en"
```

JSON input uses an array of objects with `startMs`, `text`, and optionally `endMs`. An object containing `segments` or `transcript.segments` also works. For a start-only export, each missing end uses the next start, with the final end bounded by four seconds and by `--duration` in seconds when the recording duration is known. The TXT records that the resulting end times are inferred. Separate an entire livestream's times from a standalone clip's times before exporting.

Check that the subtitle file opens, that times are ordered, and that the first and last speech match the expected edition. A gap around a bumper, credits, or outro can be normal. Preserve intentional overlapping cues and avoid guessing speaker names or removing repeated speech. Spot-check punctuation and proper names in an automatic track before describing its quality.

## Transcribe from audio when needed

Use an available local transcription tool. If a `video2txt` checkout is available, its default consumes the audio of a video URL or a local media file. Run from that checkout so its dependencies and punctuation module resolve.

```bash
python transcribe.py "VIDEO_URL_OR_LOCAL_MEDIA" --out-dir "OUTPUT_DIRECTORY"
```

An explicit language can help when the user specifies it. For Chinese speech, the bundled CT-Transformer punctuation pass preserves the recognized words and cue boundaries. Punctuation is estimated. If the pass cannot run, maintain the original short, timestamped breaks so missing punctuation cannot glue the text together.

If only a local ASR engine is available, obtain the accessible audio with the site's supported tool, or pass the user-provided media directly. Export speech segments with their original start and end values, then format the reading copy. Keep the final deliverable names and links tied to the exact recording used.
