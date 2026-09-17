import { createRoot } from "react-dom/client";
import { ReaderApp } from "@/components/reader-app";
import "@/app/globals.css";

const root = document.getElementById("root");
if (!root) throw new Error("找不到論文閱讀入口。");
// Retain links from the original eight-paper guide homepage.
const legacy = /^#paper=(\d{2})(?:&.*)?$/.exec(window.location.hash);
if (legacy) window.history.replaceState(null, "", `#guide:paper-${legacy[1]}`);
createRoot(root).render(<ReaderApp />);
