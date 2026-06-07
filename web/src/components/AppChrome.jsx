import { Button } from "tdesign-react";
import { LanguageToggle, useI18n } from "../i18n.jsx";

export function AppChrome({ page, onNavigate, children }) {
  const { t } = useI18n();
  const items = [
    { id: "home", label: t("home") },
    { id: "workbench", label: t("analysisWorkspace") },
    { id: "plot", label: t("plotStudio") },
    { id: "lab", label: t("experimentDesign") },
    { id: "reports", label: t("reports") },
    { id: "subscription", label: t("subscription") },
    { id: "docs", label: t("guide") },
  ];

  if (page === "workbench") {
    return <div className="app-frame workbench-frame">{children}</div>;
  }

  return (
    <div className="app-frame">
      <header className="topbar">
        <button className="brand" onClick={() => onNavigate("home")}>
          <span className="brand-mark">Y</span>
          <span>
            <strong>YZW Cloud</strong>
            <small>{t("bioinformaticsWorkflow")}</small>
          </span>
        </button>
        <nav className="topnav">
          {items.map((item) => (
            <Button
              className={page === item.id ? "active" : ""}
              key={item.id}
              onClick={() => onNavigate(item.id)}
              shape="round"
              theme={page === item.id ? "primary" : "default"}
              variant={page === item.id ? "base" : "text"}
            >
              {item.label}
            </Button>
          ))}
        </nav>
        <LanguageToggle />
      </header>
      {children}
    </div>
  );
}
