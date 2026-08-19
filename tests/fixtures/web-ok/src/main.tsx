import { createRoot } from "react-dom/client";
import { greeting } from "./greeting";

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(<h1>{greeting("Datum")}</h1>);
}
