import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { DashboardPage } from "./pages/Dashboard";
import { IngestionPage } from "./pages/Ingestion";
import { LoginPage } from "./pages/Login";
import { RegisterPage } from "./pages/Register";
import { UsersPage } from "./pages/Users";
import { ExplorePage } from "./pages/Explore";
import { TableDetailPage } from "./pages/TableDetail";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<DashboardPage />} />
          <Route path="explore" element={<ExplorePage />} />
          <Route path="explore/:tableId" element={<TableDetailPage />} />
          <Route path="users" element={<UsersPage />} />
          <Route path="ingestion" element={<IngestionPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
