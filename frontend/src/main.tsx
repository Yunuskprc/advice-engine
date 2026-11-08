import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router";
import "./index.css";
import Layout from "./components/Layout";
import HomePage from "./pages/HomePage";
import MovieDetailPage from "./pages/MovieDetailPage";
import PlaceholderPage from "./pages/PlaceholderPage";
import RatePage from "./pages/RatePage";
import SearchPage from "./pages/SearchPage";
import StatusPage from "./pages/StatusPage";
import TastePage from "./pages/TastePage";
import WatchlistPage from "./pages/WatchlistPage";

const queryClient = new QueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<HomePage />} />
            <Route path="puanla" element={<RatePage />} />
            <Route path="ara" element={<SearchPage />} />
            <Route path="film/:id" element={<MovieDetailPage />} />
            <Route path="zevkim" element={<TastePage />} />
            <Route path="listem" element={<WatchlistPage />} />
            <Route path="ayarlar" element={<StatusPage />} />
            <Route path="*" element={<PlaceholderPage title="Sayfa bulunamadı" />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
