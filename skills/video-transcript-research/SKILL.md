---
name: video-transcript-research
description: Find original videos for a speaker, interview, talk, or topic and extract timestamped subtitles or transcripts. Use when the user asks to identify a recent video, collect several relevant interviews, download captions, or turn a video or audio file into a searchable transcript.
---

# Video transcript research

## Find the recording

- Start from the link, speaker, or topic the user gives. Resolve nicknames and ambiguous titles using the speaker, organizer, or publisher. Check that the identified person appears in the chosen recording.
- Prefer the publisher's full recording or official event page. For recent material, distinguish when it was recorded from when it was uploaded or republished. Match the transcript to the exact video ID or edition. A podcast feed, full-day stream, and standalone clip can carry different timestamps.
- For several results, choose distinct topics that fit the request. Report the original links, duration, and why each recording fits. Search-only requests can end with the shortlist.
- When two recordings plausibly fit an extraction request, use the strongest match and state the assumption. Ask only if the missing distinction materially affects which recording to process.

## Get usable text

1. When the user asks to extract subtitles, check the organizer's timed export and the platform's original-language subtitle tracks. Prefer a suitable published track. Label automatic captions, translations, and revised transcript editions accurately.
2. When the user supplies only media or requests a fresh audio transcription, use its audio and a local speech model. If a caption extraction request has no usable track, use the same audio workflow and label the result as ASR. Read [the extraction and export reference](references/extraction.md) for tool choices and commands.
3. Preserve spoken wording and source timing. Add punctuation as a separate pass when needed. Reject punctuation predictions that change the words, and keep short timestamped lines when punctuation is sparse. Verify cues and playback coverage before calling the result complete.

## Deliver the result

- Save the original or converted SRT and, when useful for reading or analysis, a timestamped TXT. Use the requested language, or preserve the spoken language if the user leaves it unspecified. Read [the extraction and export reference](references/extraction.md) when preparing files with the exporter.
- Link the recording and each file. Say where the text came from and whether timing was inferred or speech was machine-transcribed. Keep source details in the TXT so the file makes sense on its own.
