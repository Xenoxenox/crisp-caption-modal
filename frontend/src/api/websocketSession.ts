import { PCM_WORKLET_SOURCE } from '@/audio/pcm-worklet';
import { useBridgeStore } from '@/stores/bridge';

import type { BridgeEvent } from '@/types';
import type { CaptureCallbacks } from './webrtc';

function endpointWithToken(endpoint: string, token: string): string {
  const url = new URL(endpoint);
  url.searchParams.set('token', token);
  return url.toString();
}

export class WebSocketSession {
  private ws: WebSocket | null = null;
  private activeStream: MediaStream | null = null;
  private audioContext: AudioContext | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private workletNode: AudioWorkletNode | null = null;
  private monitorGain: GainNode | null = null;
  private workletUrl = '';
  private stopping = false;

  constructor(
    private readonly endpointUrl: string,
    private readonly token: string,
    private readonly callbacks: CaptureCallbacks,
  ) {}

  async startDisplay(): Promise<void> {
    const stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true });
    await this.connectWithStream(stream, 'tab audio');
  }

  async startMicrophone(): Promise<void> {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    await this.connectWithStream(stream, 'microphone');
  }

  stop(): void {
    this.stopping = true;
    this.workletNode?.disconnect();
    this.sourceNode?.disconnect();
    this.monitorGain?.disconnect();
    this.workletNode = null;
    this.sourceNode = null;
    this.monitorGain = null;
    if (this.audioContext && this.audioContext.state !== 'closed') {
      void this.audioContext.close();
    }
    this.audioContext = null;
    if (this.workletUrl) {
      URL.revokeObjectURL(this.workletUrl);
      this.workletUrl = '';
    }
    if (this.activeStream) {
      this.activeStream.getTracks().forEach((track) => track.stop());
      this.activeStream = null;
    }
    if (this.ws && this.ws.readyState < WebSocket.CLOSING) {
      this.ws.close();
    }
    this.ws = null;
    this.callbacks.onSessionLabel('No active capture');
    this.callbacks.onRtcState('idle', '');
    this.callbacks.onAudioState('none', '');
  }

  private async connectWithStream(stream: MediaStream, label: string): Promise<void> {
    this.stop();
    this.stopping = false;
    if (!this.endpointUrl.trim()) throw new Error('Modal endpoint URL is empty.');
    if (!this.token.trim()) throw new Error('Modal token is empty.');

    const audioTracks = stream.getAudioTracks();
    if (!audioTracks.length) {
      stream.getTracks().forEach((track) => track.stop());
      throw new Error('No audio track was selected.');
    }

    this.activeStream = stream;
    this.callbacks.onAudioState(label, 'ok');
    this.callbacks.onRtcState('connecting', 'warn');
    this.callbacks.onSessionLabel(`Capturing ${label} via Modal`);

    const ws = new WebSocket(endpointWithToken(this.endpointUrl, this.token));
    ws.binaryType = 'arraybuffer';
    this.ws = ws;
    await new Promise<void>((resolve, reject) => {
      ws.onopen = () => resolve();
      ws.onerror = () => reject(new Error('Modal WebSocket connection failed.'));
      ws.onclose = (event) =>
        reject(new Error(`Modal WebSocket closed: ${event.code || 'unknown'}`));
    });

    const bridge = useBridgeStore();
    ws.onmessage = (event) => {
      try {
        bridge.handleBridgeEvent(JSON.parse(event.data as string) as BridgeEvent);
      } catch {
        bridge.incrementError();
        this.callbacks.onLog('Bad Modal WebSocket JSON');
      }
    };
    ws.onerror = () => {
      this.callbacks.onRtcState('failed', 'bad');
      this.callbacks.onLog('Modal WebSocket error');
    };
    ws.onclose = (event) => {
      if (this.stopping) return;
      if (event.code !== 1000) {
        this.callbacks.onRtcState('failed', 'bad');
        this.callbacks.onLog(`Modal WebSocket closed: ${event.code || 'unknown'}`);
      }
    };

    await this.startAudioWorklet(stream, ws);
    audioTracks[0].onended = () => {
      this.callbacks.onLog('Audio track ended');
      this.stop();
    };
    this.callbacks.onRtcState('connected', 'ok');
    this.callbacks.onLog(`Modal capture connected: ${label}`);
  }

  private async startAudioWorklet(stream: MediaStream, ws: WebSocket): Promise<void> {
    const context = new AudioContext();
    this.audioContext = context;
    this.workletUrl = URL.createObjectURL(
      new Blob([PCM_WORKLET_SOURCE], { type: 'text/javascript' }),
    );
    await context.audioWorklet.addModule(this.workletUrl);
    this.sourceNode = context.createMediaStreamSource(stream);
    this.workletNode = new AudioWorkletNode(context, 'pcm-encoder');
    this.monitorGain = context.createGain();
    this.monitorGain.gain.value = 0;
    this.workletNode.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(event.data);
    };
    this.sourceNode.connect(this.workletNode);
    this.workletNode.connect(this.monitorGain);
    this.monitorGain.connect(context.destination);
  }
}
