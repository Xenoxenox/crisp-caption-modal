<script setup lang="ts">
import type { DotState, Stats } from '@/types';

import StatusDot from './StatusDot.vue';

defineProps<{
  captureState: string;
  captureDot: DotState;
  translatorStatusText: string;
  translatorDot: DotState;
  crispState: string;
  crispDot: DotState;
  activeProfile: string;
  profileDot: DotState;
  stats: Stats;
  logText: string;
  captureActive: boolean;
}>();

defineEmits<{
  startDisplay: [];
  startMic: [];
  stopCapture: [];
}>();
</script>

<template>
  <aside class="sidebar">
    <div class="brand">
      <h1>WebRTC CrispASR</h1>
      <p>Live capture, transcript, and translation console.</p>
    </div>

    <section class="section">
      <div class="label">Capture</div>
      <div class="button-grid">
        <button type="button" class="primary" @click="$emit('startDisplay')">Tab audio</button>
        <button type="button" @click="$emit('startMic')">Microphone</button>
        <button
          type="button"
          class="danger"
          :disabled="!captureActive"
          @click="$emit('stopCapture')"
        >
          Stop
        </button>
      </div>
    </section>

    <section class="section">
      <div class="label">Status</div>
      <div class="status-list">
        <div class="status-item">
          <StatusDot :state="captureDot" /><span>Capture</span><strong>{{ captureState }}</strong>
        </div>
        <div class="status-item">
          <StatusDot :state="crispDot" /><span>CrispASR</span><strong>{{ crispState }}</strong>
        </div>
        <div class="status-item">
          <StatusDot :state="profileDot" /><span>Profile</span
          ><strong>{{ activeProfile || 'none' }}</strong>
        </div>
        <div class="status-item">
          <StatusDot :state="translatorDot" /><span>Translator</span
          ><strong>{{ translatorStatusText }}</strong>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="label">Counters</div>
      <div class="stats">
        <div class="stat">
          <b>{{ stats.partial }}</b
          ><span>partials</span>
        </div>
        <div class="stat">
          <b>{{ stats.final }}</b
          ><span>finals</span>
        </div>
        <div class="stat">
          <b>{{ stats.translation }}</b
          ><span>translations</span>
        </div>
        <div class="stat">
          <b>{{ stats.error }}</b
          ><span>errors</span>
        </div>
      </div>
    </section>

    <section class="section log-section">
      <div class="label">Event Log</div>
      <pre class="log">{{ logText }}</pre>
    </section>
  </aside>
</template>
