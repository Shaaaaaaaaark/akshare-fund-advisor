import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import WorkbenchLayout from "./layout/WorkbenchLayout";
import HomePage from "./pages/HomePage";
import IndicesPage from "./pages/IndicesPage";

const ChatPage = lazy(() => import("./pages/ChatPage"));
const FundProductPage = lazy(() => import("./pages/FundProductPage"));
const FundsPage = lazy(() => import("./pages/FundsPage"));
const IndexDetailPage = lazy(() => import("./pages/IndexDetailPage"));
const StockDetailPage = lazy(() => import("./pages/StockDetailPage"));
const WatchlistPage = lazy(() => import("./pages/WatchlistPage"));

export default function App() {
  // Vite 注入的部署子路径；去掉末尾斜杠以符合 React Router basename 约定。
  const basename = import.meta.env.BASE_URL.replace(/\/$/, "");
  return (
    <BrowserRouter basename={basename || undefined}>
      <Suspense fallback={<RouteLoading />}>
        <Routes>
          <Route element={<WorkbenchLayout />}>
            <Route path="/" element={<FundsPage />} />
            <Route path="/overview" element={<HomePage />} />
            <Route path="/indices" element={<IndicesPage />} />
            <Route path="/indices/:index" element={<IndexDetailPage />} />
            <Route path="/funds" element={<FundsPage />} />
            <Route
              path="/funds/:fund/product"
              element={<FundProductPage />}
            />
            <Route path="/funds/:fund" element={<FundsPage />} />
            <Route path="/stocks" element={<StockDetailPage />} />
            <Route path="/stocks/:stock" element={<StockDetailPage />} />
            <Route path="/watchlist" element={<WatchlistPage />} />
            <Route path="/chat" element={<ChatPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

function RouteLoading() {
  return (
    <div className="route-loading" role="status">
      正在加载页面
    </div>
  );
}
