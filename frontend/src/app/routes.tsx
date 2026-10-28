import { createBrowserRouter } from "react-router";
import { AppShell } from "../components/AppShell.tsx";
import { NotFoundPage } from "../components/NotFoundPage.tsx";
import { HomePage } from "../features/home/HomePage.tsx";
import { ComparePage } from "../features/compare/ComparePage.tsx";
import { RunDetailRoute, RunsRoute, TablesRoute, WorkspaceRoute } from "./routeElements.tsx";
import { CorrectionRoute } from "./routeElements.tsx";

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "g/:projectId/:graphId", element: <WorkspaceRoute /> },
      { path: "g/:projectId/:graphId/runs", element: <RunsRoute /> },
      { path: "g/:projectId/:graphId/runs/:runId", element: <RunDetailRoute /> },
      { path: "g/:projectId/:graphId/compare", element: <ComparePage /> },
      { path: "g/:projectId/:graphId/tables", element: <TablesRoute /> },
      { path: "g/:projectId/:graphId/review", element: <CorrectionRoute /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
