from __future__ import annotations


def _srt_time(seconds: float) -> str:
    millis = int(round(max(0.0, seconds) * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _vtt_time(seconds: float) -> str:
    return _srt_time(seconds).replace(",", ".")


def _cue_text(segment: dict[str, object]) -> str:
    text = str(segment.get("text") or "").strip()
    translation = str(segment.get("translation") or "").strip()
    if text and translation:
        return f"{text}\n{translation}"
    return text or translation


def to_srt(segments: list[dict[str, object]]) -> str:
    blocks: list[str] = []
    for index, segment in enumerate(segments, start=1):
        t0 = float(segment.get("t0") or 0.0)
        t1 = float(segment.get("t1") or max(t0 + 1.0, 1.0))
        blocks.append(f"{index}\n{_srt_time(t0)} --> {_srt_time(t1)}\n{_cue_text(segment)}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def to_vtt(segments: list[dict[str, object]]) -> str:
    blocks = ["WEBVTT", ""]
    for segment in segments:
        t0 = float(segment.get("t0") or 0.0)
        t1 = float(segment.get("t1") or max(t0 + 1.0, 1.0))
        blocks.append(f"{_vtt_time(t0)} --> {_vtt_time(t1)}\n{_cue_text(segment)}")
        blocks.append("")
    return "\n".join(blocks)
