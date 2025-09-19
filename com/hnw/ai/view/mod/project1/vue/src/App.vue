<template>
  <div style="padding:16px">
    <h1>AI Platform Viewer - Vue (DEV)</h1>
    <Pane title="상단" index="ds_top" :request-path="requestPath" />
    <Pane title="하단" index="ds_bottom" :request-path="requestPath" />
  </div>
</template>

<script setup lang="ts">
import Pane from './components/Pane.vue';
const requestPath = '/request';
</script>
