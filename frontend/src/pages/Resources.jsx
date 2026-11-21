import { useEffect, useState } from "react";
import { api } from "../api";

function PinBadges({ snaps, vers }) {
  if (!snaps || snaps.length === 0) return <small>空闲</small>;
  return (
    <>
      {snaps.map((s) => (
        <span key={s} className="tag live" style={{ marginRight: 4 }}>
          📌 {s}
        </span>
      ))}
      <br />
      <small>版本 {vers.join(" / ")}</small>
    </>
  );
}

export default function Resources() {
  const [slots, setRooms] = useState([]);
  const [executors, setTeachers] = useState([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    Promise.all([api.slots(), api.executors()])
      .then(([r, t]) => {
        setRooms(r);
        setTeachers(t);
      })
      .catch((e) => setErr(e.message));
  }, []);

  if (err) return <div className="msg err">{err}</div>;

  return (
    <>
      <section className="panel">
        <h2>算力槽（占用水位只认在途租约实存行）</h2>
        <table>
          <thead>
            <tr>
              <th>编码</th>
              <th>名称</th>
              <th>容量</th>
              <th>占用水位</th>
              <th>占用来源快照</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {slots.map((r) => (
              <tr key={r.code}>
                <td>{r.code}</td>
                <td>{r.name}</td>
                <td>{r.capacity}</td>
                <td>
                  <b>{r.open_lease_count}</b> 条在途
                </td>
                <td>
                  <PinBadges snaps={r.pinned_snapshots} vers={r.pinned_versions} />
                </td>
                <td>{r.active ? "启用" : "停用"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="panel">
        <h2>执行器</h2>
        <table>
          <thead>
            <tr>
              <th>编码</th>
              <th>名称</th>
              <th>作业类型</th>
              <th>占用水位</th>
              <th>占用来源快照</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {executors.map((t) => (
              <tr key={t.code}>
                <td>{t.code}</td>
                <td>{t.name}</td>
                <td>{t.subject}</td>
                <td>
                  <b>{t.open_lease_count}</b> 条在途
                </td>
                <td>
                  <PinBadges snaps={t.pinned_snapshots} vers={t.pinned_versions} />
                </td>
                <td>{t.active ? "启用" : "停用"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
