import { useEffect, useRef, useState } from "react";

type Row = Record<string, any>;

// ✅ 변경: 첫 번째 컬럼(ts)만 날짜 변환, 나머지는 원본 그대로
function formatCell(value: any, colIndex?: number): string {
  if (colIndex !== 0) return String(value ?? "");
  if (value == null) return "";
  // 숫자(유닉스 epoch) 처리: 초/밀리초 모두 대응
  if (typeof value === "number") {
    const ts = value > 1e12 ? value : value * 1000; // 13자리면 ms, 10자리면 s로 간주
    if (ts > 0) return new Date(ts).toLocaleString("ko-KR");
  }
  // 문자열이지만 숫자로만 구성된 epoch일 수 있음
  if (typeof value === "string" && /^\d{10,13}$/.test(value)) {
    const n = Number(value);
    const ts = value.length >= 13 ? n : n * 1000;
    if (!Number.isNaN(ts)) return new Date(ts).toLocaleString("ko-KR");
  }
  // ISO 날짜 문자열 처리(예: 2025-08-20T12:34:56Z)
  if (typeof value === "string" && /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value)) {
    const d = new Date(value);
    if (!Number.isNaN(d.getTime())) return d.toLocaleString("ko-KR");
  }
  return String(value);
}

function useWS(wsPath = "/ws") {
  const wsRef = useRef<WebSocket | null>(null);
  const [last, setLast] = useState<any | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const url =
      (location.protocol === "https:" ? "wss://" : "ws://") +
      location.host +
      wsPath;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        setLast(msg);
      } catch {
        // ignore
      }
    };
    ws.onclose = () => setConnected(false);

    return () => {
      ws.close();
    };
  }, [wsPath]);

  return { wsRef, last, connected };
}

async function requestAPI(index: string, options: any = {}, requestPath = "/request") {
  const res = await fetch(requestPath, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ index, options }),
  });
  if (!res.ok) {
    throw new Error(`POST ${requestPath} -> ${res.status}`);
  }
}

function Pane({
  title,
  index,
  requestPath,
}: {
  title: string;
  index: string;
  requestPath: string;
}) {
  const [cols, setCols] = useState<string[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [auto, setAuto] = useState(true);
  const [ms, setMs] = useState(1000);
  const [status, setStatus] = useState("대기 중");

  // WS 연결 및 마지막 메시지 구독 (자동 연결)
  const { last, connected } = useWS("/ws");

  // WS 메시지 적용
  useEffect(() => {
    if (!last || last.type !== "rows" || last.index !== index) return;
    const inferredCols =
      last.columns?.length
        ? (last.columns as string[])
        : last.rows?.[0]
        ? Object.keys(last.rows[0] as object)
        : [];
    setCols(inferredCols);
    setRows(last.rows ?? []);
    setStatus(`수신 ${last.rows?.length ?? 0}건`);
  }, [last, index]);

  // 자동 갱신(수동요청 버튼 제거, 자동만 유지)
  useEffect(() => {
    if (!auto) return;
    // 바로 한 번 호출
    requestAPI(index, {}, requestPath).catch((e) =>
      setStatus("요청 실패: " + e.message)
    );
    const t = setInterval(() => {
      requestAPI(index, {}, requestPath).catch((e) =>
        setStatus("요청 실패: " + e.message)
      );
    }, Math.max(200, ms));
    return () => clearInterval(t);
  }, [auto, ms, index, requestPath]);

  return (
    <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12, marginBottom: 16 }}>
      <div style={{ fontWeight: 700, marginBottom: 8 }}>
        {title} <span style={{ color: "#666" }}>({index})</span>
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        {/* 수동요청 버튼 제거 */}
        <button onClick={() => { setRows([]); setStatus("표 비움"); }}>표 지우기</button>
        <div style={{ marginLeft: "auto", display: "flex", gap: 10, alignItems: "center" }}>
          <label>
            <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
            자동갱신
          </label>
          <label>
            간격(ms)
            <input
              type="number"
              value={ms}
              min={200}
              step={100}
              onChange={(e) => setMs(parseInt(e.target.value || "1000", 10))}
              style={{ width: 90, marginLeft: 6 }}
            />
          </label>
          <span style={{ fontSize: 12, color: connected ? "green" : "red" }}>
            WS: {connected ? "연결" : "미연결"}
          </span>
        </div>
      </div>

      <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 8 }}>
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c} style={{ border: "1px solid #eee", padding: "6px 8px", background: "#fafafa" }}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {(rows.length > 300 ? rows.slice(-300) : rows).map((r, i) => (
            <tr key={i}>
              {cols.map((c, colIndex) => (
                <td key={c} style={{ border: "1px solid #e5e5e5", padding: "6px 8px", textAlign: "center" }}>
                  {formatCell(r[c], colIndex)} {/* ✅ 첫 번째 컬럼(ts)만 날짜 변환 */}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      <div style={{ marginTop: 8, fontSize: 12, color: "#555" }}>
        {status}
      </div>
    </div>
  );
}

export default function App() {
  const requestPath = "/request"; // ReactView의 설정과 동일
  return (
    <div style={{ padding: 16 }}>
      <h1>AI Platform Viewer - React (DEV)</h1>
      <Pane title="상단" index="ds_top" requestPath={requestPath} />
      <Pane title="하단" index="ds_bottom" requestPath={requestPath} />
    </div>
  );
}
