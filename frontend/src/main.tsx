import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/bricolage-grotesque";
import "@fontsource-variable/atkinson-hyperlegible-next";
import "./styles.css";
import WirewiseApp from "./components/WirewiseApp";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <WirewiseApp />
  </StrictMode>,
);
