import { createBrowserRouter } from "react-router";
import { AppShell } from "../components/AppShell.tsx";
import { NotFoundPage } from "../components/NotFoundPage.tsx";
import { LoginPage } from "../features/auth/LoginPage.tsx";
import { HomePage } from "../features/home/HomePage.tsx";
import { PapersPage } from "../features/papers/PapersPage.tsx";
import { ProfilePage } from "../features/profile/ProfilePage.tsx";
import { ComparePage } from "../features/compare/ComparePage.tsx";
import { QualityPage } from "../features/quality/QualityPage.tsx";
import { NotebookRoute, RunDetailRoute, RunsRoute, TablesRoute, WorkspaceRoute } from "./routeElements.tsx";
import { CorrectionRoute } from "./routeElements.tsx";

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "login", element: <LoginPage /> },
      { path: "papers", element: <PapersPage /> },
      { path: "profile", element: <ProfilePage /> },
      { path: "quality", element: <QualityPage /> },
      { path: "g/:projectId/:graphId", element: <WorkspaceRoute /> },
      { path: "g/:projectId/:graphId/runs", element: <RunsRoute /> },
      { path: "g/:projectId/:graphId/runs/:runId", element: <RunDetailRoute /> },
      { path: "g/:projectId/:graphId/compare", element: <ComparePage /> },
      { path: "g/:projectId/:graphId/tables", element: <TablesRoute /> },
      { path: "g/:projectId/:graphId/notebook", element: <NotebookRoute /> },
      { path: "g/:projectId/:graphId/review", element: <CorrectionRoute /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
