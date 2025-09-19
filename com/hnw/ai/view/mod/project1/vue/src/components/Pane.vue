<template>
  <div class="pane">
    <div class="pane-header">
      <strong>{{ title }}</strong>
      <span class="sub">({{ index }})</span>

      <div class="spacer"></div>

      <label class="inline">
        <input type="checkbox" v-model="auto" />
        자동갱신
      </label>

      <label class="inline">
        간격(ms)
        <input type="number" min="200" step="100" v-model.number="ms" class="num" />
      </label>

      <span class="ws" :class="{ on: connected }">WS: {{ connected ? '연결' : '미연결' }}</span>
    </div>

    <div class="toolbar">
      <button @click="requestAPI">새로고침</button>
      <button @click="clearTable">표 지우기</button>
    </div>

    <table class="grid">
      <thead>
        <tr>
          <th v-for="(c, colIndex) in cols" :key="c">{{ c }}</th>
        </tr>
      </thead>
    </table>

    <div class="grid-body">
      <table class="grid">
        <tbody>
          <tr v-for="(r, i) in limitedRows" :key="i">
            <td v-for="(c, colIndex) in cols" :key="c">{{ formatCell(r[c], colIndex) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="status">{{ status }}</div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch, computed } from 'vue';

type Row = Record<string, any>;

function formatCell(value: any, colIndex?: number): string {
  // ✅ 첫 번째 컬럼(ts)만 날짜 변환, 나머지는 원래 값 그대로
  if (colIndex !== 0) return String(value ?? '');
  if (value == null) return "";
  if (typeof value === "number") {
    const ts = value > 1e12 ? value : value * 1000;
    if (ts > 0) return new Date(ts).toLocaleString("ko-KR");
  }
  if (typeof value === "string" && /^\d{10,13}$/.test(value)) {
    const n = Number(value);
    const ts = value.length >= 13 ? n : n * 1000;
    if (!Number.isNaN(ts)) return new Date(ts).toLocaleString("ko-KR");
  }
  if (typeof value === "string" && /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value)) {
    const d = new Date(value);
    if (!Number.isNaN(d.getTime())) return d.toLocaleString("ko-KR");
  }
  return String(value);
}

const props = defineProps<{
  title: string;
  index: string;
  requestPath: string; // "/request"
}>();

const cols = ref<string[]>([]);
const rows = ref<Row[]>([]);
const status = ref('대기 중');

const auto = ref(true);
const ms = ref(1000);

const connected = ref(false);
let ws: WebSocket | null = null;
let timer: number | null = null;

const connectWS = () => {
  const url = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws';
  ws = new WebSocket(url);
  ws.onopen = () => { connected.value = true; };
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg?.type === 'rows' && msg?.index === props.index) {
        // 컬럼 추론
        const inferred = (msg.columns && msg.columns.length)
          ? msg.columns
          : (msg.rows && msg.rows[0]) ? Object.keys(msg.rows[0]) : [];
        cols.value = inferred;
        rows.value = msg.rows ?? [];
        status.value = `수신 ${rows.value.length}건`;
      }
    } catch {
      // ignore
    }
  };
  ws.onclose = () => { connected.value = false; };
};

const requestAPI = async () => {
  try {
    const res = await fetch(props.requestPath, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ index: props.index, options: {} })
    });
    if (!res.ok) {
      status.value = `요청 실패(${res.status})`;
    }
  } catch (e: any) {
    status.value = '요청 에러: ' + (e?.message || String(e));
  }
};

const startAuto = () => {
  stopAuto();
  if (!auto.value) return;
  requestAPI();
  timer = window.setInterval(() => requestAPI(), Math.max(200, ms.value));
};
const stopAuto = () => {
  if (timer) { window.clearInterval(timer); timer = null; }
};

const clearTable = () => {
  rows.value = [];
  status.value = '표 비움';
};

const limitedRows = computed(() => rows.value.length > 300 ? rows.value.slice(-300) : rows.value);

const toCell = (r: Row, c: string) => String(r?.[c] ?? '');

onMounted(() => {
  connectWS();
  startAuto();
});
onBeforeUnmount(() => {
  stopAuto();
  if (ws) { ws.close(); ws = null; }
});
watch([auto, ms], () => startAuto());
</script>

<style scoped>
.pane { border:1px solid #ddd; border-radius:8px; padding:12px; margin-bottom:16px; }
.pane-header { display:flex; align-items:center; gap:8px; margin-bottom:8px; }
.pane-header .sub { color:#666; }
.spacer { flex:1; }
.inline { display:flex; align-items:center; gap:6px; }
.num { width:90px; }
.ws { font-size:12px; color:#c00; }
.ws.on { color:green; }
.toolbar { display:flex; gap:8px; margin-bottom:8px; }
.grid { width:100%; border-collapse:collapse; }
.grid th, .grid td { border:1px solid #eee; padding:6px 8px; text-align:center; }
.grid thead th { background:#fafafa; }
.grid-body { max-height:50vh; overflow:auto; border:1px solid #eee; border-top:none; }
.status { margin-top:8px; font-size:12px; color:#555; }

/* === alignment fix: keep header/body columns aligned === */
.grid { table-layout: fixed; }
.grid th, .grid td { white-space: nowrap; }

</style>
