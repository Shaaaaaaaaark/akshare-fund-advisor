import { ArrowRight, Bot, Database, Landmark } from "lucide-react";
import { Link } from "react-router-dom";

interface PendingCategoryPageProps {
  category: "funds" | "stocks";
}

const CONTENT = {
  funds: {
    kicker: "FUND DATA",
    title: "基金搜索与详情",
    description:
      "基金目录、产品档案、评级、净值风险和申赎状态的页面契约正在接入。",
    boundary:
      "当前不展示未聚合的基金列表，避免把不完整数据伪装成产品能力。",
    question: "搜索并分析基金 000001",
    icon: Database,
  },
  stocks: {
    kicker: "STOCK DATA",
    title: "股票估值与详情",
    description:
      "个股前复权价格、PE TTM、PB 和研究动态页面将在指数工作台之后接入。",
    boundary:
      "stock_screen 尚未实现，因此不会展示模型生成的股票候选或综合分数。",
    question: "分析贵州茅台的估值与风险",
    icon: Landmark,
  },
};

export default function PendingCategoryPage({
  category,
}: PendingCategoryPageProps) {
  const content = CONTENT[category];
  const Icon = content.icon;

  return (
    <main className="workbench-page pending-category-page">
      <section className="pending-category-content">
        <Icon aria-hidden="true" />
        <p className="section-kicker">{content.kicker}</p>
        <h1>{content.title}</h1>
        <p>{content.description}</p>

        <div className="pending-boundary">
          <strong>当前边界</strong>
          <span>{content.boundary}</span>
        </div>

        <div className="pending-actions">
          <Link
            className="primary-link"
            to="/chat"
            state={{ initialQuestion: content.question }}
          >
            <Bot aria-hidden="true" />
            先用 Agent 研究
            <ArrowRight aria-hidden="true" />
          </Link>
          <Link className="secondary-link" to="/">
            返回总览
          </Link>
        </div>
      </section>
    </main>
  );
}
