import { defineStore } from 'pinia';

import type {
  BridgeEvent,
  ConfigProfile,
  DotState,
  EndpointSettings,
  HealthEvent,
  Stats,
  TranscriptEvent,
  TranscriptRow,
  TranslationErrorEvent,
  TranslationEvent,
  UiSettings,
} from '@/types';

const ENDPOINT_KEY = 'crisp.endpoint';
const TOKEN_KEY = 'crisp.token';

function savedEndpoint(): string {
  return localStorage.getItem(ENDPOINT_KEY) || 'local';
}

function savedToken(): string {
  return localStorage.getItem(TOKEN_KEY) || '';
}

function nowLabel(): string {
  return new Date().toLocaleTimeString([], { hour12: false });
}

function rowKey(event: TranscriptEvent): string {
  return event.utterance_id != null ? `u:${event.utterance_id}` : `s:${event.seq}`;
}

function translatorDot(status: string): DotState {
  if (status === 'online') return 'ok';
  if (status === 'offline' || status === 'error') return 'bad';
  if (status === 'disabled') return '';
  return 'warn';
}

function crispDot(status: string): DotState {
  if (status === 'running') return 'ok';
  if (status === 'starting') return 'warn';
  if (status === 'error') return 'bad';
  return '';
}

function captureDot(wsState: string, rtcState: string, audioState: string): DotState {
  if (wsState === 'error' || wsState === 'closed') return 'bad';
  if (rtcState === 'failed' || audioState === 'error') return 'bad';
  if (rtcState === 'connected' && audioState !== 'none') return 'ok';
  if (wsState === 'open' && rtcState === 'idle' && audioState === 'none') return '';
  return 'warn';
}

function captureState(wsState: string, rtcState: string, audioState: string): string {
  if (wsState === 'error' || wsState === 'closed') return 'bridge disconnected';
  if (rtcState === 'failed') return 'failed';
  if (rtcState === 'connected' && audioState !== 'none') return 'connected';
  if (audioState !== 'none') return rtcState === 'idle' ? audioState : rtcState;
  return 'idle';
}

export const useBridgeStore = defineStore('bridge', {
  state: () => ({
    wsState: 'connecting',
    wsDot: 'warn' as DotState,
    rtcState: 'idle',
    rtcDot: '' as DotState,
    audioState: 'none',
    audioDot: '' as DotState,
    translatorState: 'checking',
    translatorDot: 'warn' as DotState,
    crispState: 'stopped',
    crispDot: '' as DotState,
    activeProfile: '',
    profiles: [] as ConfigProfile[],
    queueState: 0,
    sessionLabel: 'No active capture',
    logLines: [] as string[],
    lastHealthError: '',
    rowsByKey: new Map<string, TranscriptRow>(),
    finalSeqToKey: new Map<number, string>(),
    rawEvents: [] as BridgeEvent[],
    stats: {
      partial: 0,
      final: 0,
      translation: 0,
      error: 0,
    } as Stats,
    settings: {
      showPartials: true,
      displayMode: 'both',
      autoScroll: true,
      transcriptFontPx: 18,
    } as UiSettings,
    endpoint: savedEndpoint(),
    endpointToken: savedToken(),
  }),
  getters: {
    profileDot: (state): DotState => {
      if (!state.activeProfile) return '';
      if (state.crispState === 'running') return 'ok';
      if (state.crispState === 'starting') return 'warn';
      if (state.crispState === 'error') return 'bad';
      return '';
    },
    captureActive: (state): boolean => state.audioState !== 'none',
    rows: (state): TranscriptRow[] => Array.from(state.rowsByKey.values()),
    visibleRows(): TranscriptRow[] {
      return this.rows.filter((row) => this.settings.showPartials || row.kind !== 'partial');
    },
    captureState: (state): string => captureState(state.wsState, state.rtcState, state.audioState),
    captureDot: (state): DotState => captureDot(state.wsState, state.rtcState, state.audioState),
    translatorStatusText: (state): string => `${state.translatorState} / queue ${state.queueState}`,
    logText: (state): string => state.logLines.join('\n'),
    endpointSettings: (state): EndpointSettings => ({
      endpoint: state.endpoint,
      token: state.endpointToken,
    }),
    usingLocalBridge: (state): boolean => state.endpoint === 'local',
  },
  actions: {
    log(line: string): void {
      this.logLines.push(`[${nowLabel()}] ${line}`);
    },
    setWsState(text: string, dot: DotState): void {
      this.wsState = text;
      this.wsDot = dot;
    },
    setRtcState(text: string, dot: DotState): void {
      this.rtcState = text;
      this.rtcDot = dot;
    },
    setAudioState(text: string, dot: DotState): void {
      this.audioState = text;
      this.audioDot = dot;
    },
    setProfiles(profiles: ConfigProfile[], active: string, crispStatus: string): void {
      this.profiles = profiles;
      this.activeProfile = active;
      this.crispState = crispStatus || 'stopped';
      this.crispDot = crispDot(this.crispState);
    },
    setSessionLabel(text: string): void {
      this.sessionLabel = text;
    },
    incrementError(): void {
      this.stats.error += 1;
    },
    handleBridgeEvent(event: BridgeEvent): void {
      this.rawEvents.push(event);
      if (event.type === 'transcript') this.handleTranscript(event);
      else if (event.type === 'translation') this.handleTranslation(event);
      else if (event.type === 'translation_error') this.handleTranslationError(event);
      else if (event.type === 'health') this.handleHealth(event);
    },
    handleTranscript(event: TranscriptEvent): void {
      const key = rowKey(event);
      const prev = this.rowsByKey.get(key) || {};
      this.rowsByKey.set(key, { ...prev, ...event, key, error: '' });
      if (event.kind === 'final' && event.seq != null) this.finalSeqToKey.set(event.seq, key);
      this.stats[event.kind === 'partial' ? 'partial' : 'final'] += 1;
    },
    handleTranslation(event: TranslationEvent): void {
      const key = this.finalSeqToKey.get(event.seq) || `s:${event.seq}`;
      const row = this.rowsByKey.get(key) || { key, seq: event.seq, kind: 'final', text: '' };
      this.rowsByKey.set(key, { ...row, translation: event.text || '', error: '' });
      this.stats.translation += 1;
    },
    handleTranslationError(event: TranslationErrorEvent): void {
      const key = this.finalSeqToKey.get(event.seq) || `s:${event.seq}`;
      const row = this.rowsByKey.get(key) || { key, seq: event.seq, kind: 'final', text: '' };
      const message = event.message || 'Translation failed';
      this.rowsByKey.set(key, { ...row, error: message });
      this.stats.error += 1;
      this.log(message);
    },
    handleHealth(event: HealthEvent): void {
      const status = event.translator_status || 'unknown';
      const queue = Number.isFinite(Number(event.translation_queue_size))
        ? Number(event.translation_queue_size)
        : 0;
      const error = (event.last_error || '').trim();
      this.translatorState = status;
      this.translatorDot = translatorDot(status);
      this.activeProfile = event.active_profile || this.activeProfile;
      this.crispState = event.crisp_status || this.crispState;
      this.crispDot = crispDot(this.crispState);
      this.queueState = queue;
      if (error && error !== this.lastHealthError) {
        this.log(error);
        this.lastHealthError = error;
      } else if (!error) {
        this.lastHealthError = '';
      }
    },
    clearTranscript(): void {
      this.rowsByKey.clear();
      this.finalSeqToKey.clear();
      this.rawEvents = [];
      this.stats.partial = 0;
      this.stats.final = 0;
      this.stats.translation = 0;
      this.stats.error = 0;
      this.log('Transcript cleared');
    },
    updateSettings(settings: Partial<UiSettings>): void {
      this.settings = {
        ...this.settings,
        ...settings,
      };
    },
    updateEndpointSettings(settings: Partial<EndpointSettings>): void {
      if (settings.endpoint !== undefined) {
        this.endpoint = settings.endpoint || 'local';
        localStorage.setItem(ENDPOINT_KEY, this.endpoint);
      }
      if (settings.token !== undefined) {
        this.endpointToken = settings.token;
        localStorage.setItem(TOKEN_KEY, settings.token);
      }
    },
  },
});
