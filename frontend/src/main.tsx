/**
 * React root — minimal entry for the upload UI (step 1c).
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./App.css";

const el = document.getElementById("root");
if (!el) {
  throw new Error("Missing #root element");
}

createRoot(el).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
