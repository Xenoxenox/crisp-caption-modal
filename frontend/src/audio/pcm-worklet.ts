export const PCM_WORKLET_SOURCE = `
class PcmEncoderProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.chunks = [];
    this.buffered = 0;
    this.frameSize = Math.max(1, Math.round(sampleRate * 0.03));
  }

  process(inputs) {
    const input = inputs[0];
    const channel = input && input[0];
    if (!channel || channel.length === 0) return true;

    const copy = new Float32Array(channel.length);
    copy.set(channel);
    this.chunks.push(copy);
    this.buffered += copy.length;

    while (this.buffered >= this.frameSize) {
      const frame = this.takeFrame(this.frameSize);
      const encoded = this.encodeFrame(frame);
      this.port.postMessage(encoded, [encoded]);
    }
    return true;
  }

  takeFrame(size) {
    const frame = new Float32Array(size);
    let written = 0;
    while (written < size && this.chunks.length) {
      const head = this.chunks[0];
      const need = size - written;
      if (head.length <= need) {
        frame.set(head, written);
        written += head.length;
        this.chunks.shift();
      } else {
        frame.set(head.subarray(0, need), written);
        this.chunks[0] = head.subarray(need);
        written += need;
      }
    }
    this.buffered -= size;
    return frame;
  }

  encodeFrame(frame) {
    const ratio = sampleRate / 16000;
    const outputLength = Math.max(1, Math.round(frame.length / ratio));
    const buffer = new ArrayBuffer(outputLength * 2);
    const view = new DataView(buffer);
    for (let index = 0; index < outputLength; index += 1) {
      const position = index * ratio;
      const leftIndex = Math.floor(position);
      const rightIndex = Math.min(leftIndex + 1, frame.length - 1);
      const weight = position - leftIndex;
      const sample = frame[leftIndex] + (frame[rightIndex] - frame[leftIndex]) * weight;
      const clamped = Math.max(-1, Math.min(1, sample));
      view.setInt16(index * 2, clamped < 0 ? clamped * 32768 : clamped * 32767, true);
    }
    return buffer;
  }
}

registerProcessor('pcm-encoder', PcmEncoderProcessor);
`;
