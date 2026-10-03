import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import App from "@/App";
import AppLayout from "@/AppLayout";
import GraphPage from "@/features/graph/GraphPage";
import { syncThemeWithOS } from "@/lib/theme";
import "@/index.css";

syncThemeWithOS();

const root = document.getElementById("root");
if (!root) throw new Error("Root element #root not found");

createRoot(root).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<App />} />
          <Route path="/c/:conversationId" element={<App />} />
          <Route path="/graph" element={<GraphPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
