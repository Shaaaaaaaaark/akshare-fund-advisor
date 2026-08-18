import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import WorkbenchLayout from "./layout/WorkbenchLayout";
import HomePage from "./pages/HomePage";
import IndicesPage from "./pages/IndicesPage";
import PendingCategoryPage from "./pages/PendingCategoryPage";

const ChatPage = lazy(() => import("./pages/ChatPage"));
const FundsPage = lazy(() => import("./pages/FundsPage"));
const IndexDetailPage = lazy(() => import("./pages/IndexDetailPage"));

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<RouteLoading />}>
        <Routes>
          <Route element={<WorkbenchLayout />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/indices" element={<IndicesPage />} />
            <Route path="/indices/:index" element={<IndexDetailPage />} />
            <Route path="/funds" element={<FundsPage />} />
            <Route path="/funds/:fund" element={<FundsPage />} />
            <Route
              path="/stocks"
              element={<PendingCategoryPage category="stocks" />}
            />
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
