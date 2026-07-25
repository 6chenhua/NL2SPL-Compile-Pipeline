import { useMemo } from "react";
import type { SplWebDemoClient } from "./api";
import { createSplWebDemoClient } from "./api";
import { useAppRoute } from "./routing/useAppRoute";
import GeneratePage from "./pages/GeneratePage";
import SplWorkbenchPage from "./pages/SplWorkbenchPage";

interface AppProps {
  client?: SplWebDemoClient;
}

export default function App({ client: suppliedClient }: AppProps) {
  const client = useMemo(
    () => suppliedClient ?? createSplWebDemoClient(),
    [suppliedClient],
  );

  const { route, navigate } = useAppRoute();

  if (route.type === "workbench") {
    return (
      <SplWorkbenchPage
        client={client}
        runId={route.runId}
        onNavigate={navigate}
      />
    );
  }

  return (
    <GeneratePage
      client={client}
      onNavigate={navigate}
    />
  );
}
