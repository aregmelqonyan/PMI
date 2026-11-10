import { FileStack, FlaskConical, Gauge, Layers3 } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { loadReviewer, saveReviewer } from "./format";
import DocumentsPage from "./pages/DocumentsPage";
import EvaluationPage from "./pages/EvaluationPage";
import PlaygroundPage from "./pages/PlaygroundPage";
import WorkspacePage from "./pages/WorkspacePage";

interface AppContextValue {
  reviewer: string;
  notify: (message: string, kind?: "info" | "error") => void;
}

const AppContext = createContext<AppContextValue>({ reviewer: "reviewer", notify: () => undefined });
export const useApp = () => useContext(AppContext);

function Provider({ reviewer, children }: { reviewer: string; children: (toast: ReactNode) => ReactNode }) {
  const [toast, setToast] = useState<{ message: string; kind: "info" | "error" } | null>(null);
  const timer = useRef<number>();
  const notify = useCallback((message: string, kind: "info" | "error" = "info") => {
    setToast({ message, kind });
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setToast(null), kind === "error" ? 7000 : 3500);
  }, []);
  const value = useMemo(() => ({ reviewer, notify }), [reviewer, notify]);
  const element = toast ? (
    <div className={`toast toast-${toast.kind}`} role="status">
      {toast.message}
    </div>
  ) : null;
  return <AppContext.Provider value={value}>{children(element)}</AppContext.Provider>;
}

const NAV = [
  { to: "/documents", label: "Documents", icon: FileStack },
  { to: "/playground", label: "Try a sentence", icon: FlaskConical },
  { to: "/evaluation", label: "Evaluation", icon: Gauge },
];

export default function App() {
  const [reviewer, setReviewer] = useState(loadReviewer);
  return (
    <Provider reviewer={reviewer.trim() || "reviewer"}>
      {(toast) => (
        <div className="shell">
          <aside className="rail">
            <div className="brand">
              <span className="brand-mark" aria-hidden>
                <Layers3 size={18} />
              </span>
              <div>
                <div className="brand-name">EngiReq-AI</div>
                <div className="brand-sub">Interim pilot</div>
              </div>
            </div>
            <nav>
              {NAV.map(({ to, label, icon: Icon }) => (
                <NavLink key={to} to={to} className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
                  <Icon size={17} />
                  <span>{label}</span>
                </NavLink>
              ))}
            </nav>
            <div className="rail-foot">
              <label className="reviewer">
                <span>Reviewer</span>
                <input
                  value={reviewer}
                  maxLength={80}
                  onChange={(event) => {
                    setReviewer(event.target.value);
                    saveReviewer(event.target.value);
                  }}
                />
              </label>
              <p>Research prototype. Every record needs approval from a qualified engineer.</p>
            </div>
          </aside>
          <main className="content">
            <Routes>
              <Route path="/" element={<Navigate to="/documents" replace />} />
              <Route path="/documents" element={<DocumentsPage />} />
              <Route path="/documents/:id" element={<WorkspacePage />} />
              <Route path="/playground" element={<PlaygroundPage />} />
              <Route path="/evaluation" element={<EvaluationPage />} />
              <Route path="*" element={<Navigate to="/documents" replace />} />
            </Routes>
          </main>
          {toast}
        </div>
      )}
    </Provider>
  );
}
