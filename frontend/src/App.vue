<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';

import { downloadText, vttText } from '@/api/export';
import { fetchProfiles, selectProfile } from '@/api/profiles';
import { startSubtitleOverlay } from '@/api/subtitle';
import { CaptureSession, type CaptureCallbacks } from '@/api/webrtc';
import { BridgeSocket } from '@/api/websocket';
import { WebSocketSession } from '@/api/websocketSession';
import SettingsPopover from '@/components/SettingsPopover.vue';
import SidebarPanel from '@/components/SidebarPanel.vue';
import TranscriptView from '@/components/TranscriptView.vue';
import { useBridgeStore } from '@/stores/bridge';

const bridge = useBridgeStore();
const settingsOpen = ref(false);
const profileBusy = ref(false);

let bridgeSocket: BridgeSocket | null = null;
let captureSession: CaptureSession | WebSocketSession | null = null;

const captureCallbacks: CaptureCallbacks = {
  onRtcState: (text, dot) => {
    bridge.setRtcState(text, dot);
  },
  onAudioState: (text, dot) => {
    bridge.setAudioState(text, dot);
  },
  onSessionLabel: (text) => {
    bridge.setSessionLabel(text);
  },
  onLog: bridge.log,
};

async function startDisplay(): Promise<void> {
  try {
    await captureSession?.startDisplay();
  } catch (error) {
    bridge.log(`Capture error: ${error instanceof Error ? error.message : String(error)}`);
    captureSession?.stop();
  }
}

async function startMic(): Promise<void> {
  try {
    await captureSession?.startMicrophone();
  } catch (error) {
    bridge.log(`Capture error: ${error instanceof Error ? error.message : String(error)}`);
    captureSession?.stop();
  }
}

function stopCapture(): void {
  captureSession?.stop();
}

async function loadProfiles(): Promise<void> {
  try {
    const data = await fetchProfiles();
    bridge.setProfiles(data.profiles, data.active, data.crisp_status);
  } catch (error) {
    bridge.log(`Profile list error: ${error instanceof Error ? error.message : String(error)}`);
  }
}

async function changeProfile(event: Event): Promise<void> {
  const name = (event.target as HTMLSelectElement).value;
  if (!name || name === bridge.activeProfile || profileBusy.value) return;
  profileBusy.value = true;
  try {
    const data = await selectProfile(name);
    bridge.setProfiles(data.profiles || bridge.profiles, data.active, data.crisp_status);
    bridge.log(`Profile selected: ${data.active}`);
  } catch (error) {
    bridge.log(`Profile switch error: ${error instanceof Error ? error.message : String(error)}`);
    await loadProfiles();
  } finally {
    profileBusy.value = false;
  }
}

function clearTranscript(): void {
  bridge.clearTranscript();
}

async function startOverlay(): Promise<void> {
  try {
    await startSubtitleOverlay();
    bridge.log('Subtitle overlay started');
  } catch (error) {
    bridge.log(`Overlay error: ${error instanceof Error ? error.message : String(error)}`);
  }
}

function exportSelected(): void {
  downloadText(
    'crispasr-subtitles.vtt',
    vttText(bridge.visibleRows, bridge.settings.displayMode),
    'text/vtt',
  );
}

function makeBridgeSocket(): BridgeSocket {
  return new BridgeSocket({
    onState: (text, dot) => {
      bridge.setWsState(text, dot);
    },
    onLog: bridge.log,
    onEvent: bridge.handleBridgeEvent,
    onBadJson: () => {
      bridge.incrementError();
    },
  });
}

function configureCaptureTransport(): void {
  captureSession?.stop();
  if (bridge.usingLocalBridge) {
    captureSession = new CaptureSession(captureCallbacks);
    bridgeSocket ??= makeBridgeSocket();
    bridgeSocket.connect();
    void loadProfiles();
    return;
  }

  bridgeSocket?.close();
  bridgeSocket = null;
  bridge.setWsState('cloud endpoint', 'ok');
  captureSession = new WebSocketSession(bridge.endpoint, bridge.endpointToken, captureCallbacks);
  bridge.setProfiles([], 'Modal cloud ja', bridge.crispState === 'running' ? 'running' : 'stopped');
}

function updateEndpointSettings(
  settings: Parameters<typeof bridge.updateEndpointSettings>[0],
): void {
  const previousEndpoint = bridge.endpoint;
  const previousToken = bridge.endpointToken;
  bridge.updateEndpointSettings(settings);
  if (previousEndpoint !== bridge.endpoint || previousToken !== bridge.endpointToken) {
    configureCaptureTransport();
  }
}

onMounted(() => {
  bridgeSocket = new BridgeSocket({
    onState: (text, dot) => {
      bridge.setWsState(text, dot);
    },
    onLog: bridge.log,
    onEvent: bridge.handleBridgeEvent,
    onBadJson: () => {
      bridge.incrementError();
    },
  });
  configureCaptureTransport();
});

onUnmounted(() => {
  bridgeSocket?.close();
  captureSession?.stop();
});
</script>

<template>
  <div class="app">
    <SidebarPanel
      :capture-state="bridge.captureState"
      :capture-dot="bridge.captureDot"
      :crisp-state="bridge.crispState"
      :crisp-dot="bridge.crispDot"
      :active-profile="bridge.activeProfile"
      :profile-dot="bridge.profileDot"
      :translator-status-text="bridge.translatorStatusText"
      :translator-dot="bridge.translatorDot"
      :stats="bridge.stats"
      :log-text="bridge.logText"
      :capture-active="bridge.captureActive"
      @start-display="startDisplay"
      @start-mic="startMic"
      @stop-capture="stopCapture"
    />
    <main class="main">
      <header class="toolbar">
        <div class="toolbar-title">
          <h2>Transcript</h2>
          <p>{{ bridge.sessionLabel }}</p>
        </div>
        <div class="toolbar-actions">
          <select
            class="profile-select"
            :value="bridge.activeProfile"
            :disabled="profileBusy || !bridge.usingLocalBridge"
            title="Config profile"
            @change="changeProfile"
          >
            <option value="" disabled>Select profile</option>
            <option
              v-for="profile in bridge.profiles"
              :key="profile.name"
              :value="profile.name"
              :title="profile.description || profile.name"
            >
              {{ profile.label || profile.name }}
            </option>
          </select>
          <button type="button" @click="clearTranscript">Clear</button>
          <button type="button" @click="startOverlay">Overlay</button>
          <button type="button" @click="exportSelected">Export</button>
          <div class="settings-wrap">
            <button
              type="button"
              class="icon-button"
              :aria-expanded="settingsOpen"
              aria-label="Settings"
              title="Settings"
              @click="settingsOpen = !settingsOpen"
            >
              ⚙
            </button>
            <SettingsPopover
              v-if="settingsOpen"
              :settings="bridge.settings"
              :endpoint-settings="bridge.endpointSettings"
              @update-settings="bridge.updateSettings"
              @update-endpoint-settings="updateEndpointSettings"
            />
          </div>
        </div>
      </header>
      <TranscriptView
        :rows="bridge.visibleRows"
        :display-mode="bridge.settings.displayMode"
        :auto-scroll="bridge.settings.autoScroll"
        :text-size="bridge.settings.transcriptFontPx"
      />
    </main>
  </div>
</template>
