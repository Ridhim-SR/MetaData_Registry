import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { RegistryLayout } from "./components/RegistryLayout";
import { AboutPage } from "./pages/About";
import { ContactPage } from "./pages/Contact";
import { DashboardPage } from "./pages/Dashboard";
import { DatasetDetailPage } from "./pages/DatasetDetail";
import { DepartmentDetailPage } from "./pages/DepartmentDetail";
import { DepartmentsPage } from "./pages/Departments";
import { IngestionPage } from "./pages/Ingestion";
import { LoginPage } from "./pages/Login";
import { OAuthCallbackPage } from "./pages/OAuthCallback";
import { PrivacyPolicyPage } from "./pages/PrivacyPolicy";
import { CopyrightsPolicyPage } from "./pages/CopyrightsPolicy";
import { RegisterPage } from "./pages/Register";
import { RegistryHomePage } from "./pages/RegistryHome";
import { UsersPage } from "./pages/Users";
import { ExplorePage } from "./pages/Explore";
import { TableDetailPage } from "./pages/TableDetail";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/auth/callback/:provider" element={<OAuthCallbackPage />} />
        <Route element={<RegistryLayout />}>
          <Route index element={<RegistryHomePage />} />
          <Route path="explore" element={<ExplorePage />} />
          <Route path="explore/:tableId" element={<TableDetailPage />} />
          <Route path="datasets/:datasetFqn" element={<DatasetDetailPage />} />
          <Route path="departments" element={<DepartmentsPage />} />
          <Route path="departments/:slug" element={<DepartmentDetailPage />} />
          <Route path="about" element={<AboutPage />} />
          <Route path="contact" element={<ContactPage />} />
          <Route path="privacy" element={<PrivacyPolicyPage />} />
          <Route path="copyrights" element={<CopyrightsPolicyPage />} />
        </Route>
        <Route
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="users" element={<UsersPage />} />
          <Route path="ingestion" element={<IngestionPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
