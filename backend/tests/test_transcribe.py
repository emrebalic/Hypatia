"""Offline tests for POST /api/transcribe and POST /api/transcript.

The Meta transcription model is faked (app.transcribe.transcribe_wav is
patched); ffmpeg-dependent paths patch app.transcribe.convert_to_wav or
shutil.which so no binary or network is needed.
"""

import io
import shutil
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import transcribe as tmod
from app.main import app
from app.meta_client import TranscriptionResult
from app.schemas import Segment, Speaker

client = TestClient(app)

FIXTURE_TRANSCRIPT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "sample_transcript.txt"
)
EXPECTED_STARTS = [0.0, 9.0, 17.0, 26.0, 34.0, 41.0, 49.0, 57.0, 62.0, 68.0, 77.0]


def _wav_bytes(seconds: float = 1.0, framerate: int = 16000) -> bytes:
    buf = io.BytesIO()
    frames = int(seconds * framerate)
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(framerate)
        wav.writeframes(b"\x00\x00" * frames)
    return buf.getvalue()


def _canned_result(**overrides) -> TranscriptionResult:
    payload = {
        "sessionId": "sess_1",
        "transcript": "Hello here. Hi there.",
        "audioDurationMs": 9250,
        "turns": [
            {
                "turnId": "t1",
                "startMs": 0,
                "endMs": 4500,
                "transcript": "Hello here.",
                "speaker": "A",
            },
            {
                "turnId": "t2",
                "startMs": 4500,
                "endMs": 9250,
                "transcript": "Hi there.",
                "speaker": "B",
            },
        ],
    }
    payload.update(overrides)
    return TranscriptionResult.model_validate(payload)


def _fake_transcribe_factory(canned, calls):
    def fake_transcribe(audio_wav, *, filename="audio.wav", **kwargs):
        calls["audio_wav"] = audio_wav
        calls["filename"] = filename
        return canned

    return fake_transcribe


def test_transcribe_wav_upload_maps_turns_to_segments(monkeypatch):
    calls: dict = {}
    monkeypatch.setattr(
        tmod, "transcribe_wav", _fake_transcribe_factory(_canned_result(), calls)
    )
    wav = _wav_bytes()
    response = client.post(
        "/api/transcribe", files={"file": ("debate.wav", wav, "audio/wav")}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["speakers"] == [
        {"id": "S1", "label": "Speaker 1"},
        {"id": "S2", "label": "Speaker 2"},
    ]
    assert [s["id"] for s in body["segments"]] == ["seg_1", "seg_2"]
    assert [s["speaker"] for s in body["segments"]] == ["S1", "S2"]
    # ms converted to seconds, including fractional values.
    assert [s["start"] for s in body["segments"]] == [0.0, 4.5]
    assert [s["end"] for s in body["segments"]] == [4.5, 9.25]
    assert [s["text"] for s in body["segments"]] == ["Hello here.", "Hi there."]
    # The raw WAV bytes (not re-encoded) reach the model.
    assert calls["audio_wav"] == wav
    assert calls["filename"] == "debate.wav"
    # Response matches the contract models.
    for speaker in body["speakers"]:
        Speaker.model_validate(speaker)
    for segment in body["segments"]:
        Segment.model_validate(segment)


def test_transcribe_repeated_speaker_keeps_first_numbering(monkeypatch):
    canned = _canned_result(
        turns=[
            {"turnId": "t1", "startMs": 0, "endMs": 1000, "transcript": "A.", "speaker": "B"},
            {"turnId": "t2", "startMs": 1000, "endMs": 2000, "transcript": "B.", "speaker": "A"},
            {"turnId": "t3", "startMs": 2000, "endMs": 3000, "transcript": "C.", "speaker": "B"},
        ]
    )
    monkeypatch.setattr(tmod, "transcribe_wav", _fake_transcribe_factory(canned, {}))
    response = client.post(
        "/api/transcribe", files={"file": ("debate.wav", _wav_bytes(), "audio/wav")}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [s["speaker"] for s in body["segments"]] == ["S1", "S2", "S1"]
    assert [s["id"] for s in body["speakers"]] == ["S1", "S2"]


def test_turns_to_transcript_inherits_missing_speaker_and_drops_empty():
    # Regression (Emre, 5-min m4a): turns without `speaker` used to fail
    # validation for the whole file. Empty turns are dropped; unattributed
    # fragments inherit the previous speaker (a leading one, the next).
    canned = _canned_result(
        turns=[
            {"turnId": 22, "startMs": 0, "endMs": 100, "transcript": ""},
            {"turnId": 30, "startMs": 100, "endMs": 200, "transcript": "well"},
            {
                "turnId": 31,
                "startMs": 200,
                "endMs": 1000,
                "transcript": "Remote work should be the default.",
                "speaker": "B",
            },
            {"turnId": 35, "startMs": 1000, "endMs": 1200, "transcript": "They"},
            {
                "turnId": 36,
                "startMs": 1200,
                "endMs": 2000,
                "transcript": "I disagree.",
                "speaker": "A",
            },
        ]
    )
    speakers, segments = tmod.turns_to_transcript(canned.turns)
    assert [segment.text for segment in segments] == [
        "well",
        "Remote work should be the default.",
        "They",
        "I disagree.",
    ]
    assert [segment.id for segment in segments] == ["seg_1", "seg_2", "seg_3", "seg_4"]
    # "well" takes the next attributed speaker (B -> S1); "They" keeps the
    # previous one; "I disagree." is the second distinct speaker.
    assert [segment.speaker for segment in segments] == ["S1", "S1", "S1", "S2"]
    assert [speaker.id for speaker in speakers] == ["S1", "S2"]


def test_transcribe_converts_non_wav_with_ffmpeg(monkeypatch):
    calls: dict = {}
    wav = _wav_bytes()
    converted = {"bytes": wav}

    def fake_convert(data: bytes, suffix: str = "") -> bytes:
        converted["input"] = data
        converted["suffix"] = suffix
        return converted["bytes"]

    monkeypatch.setattr(tmod, "convert_to_wav", fake_convert)
    monkeypatch.setattr(
        tmod, "transcribe_wav", _fake_transcribe_factory(_canned_result(), calls)
    )
    response = client.post(
        "/api/transcribe",
        files={"file": ("clip.mp3", b"ID3\x04fake-mp3-bytes", "audio/mpeg")},
    )
    assert response.status_code == 200, response.text
    assert converted["input"] == b"ID3\x04fake-mp3-bytes"
    assert converted["suffix"] == ".mp3"
    assert calls["audio_wav"] == wav
    assert calls["filename"] == "audio.wav"


def test_transcribe_non_wav_without_ffmpeg_is_clear_400(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda *args, **kwargs: None)
    response = client.post(
        "/api/transcribe",
        files={"file": ("clip.m4a", b"fake-m4a-bytes", "audio/mp4")},
    )
    assert response.status_code == 400, response.text
    assert "ffmpeg" in response.json()["detail"].lower()


def test_convert_to_wav_reports_ffmpeg_suffix_in_error(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda *args, **kwargs: None)
    with pytest.raises(tmod.FfmpegMissingError, match="(?i)ffmpeg"):
        tmod.convert_to_wav(b"fake", ".m4a")


def test_transcribe_rejects_audio_over_10_minutes(monkeypatch):
    monkeypatch.setattr(tmod, "wav_duration_s", lambda data: 660.0)
    response = client.post(
        "/api/transcribe", files={"file": ("long.wav", _wav_bytes(), "audio/wav")}
    )
    assert response.status_code == 400, response.text
    assert "10 minute" in response.json()["detail"]


def test_transcribe_rejects_long_audio_reported_by_model(monkeypatch):
    canned = _canned_result(audioDurationMs=660000)
    monkeypatch.setattr(tmod, "transcribe_wav", _fake_transcribe_factory(canned, {}))
    response = client.post(
        "/api/transcribe", files={"file": ("long.wav", _wav_bytes(), "audio/wav")}
    )
    assert response.status_code == 400, response.text
    assert "10 minute" in response.json()["detail"]


def test_transcribe_rejects_empty_upload():
    response = client.post(
        "/api/transcribe", files={"file": ("empty.wav", b"", "audio/wav")}
    )
    assert response.status_code == 400, response.text


def test_transcribe_rejects_invalid_wav():
    response = client.post(
        "/api/transcribe",
        files={"file": ("broken.wav", b"not really wav data", "audio/wav")},
    )
    assert response.status_code == 400, response.text


def test_transcript_parses_sample_fixture_without_model(monkeypatch):
    def refuse_transcribe(*args, **kwargs):
        raise AssertionError("parse path must not call the model")

    monkeypatch.setattr(tmod, "transcribe_wav", refuse_transcribe)
    text = FIXTURE_TRANSCRIPT.read_text(encoding="utf-8")
    response = client.post("/api/transcript", json={"text": text})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["speakers"] == [
        {"id": "S1", "label": "Speaker 1"},
        {"id": "S2", "label": "Speaker 2"},
    ]
    assert len(body["segments"]) == 11
    assert [s["id"] for s in body["segments"]] == [f"seg_{i}" for i in range(1, 12)]
    assert [s["start"] for s in body["segments"]] == EXPECTED_STARTS
    # Each segment ends where the next one starts; the last one extends past.
    ends = [s["end"] for s in body["segments"]]
    assert ends[:-1] == EXPECTED_STARTS[1:]
    assert ends[-1] > EXPECTED_STARTS[-1]
    assert body["segments"][0]["speaker"] == "S1"
    assert body["segments"][1]["speaker"] == "S2"
    assert body["segments"][0]["text"].startswith("Remote work should be the default")
    speaker_ids = {s["id"] for s in body["speakers"]}
    for segment in body["segments"]:
        Segment.model_validate(segment)
        assert segment["speaker"] in speaker_ids


def test_transcript_accepts_transcript_alias():
    text = FIXTURE_TRANSCRIPT.read_text(encoding="utf-8")
    response = client.post("/api/transcript", json={"transcript": text})
    assert response.status_code == 200, response.text
    assert len(response.json()["segments"]) == 11


def test_transcript_rejects_malformed_line():
    response = client.post(
        "/api/transcript", json={"text": "just some words without a timestamp"}
    )
    assert response.status_code == 400, response.text


def test_transcript_rejects_empty_text():
    assert client.post("/api/transcript", json={"text": "   \n "}).status_code == 400
    assert client.post("/api/transcript", json={}).status_code == 400


def test_transcript_rejects_decreasing_timestamps():
    text = "[00:09] Speaker 1: Second line first.\n[00:00] Speaker 2: Earlier time."
    response = client.post("/api/transcript", json={"text": text})
    assert response.status_code == 400, response.text
