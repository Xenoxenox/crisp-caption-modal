from __future__ import annotations


SAMPLE_RATE = 16000

CRISPASR_BIN = "/opt/crispasr/crispasr"
TRANSLATION_MODEL_PATH = "/models/translation/Hy-MT2-1.8B-Q4_K_M.gguf"
TRANSLATION_MODEL_ALIAS = "Hy-MT2-1.8B"

CRISP_ARGS_JA = [
    "--backend",
    "cohere",
    "-l",
    "ja",
    "-m",
    "/models/asr/cohere-asr-ja-v0.1-q4_k.gguf",
    "--stream-json",
    "--stream-final-mode",
    "redecode",
    "--stream-utterance-max-sec",
    "60",
    "--stream-final-on-silence-ms",
    "300",
    "--stream-vad-merge-gap-ms",
    "250",
    "--stream-length",
    "8000",
    "--stream-step",
    "750",
    "--stream-partial-decode-ms",
    "0",
    "--vad",
    "-vm",
    "/models/vad/firered-vad.gguf",
    "-vt",
    "0.70",
    "-vspd",
    "180",
    "-vsd",
    "330",
    "-vmsd",
    "10",
    "-vp",
    "110",
]


def crisp_args_for_profile(profile: str) -> list[str]:
    if profile != "ja":
        raise ValueError(f"Unsupported Modal transcription profile: {profile!r}")
    return list(CRISP_ARGS_JA)


def stream_step_bytes(extra: list[str], sample_rate: int = SAMPLE_RATE) -> int:
    step_ms = 3000
    for index, token in enumerate(extra):
        if token == "--stream-step" and index + 1 < len(extra):
            try:
                step_ms = max(1, int(extra[index + 1]))
            except ValueError:
                pass
            break
    return step_ms * sample_rate // 1000 * 2


def normalize_target_lang(target_lang: str) -> str:
    aliases = {
        "zh-TW": "繁體中文（台灣）",
        "zh-Hant": "繁體中文（台灣）",
        "zh-CN": "简体中文",
    }
    return aliases.get(target_lang, target_lang)
