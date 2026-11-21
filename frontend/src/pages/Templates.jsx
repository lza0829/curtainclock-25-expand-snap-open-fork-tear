import { useEffect, useState } from "react";
import { api } from "../api";

const WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

function fmtMin(m) {
  const h = String(Math.floor(m / 60)).padStart(2, "0");
  const mm = String(m % 60).padStart(2, "0");
  return `${h}:${mm}`;
}

function toMin(hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}

function nextMonday() {
  const d = new Date();
  d.setDate(d.getDate() + ((8 - d.getDay()) % 7 || 7));
  return d.toISOString().slice(0, 10);
}

const emptyEntry = (slots, execs) => ({
  weekday: 0,
  slot_code: slots[0]?.code || "",
  executor_code: execs[0]?.code || "",
  start: "09:00",
  end: "10:30",
});

export default function Templates() {
  const [templates, setTemplates] = useState([]);
  const [expansions, setExpansions] = useState([]);
  const [slots, setSlots] = useState([]);
  const [execs, setExecs] = useState([]);
  const [editing, setEditing] = useState(null); // null=新建表单未开, {code?...}
  const [weekStart, setWeekStart] = useState(nextMonday());
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  async function load() {
    setErr("");
    try {
      const [t, x, s, e] = await Promise.all([
        api.templates(),
        api.expansions(),
        api.slots(),
        api.executors(),
      ]);
      setTemplates(t);
      setExpansions(x);
      setSlots(s);
      setExecs(e);
    } catch (e2) {
      setErr(e2.message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function startCreate() {
    setEditing({
      code: "",
      title: "",
      subject: "",
      entries: [emptyEntry(slots, execs)],
    });
  }

  function startEdit(t) {
    setEditing({
      code: t.code,
      version: t.version,
      title: t.title,
      subject: t.subject,
      entries: t.entries.map((e) => ({
        weekday: e.weekday,
        slot_code: e.slot_code,
        executor_code: e.executor_code,
        start: fmtMin(e.start_min),
        end: fmtMin(e.end_min),
      })),
    });
  }

  function setEntry(i, patch) {
    setEditing((ed) => ({
      ...ed,
      entries: ed.entries.map((e, j) => (j === i ? { ...e, ...patch } : e)),
    }));
  }

  async function save() {
    setMsg("");
    setErr("");
    const body = {
      title: editing.title,
      subject: editing.subject,
      entries: editing.entries.map((e) => ({
        weekday: Number(e.weekday),
        slot_code: e.slot_code,
        executor_code: e.executor_code,
        start_min: toMin(e.start),
        end_min: toMin(e.end),
      })),
    };
    try {
      if (editing.version != null) {
        const r = await api.updateTemplate(editing.code, body);
        setMsg(
          `模板 ${r.code} 已存为 v${r.version}；已展开草稿保持原快照，不受影响`
        );
      } else {
        const r = await api.createTemplate({ code: editing.code, ...body });
        setMsg(`模板 ${r.code} 已创建（v${r.version}）`);
      }
      setEditing(null);
      await load();
    } catch (e) {
      setErr(e.message);
    }
  }

  async function expand(code) {
    setMsg("");
    setErr("");
    try {
      const r = await api.expandTemplate(code, weekStart);
      setMsg(
        r.reused
          ? `${code} 该周已展开过（v${r.template_version}），复用既有 ${r.windows.length} 个草稿，未重复展开`
          : `已按 v${r.template_version} 展开 ${r.windows.length} 个草稿批窗：${r.windows.join("、")}`
      );
      await load();
    } catch (e) {
      setErr(e.message);
    }
  }

  return (
    <>
      <section className="panel">
        <h2>周模板（快照臂：展开即定格，改模板不回写草稿）</h2>
        {msg && <div className="msg">{msg}</div>}
        {err && <div className="msg err">{err}</div>}
        <div className="row-actions" style={{ marginBottom: 10 }}>
          <button onClick={startCreate}>新建模板</button>
          <label>
            展开周（周一）{" "}
            <input
              type="date"
              value={weekStart}
              onChange={(e) => setWeekStart(e.target.value)}
            />
          </label>
        </div>
        <table>
          <thead>
            <tr>
              <th>模板</th>
              <th>版本</th>
              <th>条目（星期 · 时段 · 算力槽/执行器）</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {templates.map((t) => (
              <tr key={t.code}>
                <td>
                  <div>{t.title}</div>
                  <small>
                    {t.code} · {t.subject}
                  </small>
                </td>
                <td>
                  <span className="tag">v{t.version}</span>
                  <br />
                  <small>{t.updated_at}</small>
                </td>
                <td>
                  {t.entries.map((e, i) => (
                    <div key={i}>
                      {WEEKDAYS[e.weekday]} {fmtMin(e.start_min)}–
                      {fmtMin(e.end_min)} · {e.slot_code}/{e.executor_code}
                    </div>
                  ))}
                </td>
                <td>
                  <div className="row-actions">
                    <button className="secondary" onClick={() => expand(t.code)}>
                      展开本周
                    </button>
                    <button className="secondary" onClick={() => startEdit(t)}>
                      改模板
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {editing && (
        <section className="panel">
          <h2>
            {editing.version != null
              ? `改模板 ${editing.code}（当前 v${editing.version}，保存后升版）`
              : "新建模板"}
          </h2>
          <div className="row-actions" style={{ marginBottom: 8 }}>
            {editing.version == null && (
              <input
                placeholder="编码，如 T-ETL-DAILY"
                value={editing.code}
                onChange={(e) => setEditing({ ...editing, code: e.target.value })}
              />
            )}
            <input
              placeholder="标题"
              value={editing.title}
              onChange={(e) => setEditing({ ...editing, title: e.target.value })}
            />
            <input
              placeholder="主题，如 ETL"
              value={editing.subject}
              onChange={(e) =>
                setEditing({ ...editing, subject: e.target.value })
              }
            />
          </div>
          {editing.entries.map((en, i) => (
            <div className="row-actions" key={i} style={{ marginBottom: 6 }}>
              <select
                value={en.weekday}
                onChange={(e) => setEntry(i, { weekday: e.target.value })}
              >
                {WEEKDAYS.map((w, d) => (
                  <option key={d} value={d}>
                    {w}
                  </option>
                ))}
              </select>
              <input
                type="time"
                value={en.start}
                onChange={(e) => setEntry(i, { start: e.target.value })}
              />
              <input
                type="time"
                value={en.end}
                onChange={(e) => setEntry(i, { end: e.target.value })}
              />
              <select
                value={en.slot_code}
                onChange={(e) => setEntry(i, { slot_code: e.target.value })}
              >
                {slots.map((s) => (
                  <option key={s.code} value={s.code}>
                    {s.code}
                  </option>
                ))}
              </select>
              <select
                value={en.executor_code}
                onChange={(e) => setEntry(i, { executor_code: e.target.value })}
              >
                {execs.map((x) => (
                  <option key={x.code} value={x.code}>
                    {x.code}
                  </option>
                ))}
              </select>
              <button
                className="secondary"
                onClick={() =>
                  setEditing((ed) => ({
                    ...ed,
                    entries: ed.entries.filter((_, j) => j !== i),
                  }))
                }
              >
                删行
              </button>
            </div>
          ))}
          <div className="row-actions">
            <button
              className="secondary"
              onClick={() =>
                setEditing((ed) => ({
                  ...ed,
                  entries: [...ed.entries, emptyEntry(slots, execs)],
                }))
              }
            >
              加条目
            </button>
            <button onClick={save}>保存</button>
            <button className="secondary" onClick={() => setEditing(null)}>
              取消
            </button>
          </div>
        </section>
      )}

      <section className="panel">
        <h2>展开审计</h2>
        <table>
          <thead>
            <tr>
              <th>展开</th>
              <th>模板@版本</th>
              <th>周</th>
              <th>批窗（快照）</th>
            </tr>
          </thead>
          <tbody>
            {expansions.map((x) => (
              <tr key={x.id}>
                <td>
                  #{x.id}
                  <br />
                  <small>{x.created_at}</small>
                </td>
                <td>
                  {x.template_code} <span className="tag">v{x.template_version}</span>
                </td>
                <td>{x.week_start}</td>
                <td>
                  {x.items.map((i) => (
                    <div key={i.window_code}>
                      {i.window_code}{" "}
                      {i.status ? (
                        <small>
                          {i.day} {fmtMin(i.start_min)}–{fmtMin(i.end_min)} ·{" "}
                          {i.slot_code}/{i.executor_code} · {i.status}
                        </small>
                      ) : (
                        <small>（已作废）</small>
                      )}
                    </div>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
