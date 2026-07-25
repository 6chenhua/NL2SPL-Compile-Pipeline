import { useState, useEffect, useCallback } from "react";

export type AppRoute =
  | { type: "generate" }
  | { type: "workbench"; runId: string };

function parsePath(pathname: string): AppRoute {
  // pathname starts with /
  const parts = pathname.split("/").filter(Boolean);
  if (parts[0] === "runs" && parts[1]) {
    return { type: "workbench", runId: parts[1] };
  }
  return { type: "generate" };
}

export function useAppRoute() {
  const [route, setRoute] = useState<AppRoute>(() => parsePath(window.location.pathname));

  useEffect(() => {
    const handlePopState = () => {
      setRoute(parsePath(window.location.pathname));
    };
    window.addEventListener("popstate", handlePopState);
    return () => {
      window.removeEventListener("popstate", handlePopState);
    };
  }, []);

  const navigate = useCallback((path: string) => {
    window.history.pushState(null, "", path);
    setRoute(parsePath(path));
  }, []);

  return {
    route,
    navigate,
  };
}
