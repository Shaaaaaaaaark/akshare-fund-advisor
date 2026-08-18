import { Bot, Database, ShieldCheck } from "lucide-react";
import { Link, Outlet, useLocation } from "react-router-dom";

export default function WorkbenchLayout() {
  const { pathname } = useLocation();
  const immersiveETF = pathname === "/funds" || pathname.startsWith("/funds/");
  const agentActive = pathname === "/chat";

  return (
    <div
      className={`workbench-shell ${immersiveETF ? "etf-immersive-shell" : ""}`}
    >
      <header className="workbench-topbar">
        <div className="workbench-topbar-inner">
          <Link className="workbench-brand" to="/">
            <span className="workbench-brand-mark" aria-hidden="true">
              FA
            </span>
            <span className="workbench-brand-copy">
              <strong>Fund Advisor</strong>
              <small>可信投研工作台</small>
            </span>
          </Link>

          <nav className="workbench-nav" aria-label="一级功能">
            <Link
              to="/"
              className={`workbench-nav-item ${agentActive ? "" : "active"}`}
            >
              <Database aria-hidden="true" />
              数据面板
            </Link>
            <Link
              to="/chat"
              className={`workbench-nav-item ${agentActive ? "active" : ""}`}
            >
              <Bot aria-hidden="true" />
              Agent
            </Link>
          </nav>

          <div className="workbench-actions">
            <span className="audit-mode">
              <ShieldCheck aria-hidden="true" />
              审计模式
            </span>
          </div>
        </div>
      </header>

      <div className="workbench-main">
        <Outlet />
      </div>
    </div>
  );
}
