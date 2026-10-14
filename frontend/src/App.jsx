import { Navigate, Route, Routes } from "react-router-dom";
import { homeFor, useAuth } from "./auth/context";
import AppShell from "./components/AppShell";
import RequireRole from "./components/RequireRole";
import AccountPage from "./pages/AccountPage";
import AdminDevices from "./pages/admin/AdminDevices";
import AdminFarmers from "./pages/admin/AdminFarmers";
import AdminHealth from "./pages/admin/AdminHealth";
import AdminModel from "./pages/admin/AdminModel";
import AdminOverview from "./pages/admin/AdminOverview";
import DevicePage from "./pages/DevicePage";
import FarmerHome from "./pages/farmer/FarmerHome";
import LoginPage from "./pages/LoginPage";
import NotFoundPage from "./pages/NotFoundPage";
import RegisterPage from "./pages/RegisterPage";

function Home() {
  const { user, ready } = useAuth();
  if (!ready) return <div className="splash">CropMind…</div>;
  return <Navigate to={user ? homeFor(user) : "/login"} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Farmer dashboard */}
      <Route element={<RequireRole roles={["farmer"]} />}>
        <Route element={<AppShell />}>
          <Route path="/farm" element={<FarmerHome />} />
          <Route path="/farm/:deviceId" element={<DevicePage />} />
        </Route>
      </Route>

      {/* Admin console */}
      <Route element={<RequireRole roles={["admin"]} />}>
        <Route element={<AppShell />}>
          <Route path="/admin" element={<AdminOverview />} />
          <Route path="/admin/farmers" element={<AdminFarmers />} />
          <Route path="/admin/devices" element={<AdminDevices />} />
          <Route path="/admin/devices/:deviceId" element={<DevicePage />} />
          <Route path="/admin/model" element={<AdminModel />} />
          <Route path="/admin/health" element={<AdminHealth />} />
        </Route>
      </Route>

      {/* Both roles */}
      <Route element={<RequireRole roles={["farmer", "admin"]} />}>
        <Route element={<AppShell />}>
          <Route path="/account" element={<AccountPage />} />
        </Route>
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
