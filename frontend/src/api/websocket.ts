import type { BridgeEvent, DotState } from '@/types';

export interface BridgeSocketCallbacks {
  onState: (text: string, dot: DotState) => void;
  onLog: (line: string) => void;
  onEvent: (event: BridgeEvent) => void;
  onBadJson: () => void;
}

export class BridgeSocket {
  private ws: WebSocket | null = null;
  private reconnectTimer = 0;
  private closedByUser = false;

  constructor(private readonly callbacks: BridgeSocketCallbacks) {}

  connect(): void {
    window.clearTimeout(this.reconnectTimer);
    this.closedByUser = false;
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    this.ws = new WebSocket(`${proto}//${location.host}/ws`);
    this.callbacks.onState('connecting', 'warn');
    this.ws.onopen = () => {
      this.callbacks.onState('open', 'ok');
    };
    this.ws.onerror = () => {
      if (this.closedByUser) return;
      this.callbacks.onState('error', 'bad');
      this.callbacks.onLog('WebSocket error');
    };
    this.ws.onclose = () => {
      if (this.closedByUser) return;
      this.callbacks.onState('closed', 'bad');
      this.reconnectTimer = window.setTimeout(() => this.connect(), 1500);
    };
    this.ws.onmessage = (ev) => {
      try {
        this.callbacks.onEvent(JSON.parse(ev.data as string) as BridgeEvent);
      } catch {
        this.callbacks.onBadJson();
        this.callbacks.onLog('Bad WebSocket JSON');
      }
    };
  }

  close(): void {
    window.clearTimeout(this.reconnectTimer);
    this.closedByUser = true;
    if (this.ws) {
      this.ws.onerror = null;
      this.ws.onclose = null;
      this.ws.close();
    }
    this.ws = null;
  }
}
