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
- health: 54

## Latency

- first_final_elapsed_sec: 5.165
- translation_latency_sec.min: 0.550
- translation_latency_sec.p50: 1.182
- translation_latency_sec.p95: 2.060
- translation_latency_sec.max: 2.571

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
- LRC: 很抱歉打扰了您的工作 / Modal: 對不起，主人。 / quality=near
- LRC: 太过努力也不太好 / Modal: 不可過度為難自己。 / quality=near
- LRC: 我来为您泡盏红茶 / Modal: 需要 / quality=near

## Slowest Translation Latencies

- seq=42: 2.571s
- seq=49: 2.060s
- seq=21: 1.999s
- seq=14: 1.944s
- seq=57: 1.710s

## Known Issues

- unexpected WebSocket close code: 1006
