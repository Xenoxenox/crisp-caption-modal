# Phase 2 Realtime Evaluation Result

## Test Range

- start_sec: 0.000
- end_sec: 180.000
- audio_seconds: 180.000
- chunk_ms: 750
- tail_silence_sec: 3.000

## Link

- endpoint: `wss://litardphobia--crisp-caption-runtime-realtime-service.modal.run/v1/realtime`
- git_head: `5d823af1dfd48fc373f62874bd32b78eeb12fa7d`
- token_source: `CRISP_API_TOKEN` / project `.env` / CLI override; value not recorded

## Event Counts

- partial: 54
- final: 26
- translation: 26
- translation_error: 0
- silence: 185
- health: 53

## Latency

- first_final_elapsed_sec: 5.247
- translation_latency_sec.min: 2.108
- translation_latency_sec.p50: 36.453
- translation_latency_sec.p95: 71.798
- translation_latency_sec.max: 75.932

## WebSocket Close

- close_code: 1006
- close_reason:

## Translation Errors

- None.

## LRC Alignment Summary

- lrc_total: 20
- matched_exact: 0
- matched_near: 15
- miss: 5
- extra: 11

## Samples

- LRC: 我进来了 / Modal: 不 / quality=near
- LRC: 打扰了 / Modal: 新鮮的。 / quality=near
- LRC: 很抱歉打扰了您的工作 / Modal: 對不起，主人大人。 / quality=near
- LRC: 太过努力也不太好 / Modal: 不可以過度為難自己。 / quality=near
- LRC: 我来为您泡盏红茶 / Modal: 需要 / quality=near

## Slowest Translation Latencies

- seq=59: 75.932s
- seq=61: 71.798s
- seq=71: 70.382s
- seq=67: 69.920s
- seq=65: 69.677s

## Known Issues

- translation latency p95 exceeded 10 seconds.
- unexpected WebSocket close code: 1006
