<script setup lang="ts">
import type { EndpointSettings, UiSettings } from '@/types';

const DEFAULT_MODAL_ENDPOINT =
  'wss://litardphobia--crisp-caption-runtime-realtime-service.modal.run/v1/realtime';

const props = defineProps<{
  settings: UiSettings;
  endpointSettings: EndpointSettings;
}>();

defineEmits<{
  updateSettings: [settings: Partial<UiSettings>];
  updateEndpointSettings: [settings: Partial<EndpointSettings>];
}>();

function checkedValue(event: Event): boolean {
  return (event.target as HTMLInputElement).checked;
}

function numberValue(event: Event): number {
  return Number((event.target as HTMLInputElement).value);
}

function endpointMode(): 'local' | 'modal' {
  return props.endpointSettings.endpoint === 'local' ? 'local' : 'modal';
}

function modalEndpoint(): string {
  return props.endpointSettings.endpoint === 'local' ? '' : props.endpointSettings.endpoint;
}
</script>

<template>
  <section class="settings-popover">
    <div class="settings-title">Settings</div>
    <div class="settings-list">
      <label class="check-row">
        <input
          :checked="settings.showPartials"
          type="checkbox"
          @change="$emit('updateSettings', { showPartials: checkedValue($event) })"
        />
        <span>Show partials</span>
      </label>
      <label class="check-row">
        <input
          :checked="settings.autoScroll"
          type="checkbox"
          @change="$emit('updateSettings', { autoScroll: checkedValue($event) })"
        />
        <span>Auto scroll</span>
      </label>
      <label class="field-row">
        <span>Display</span>
        <select
          :value="settings.displayMode"
          @change="
            $emit('updateSettings', {
              displayMode: ($event.target as HTMLSelectElement).value as UiSettings['displayMode'],
            })
          "
        >
          <option value="both">Source + translation</option>
          <option value="translation">Translation only</option>
        </select>
      </label>
      <label class="field-row">
        <span>Text size</span>
        <div class="range-control">
          <input
            :value="settings.transcriptFontPx"
            type="range"
            min="14"
            max="28"
            step="1"
            @input="$emit('updateSettings', { transcriptFontPx: numberValue($event) })"
          />
          <output>{{ settings.transcriptFontPx }}px</output>
        </div>
      </label>
      <label class="field-row">
        <span>Endpoint</span>
        <select
          :value="endpointMode()"
          @change="
            $emit('updateEndpointSettings', {
              endpoint:
                ($event.target as HTMLSelectElement).value === 'local'
                  ? 'local'
                  : modalEndpoint() || DEFAULT_MODAL_ENDPOINT,
            })
          "
        >
          <option value="local">Local bridge</option>
          <option value="modal">Modal cloud</option>
        </select>
      </label>
      <label v-if="endpointMode() === 'modal'" class="stack-field">
        <span>WSS URL</span>
        <input
          :value="modalEndpoint()"
          placeholder="wss://.../v1/realtime"
          type="url"
          @input="
            $emit('updateEndpointSettings', {
              endpoint: ($event.target as HTMLInputElement).value,
            })
          "
        />
      </label>
      <label v-if="endpointMode() === 'modal'" class="stack-field">
        <span>Token</span>
        <input
          :value="endpointSettings.token"
          autocomplete="off"
          placeholder="CRISP_API_TOKEN"
          type="password"
          @input="
            $emit('updateEndpointSettings', {
              token: ($event.target as HTMLInputElement).value,
            })
          "
        />
      </label>
    </div>
  </section>
</template>
