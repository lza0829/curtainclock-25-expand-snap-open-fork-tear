import { useEffect, useState } from "react";
import { api } from "../api";

function fmtMin(m) {
  const h = String(Math.floor(m / 60)).padStart(2, "0");
  const mm = String(m % 60).padStart(2, "0");
  return `${h}:${mm}`;
}

const statusLabel = { draft: "待开窗", live: "占用中", done: "已结束" };

export default function Sessions() {
  const [rows, setRows] = useState([]);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  async function load() {
    setErr("");
    try {
      setRows(await api.windows());
    } catch (e) {
      setErr(e.message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function openLease(code) {
    setMsg("");
    setErr("");
    try {
      const r = await api.openLease(code);
      setMsg(`已开窗，租约 ${r.lease_no}；在途租约 ${r.open_leases}`);
      await load();
    } catch (e) {
      setErr(e.message);
      await load();
    }
  }

  async function discard(code) {
    setMsg("");
    setErr("");
    try {
      await api.discardWindow(code);
      setMsg(`已作废草稿 ${code}`);
      await load();
    } catch (e) {
      setErr(e.message);
      await load();
    }
  }

  return (
    <section className="panel">
      <h2>批窗</h2>
      {msg && <div className="msg">{msg}</div>}
      {err && <div className="msg err">{err}</div>}
      <table>
        <thead>
          <tr>
            <th>批窗</th>
            <th>来源</th>
            <th>时段</th>
            <th>算力槽 / 执行器</th>
            <th>就绪</th>
            <th>状态</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.code}>
              <td>
                <div>{r.title}</div>
                <small>{r.code}</small>
              </td>
              <td>
                {r.template_code ? (
                  r.snapshot_id ? (
                    <>
                      <span className="tag live">
                        {r.template_code}·v{r.template_version}
                      </span>
                      <br />
                      <small title="开窗/预检/租约唯一真源">📌 {r.snapshot_id}</small>
                    </>
                  ) : (
                    <span className="tag bad" title="模板批窗缺钉扎，开窗将被拒">
                      {r.template_code}·v{r.template_version} 未钉快照
                    </span>
                  )
                ) : (
                  <small>手工</small>
                )}
              </td>
              <td>
                {r.day}
                <br />
                {fmtMin(r.start_min)}–{fmtMin(r.end_min)}
              </td>
              <td>
                {r.slot_code}
                <br />
                {r.executor_code}
              </td>
              <td>
                {r.readiness?.ready ? (
                  <span className="tag live">就绪</span>
                ) : (
                  <span className="tag bad">
                    {(r.readiness?.reasons || []).join("；") || "未就绪"}
                  </span>
                )}
              </td>
              <td>
                <span className={`tag ${r.status}`}>
                  {statusLabel[r.status] || r.status}
                </span>
              </td>
              <td>
                <div className="row-actions">
                  <button
                    disabled={r.status !== "draft"}
                    onClick={() => openLease(r.code)}
                  >
                    开窗占用
                  </button>
                  {r.status === "draft" && (
                    <button className="secondary" onClick={() => discard(r.code)}>
                      作废
                    </button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
