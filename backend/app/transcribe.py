"""Upload transcription and pasted-transcript fallback (TASKS.md task 6).

POST /api/transcribe: accepts an audio upload. WAV files go straight to the
Meta transcription model via ``app.meta_client.transcribe_wav``; anything else
is first converted to the required WAV (mono 16-bit PCM at 24 kHz) with ffmpeg.
Audio longer than 10 minutes is rejected with a clear 400 message, and the
model's millisecond ``turns`` are mapped to contract ``speakers`` + ``segments``
(seconds).

POST /api/transcript: fallback for pasted transcript text in the format of
``fixtures/sample_transcript.txt`` ("[MM:SS] Speaker: words", one turn per
line). Parsed locally with no model call.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import PurePath

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.meta_client import MetaClientError, TranscriptionTurn, transcribe_wav
from app.schemas import Segment, Speaker

router = APIRouter()

MAX_AUDIO_SECONDS = 600  # transcription takes WAV only, up to 10 minutes
MAX_AUDIO_BYTES = 32 * 1024 * 1024  # transcription request body max 32 MB
TARGET_SAMPLE_RATE = 24000  # the model's native rate; 16 kHz is resampled server-side
WAV_CONTENT_TYPES = {"audio/wav", "audio/x-wav", "audio/vnd.wave", "audio/wave"}
EXPECTED_TRANSCRIPT_FORMAT = "'[MM:SS] Speaker: words', one turn per line"


class FfmpegMissingError(RuntimeError):
    """ffmpeg is needed for conversion but is not installed."""


class AudioConversionError(RuntimeError):
    """ffmpeg ran but the input could not be converted to WAV."""


class TranscriptResponse(BaseModel):
    """What both transcription endpoints return: speakers + segments only."""

    speakers: list[Speaker]
    segments: list[Segment]


class TranscriptRequest(BaseModel):
    """Pasted transcript text; ``transcript`` is accepted as an alias."""

    text: str | None = None
    transcript: str | None = None


def is_wav_bytes(data: bytes) -> bool:
    """True when the bytes carry a WAV (RIFF/WAVE) header."""
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def looks_like_wav(filename: str, content_type: str, data: bytes) -> bool:
    """Decide whether an upload can go to the model without ffmpeg."""
    if PurePath(filename or "").suffix.lower() == ".wav":
        return True
    if (content_type or "").split(";")[0].strip().lower() in WAV_CONTENT_TYPES:
        return True
    return is_wav_bytes(data)


def wav_duration_s(data: bytes) -> float:
    """Duration of WAV bytes in seconds; raises ValueError when not valid WAV."""
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            rate = wav.getframerate()
            frames = wav.getnframes()
            if rate <= 0 or frames < 0:
                raise ValueError(f"bad WAV header (rate={rate}, frames={frames})")
            return frames / float(rate)
    except (wave.Error, EOFError, ValueError) as exc:
        raise ValueError(
            "File is not a valid WAV file "
            f"({exc}); upload mono 16-bit PCM WAV at 16 or 24 kHz, "
            "or another audio format with ffmpeg installed."
        ) from exc


def too_long_message(seconds: float) -> str:
    """Clear rejection message for audio over the 10-minute model limit."""
    return (
        f"Audio is {seconds / 60:.1f} minutes long; the transcription model "
        "accepts at most 10 minutes. Upload a shorter clip."
    )


def convert_to_wav(data: bytes, suffix: str = "") -> bytes:
    """Convert uploaded audio to the required WAV with ffmpeg.

    Raises FfmpegMissingError (caller maps to a clear 400) or
    AudioConversionError when ffmpeg cannot convert the input.
    """
    label = suffix if suffix.startswith(".") else (f".{suffix}" if suffix else "")
    if shutil.which("ffmpeg") is None:
        raise FfmpegMissingError(
            f"ffmpeg is not installed, so this {label or 'audio'} file cannot "
            "be converted to WAV. Install ffmpeg "
            "(https://ffmpeg.org/download.html) and retry, "
            "or upload a WAV file instead (mono 16-bit PCM at 16 or 24 kHz)."
        )
    with tempfile.TemporaryDirectory(prefix="hypatia_") as tmp:
        src = os.path.join(tmp, f"input{label or '.bin'}")
        dst = os.path.join(tmp, "output.wav")
        with open(src, "wb") as handle:
            handle.write(data)
        try:
            proc = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", src,
                    "-ac", "1", "-ar", str(TARGET_SAMPLE_RATE),
                    "-c:a", "pcm_s16le", "-map_metadata", "-1", dst,
                ],
                capture_output=True,
                timeout=300,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AudioConversionError(
                f"Could not convert {label or 'audio'} to WAV with ffmpeg: {exc}. "
                "Upload a WAV file instead (mono 16-bit PCM at 16 or 24 kHz)."
            ) from exc
        if proc.returncode != 0:
            detail = (proc.stderr or b"").decode("utf-8", "replace")[-500:].strip()
            raise AudioConversionError(
                f"Could not convert {label or 'audio'} to WAV with ffmpeg"
                f" (ffmpeg said: {detail}). "
                "Upload a WAV file instead (mono 16-bit PCM at 16 or 24 kHz)."
            )
        try:
            with open(dst, "rb") as handle:
                return handle.read()
        except OSError as exc:
            raise AudioConversionError(
                f"ffmpeg produced no WAV output for {label or 'audio'}: {exc}."
            ) from exc


def turns_to_transcript(
    turns: list[TranscriptionTurn],
) -> tuple[list[Speaker], list[Segment]]:
    """Map model ``turns`` (integer ms, per-request labels) to the contract.

    Speakers are numbered S1, S2, ... in order of first appearance with labels
    "Speaker 1", "Speaker 2", ...; times are converted from ms to seconds.
    Empty turns carry no speech and are dropped. A turn the model never
    attributed (no ``speaker``) inherits the previous speaker, or the next
    attributed one when it comes first, so a stray fragment such as "well"
    cannot fail the whole transcription.
    """
    kept = [turn for turn in turns if turn.transcript.strip()]
    # Next attributed speaker at or after each position, for leading gaps.
    next_speaker: list[str | None] = [None] * len(kept)
    upcoming: str | None = None
    for index in range(len(kept) - 1, -1, -1):
        if kept[index].speaker:
            upcoming = kept[index].speaker
        next_speaker[index] = upcoming
    speaker_ids: dict[str, str] = {}
    speakers: list[Speaker] = []
    segments: list[Segment] = []
    previous: str | None = None
    for index, turn in enumerate(kept):
        speaker = turn.speaker or previous or next_speaker[index] or "unknown"
        previous = speaker
        if speaker not in speaker_ids:
            number = len(speakers) + 1
            speaker_id = f"S{number}"
            speaker_ids[speaker] = speaker_id
            speakers.append(Speaker(id=speaker_id, label=f"Speaker {number}"))
        segments.append(
            Segment(
                id=f"seg_{len(segments) + 1}",
                speaker=speaker_ids[speaker],
                start=turn.startMs / 1000.0,
                end=turn.endMs / 1000.0,
                text=turn.transcript,
            )
        )
    return speakers, segments


_TIMESTAMP_RE = re.compile(
    r"^\s*\[(?:(\d+):)?(\d{1,3}):(\d{2}(?:\.\d+)?)\]\s*"
    r"(?:([^:\[\]]+):\s*)?(.+?)\s*$"
)
_SPEAKER_NUMBER_RE = re.compile(r"(?i)^\s*speaker\s+(\d+)\s*$")


def _parse_timestamp(hours: str | None, minutes: str, seconds: str, line_no: int) -> float:
    minute_value = int(minutes)
    second_value = float(seconds)
    if second_value >= 60.0:
        raise ValueError(
            f"Line {line_no}: bad timestamp (seconds must be below 60); "
            f"expected format {EXPECTED_TRANSCRIPT_FORMAT}."
        )
    if hours is not None:
        if minute_value >= 60:
            raise ValueError(
                f"Line {line_no}: bad timestamp (minutes must be below 60 "
                f"when hours are given); expected format {EXPECTED_TRANSCRIPT_FORMAT}."
            )
        return int(hours) * 3600 + minute_value * 60 + second_value
    return minute_value * 60 + second_value


def _assign_speaker_ids(labels: list[str]) -> dict[str, Speaker]:
    """Numbered 'Speaker N' labels keep their number; others get free S ids."""
    speakers: dict[str, Speaker] = {}
    used: set[str] = set()
    numbered: list[str] = []
    generic: list[str] = []
    for label in labels:
        match = _SPEAKER_NUMBER_RE.match(label)
        (numbered if match else generic).append(label)
    for label in numbered:
        number = int(_SPEAKER_NUMBER_RE.match(label).group(1))  # type: ignore[union-attr]
        candidate = f"S{number}"
        if candidate in used:
            generic.append(label)
            continue
        used.add(candidate)
        speakers[label] = Speaker(id=candidate, label=f"Speaker {number}")
    next_free = 1
    for label in generic:
        while f"S{next_free}" in used:
            next_free += 1
        speaker_id = f"S{next_free}"
        used.add(speaker_id)
        speakers[label] = Speaker(id=speaker_id, label=label)
    return speakers


def parse_transcript_text(text: str) -> tuple[list[Speaker], list[Segment]]:
    """Parse pasted transcript text into contract speakers + segments.

    Format (``fixtures/sample_transcript.txt``): ``[MM:SS] Speaker: words``,
    one turn per line. Each segment ends where the next one starts; the last
    segment's length is estimated from its word count. Raises ValueError with
    a clear message on empty or malformed input. No model call is involved.
    """
    lines = (text or "").splitlines()
    parsed: list[tuple[int, float, str, str]] = []
    for line_no, raw_line in enumerate(lines, start=1):
        if not raw_line.strip():
            continue
        match = _TIMESTAMP_RE.match(raw_line)
        if match is None or not match.group(5).strip():
            raise ValueError(
                f"Line {line_no}: cannot parse {raw_line.strip()!r}; expected "
                f"format {EXPECTED_TRANSCRIPT_FORMAT}."
            )
        hours, minutes, seconds, speaker, words = match.groups()
        label = speaker.strip() if speaker else "Speaker 1"
        parsed.append((line_no, _parse_timestamp(hours, minutes, seconds, line_no), label, words.strip()))
    if not parsed:
        raise ValueError(
            "No transcript turns found; paste text in the format "
            f"{EXPECTED_TRANSCRIPT_FORMAT}."
        )
    for (line_no, start, _, _), (_, following, _, _) in zip(parsed, parsed[1:]):
        if following < start:
            raise ValueError(
                f"Line {line_no}: timestamps must be in order "
                f"({start:.1f}s is followed by {following:.1f}s); expected "
                f"format {EXPECTED_TRANSCRIPT_FORMAT}."
            )
    labels_in_order: list[str] = []
    for _, _, label, _ in parsed:
        if label not in labels_in_order:
            labels_in_order.append(label)
    by_label = _assign_speaker_ids(labels_in_order)
    speakers = [by_label[label] for label in labels_in_order]
    segments: list[Segment] = []
    for index, (_, start, label, words) in enumerate(parsed):
        if index + 1 < len(parsed):
            end = parsed[index + 1][1]
        else:
            end = start + max(3.0, len(words.split()) / 2.5)
        segments.append(
            Segment(
                id=f"seg_{index + 1}",
                speaker=by_label[label].id,
                start=start,
                end=end,
                text=words,
            )
        )
    return speakers, segments


def _map_meta_error(exc: MetaClientError) -> HTTPException:
    """Map a transcription failure to an HTTP error with a clear message."""
    message = str(exc)
    if "429" in message:
        return HTTPException(
            status_code=429,
            detail=f"Transcription is rate-limited, retry later: {message}",
        )
    if "413" in message:
        return HTTPException(
            status_code=413,
            detail=f"Audio is too large for transcription (max 32 MB): {message}",
        )
    if "400" in message or "Bad Request" in message:
        return HTTPException(
            status_code=400,
            detail=f"Transcription rejected the audio: {message}",
        )
    return HTTPException(status_code=502, detail=f"Transcription failed: {message}")


@router.post("/api/transcribe", response_model=TranscriptResponse)
async def post_transcribe(file: UploadFile = File(...)) -> TranscriptResponse:
    """Transcribe an uploaded audio file via the Meta transcription model."""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    filename = file.filename or "audio"
    content_type = (file.content_type or "").lower()
    suffix = PurePath(filename).suffix.lower()
    if looks_like_wav(filename, content_type, raw):
        try:
            duration_s = wav_duration_s(raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if duration_s > MAX_AUDIO_SECONDS:
            raise HTTPException(status_code=400, detail=too_long_message(duration_s))
        wav_bytes = raw
    else:
        try:
            wav_bytes = convert_to_wav(raw, suffix)
        except FfmpegMissingError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except AudioConversionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            duration_s = wav_duration_s(wav_bytes)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if duration_s > MAX_AUDIO_SECONDS:
            raise HTTPException(status_code=400, detail=too_long_message(duration_s))
    if len(wav_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Audio file is {len(wav_bytes) / (1024 * 1024):.1f} MB; "
                "the maximum upload size is 32 MB. Upload a shorter clip."
            ),
        )
    upload_name = filename if filename.lower().endswith(".wav") else "audio.wav"
    try:
        result = transcribe_wav(wav_bytes, filename=upload_name)
    except MetaClientError as exc:
        raise _map_meta_error(exc) from exc
    if result.audioDurationMs > MAX_AUDIO_SECONDS * 1000:
        raise HTTPException(
            status_code=400,
            detail=too_long_message(result.audioDurationMs / 1000.0),
        )
    speakers, segments = turns_to_transcript(result.turns)
    return TranscriptResponse(speakers=speakers, segments=segments)


@router.post("/api/transcript", response_model=TranscriptResponse)
def post_transcript(body: TranscriptRequest) -> TranscriptResponse:
    """Parse pasted transcript text locally (no model call)."""
    raw = body.text if body.text is not None else body.transcript
    if raw is None or not raw.strip():
        raise HTTPException(
            status_code=400,
            detail=(
                "Paste transcript text in the request body as 'text' "
                f"(format {EXPECTED_TRANSCRIPT_FORMAT})."
            ),
        )
    try:
        speakers, segments = parse_transcript_text(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TranscriptResponse(speakers=speakers, segments=segments)
