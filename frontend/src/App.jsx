import { NavLink, Route, Routes } from "react-router-dom";
import Home from "./pages/Home.jsx";
import Sessions from "./pages/Sessions.jsx";
import Templates from "./pages/Templates.jsx";
import Resources from "./pages/Resources.jsx";
import Leases from "./pages/Leases.jsx";
import Conflicts from "./pages/Conflicts.jsx";

export default function App() {
  return (
    <div className="shell">
      <header className="hero">
        <h1 className="brand">幕窗钟</h1>
        <p>
          周模板展开为草稿批窗即定格快照：改模板只升版不回写；开窗预检与租约实资源只认批窗快照，数字同源可核。
        </p>
      </header>

      <nav className="nav">
        <NavLink to="/" end>
          总览
        </NavLink>
        <NavLink to="/templates">周模板</NavLink>
        <NavLink to="/windows">批窗</NavLink>
        <NavLink to="/resources">算力槽与执行器</NavLink>
        <NavLink to="/leases">租约</NavLink>
        <NavLink to="/conflicts">冲突</NavLink>
      </nav>

      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/templates" element={<Templates />} />
        <Route path="/windows" element={<Sessions />} />
        <Route path="/resources" element={<Resources />} />
        <Route path="/leases" element={<Leases />} />
        <Route path="/conflicts" element={<Conflicts />} />
      </Routes>
    </div>
  );
}
