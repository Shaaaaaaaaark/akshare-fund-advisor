import {
  ArrowRight,
  BarChart3,
  Database,
  Landmark,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { fetchIndices } from "../api";
import StatusBadge from "../components/StatusBadge";
import type { IndicesResponse } from "../types";

export default function HomePage() {
  const [indices, setIndices] = useState<IndicesResponse | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void fetchIndices(controller.signal)
      .then(setIndices)
      .catch(() => {
        // Category entry remains usable when the optional overview call fails.
      });
    return () => controller.abort();
  }, []);

  const availableIndices = useMemo(
    () =>
      indices?.rows.filter((row) => row.meta.status === "available").length ??
      null,
    [indices],
  );
  const warningCount = useMemo(
    () =>
      indices?.rows.filter((row) => Boolean(row.meta.warnings?.length))
        .length ?? null,
    [indices],
  );

  return (
    <main className="workbench-page home-page">
      <header className="home-heading">
        <div>
          <p className="section-kicker">RESEARCH WORKBENCH</p>
          <h1>可信投研数据面板</h1>
          <p>
            独立浏览基金、ETF、指数和股票的结构化数据。页面不调用模型，
            市场数值全部来自审计数据服务。
          </p>
        </div>
        <div className="home-policy">
          <ShieldCheck aria-hidden="true" />
          <span>
            <strong>公开只读 · 审计事实</strong>
            日期、来源和内容指纹完整保留
          </span>
        </div>
      </header>

      <section className="home-status-strip" aria-label="数据状态">
        <div>
          <span>关注指数</span>
          <strong>{indices?.rows.length ?? "—"}</strong>
        </div>
        <div>
          <span>可用数据</span>
          <strong>{availableIndices ?? "—"}</strong>
        </div>
        <div>
          <span>数据警告</span>
          <strong>{warningCount ?? "—"}</strong>
        </div>
        <div>
          <span>当前状态</span>
          {indices ? <StatusBadge status={indices.status} /> : <b>加载中</b>}
        </div>
      </section>

      <section className="home-categories" aria-labelledby="category-title">
        <div className="home-section-heading">
          <div>
            <p className="section-kicker">DATA CATEGORIES</p>
            <h2 id="category-title">数据分类</h2>
          </div>
          <span>选择分类进入对应数据页</span>
        </div>

        <div className="category-grid data-category-grid">
          <Link className="category-card category-card-active" to="/indices">
            <BarChart3 aria-hidden="true" />
            <div>
              <span>指数</span>
              <strong>指数估值终端</strong>
              <p>点位、PE TTM、PB、历史分位与十年曲线</p>
            </div>
            <div className="category-card-meta">
              {indices ? <StatusBadge status={indices.status} /> : <span>加载中</span>}
              <b>
                {availableIndices === null ? "—" : availableIndices} 个可用
              </b>
            </div>
            <ArrowRight aria-hidden="true" />
          </Link>

          <Link className="category-card" to="/funds/510300">
            <Database aria-hidden="true" />
            <div>
              <span>基金 / ETF</span>
              <strong>ETF 数据终端</strong>
              <p>价格、成交额、成交量、涨跌幅与回撤五联图</p>
            </div>
            <div className="category-card-meta">
              <span className="category-ready">ETF 终端可用</span>
              <b>五联图</b>
            </div>
            <ArrowRight aria-hidden="true" />
          </Link>

          <Link className="category-card" to="/stocks">
            <Landmark aria-hidden="true" />
            <div>
              <span>股票</span>
              <strong>股票研究终端</strong>
              <p>前复权价格、PE TTM、PB 与公开研究背景</p>
            </div>
            <div className="category-card-meta">
              <span className="category-pending">页面待接入</span>
              <b>M3</b>
            </div>
            <ArrowRight aria-hidden="true" />
          </Link>

        </div>
      </section>
    </main>
  );
}
