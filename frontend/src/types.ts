export type DotState = '' | 'ok' | 'warn' | 'bad';
export type DisplayMode = 'both' | 'translation';
export type CaptureEndpoint = 'local' | string;

export interface UiSettings {
  showPartials: boolean;
  displayMode: DisplayMode;
  autoScroll: boolean;
  transcriptFontPx: number;
}

export interface EndpointSettings {
  endpoint: CaptureEndpoint;
  token: string;
}

export interface ConfigProfile {
  name: string;
  label?: string;
  description?: string;
  tags?: string[];
  path: string;
  translate_model?: string;
  crispasr?: string;
}

export interface Stats {
  partial: number;
  final: number;
  translation: number;
  error: number;
}

export interface TranscriptRow {
  key: string;
  seq?: number;
  kind?: 'partial' | 'final' | 'plain' | string;
  final?: boolean;
  text?: string;
  translation?: string;
  error?: string;
  utterance_id?: number;
  t0?: number;
  t1?: number;
}

export interface TranscriptEvent extends TranscriptRow {
  type: 'transcript';
  seq: number;
}

export interface TranslationEvent {
  type: 'translation';
  seq: number;
  text: string;
}

export interface TranslationErrorEvent {
  type: 'translation_error';
  seq: number;
  message: string;
}

export interface HealthEvent {
  type: 'health';
  translator_status?: string;
  translation_queue_size?: number;
  last_error?: string;
  active_profile?: string;
  crisp_status?: string;
}

export type BridgeEvent = TranscriptEvent | TranslationEvent | TranslationErrorEvent | HealthEvent;
