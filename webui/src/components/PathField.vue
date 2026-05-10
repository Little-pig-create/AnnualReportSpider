<template>
  <label class="field">
    <span>{{ label }}</span>
    <div class="input-row">
      <input :value="modelValue" @input="onInput" :placeholder="placeholder" />
      <div class="actions">
        <button v-if="selectable" type="button" class="secondary" @click="$emit('select')">选择</button>
        <button v-if="openable" type="button" @click="$emit('open')">打开</button>
      </div>
    </div>
  </label>
</template>

<script setup lang="ts">
defineProps<{
  label: string;
  modelValue: string;
  placeholder?: string;
  openable?: boolean;
  selectable?: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: string];
  open: [];
  select: [];
}>();

function onInput(event: Event) {
  emit("update:modelValue", (event.target as HTMLInputElement).value);
}
</script>

<style scoped>
.field {
  display: grid;
  gap: 10px;
}

.field span {
  font-size: 13px;
  color: var(--muted);
}

.input-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 12px;
  align-items: center;
}

.actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 16px;
  background: var(--brand);
  color: white;
  min-height: 48px;
  min-width: 76px;
  padding: 0 16px;
  cursor: pointer;
}

.secondary {
  background: #dceef0;
  color: #14515b;
}
</style>
