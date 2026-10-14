import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Activity,
  BrainCircuit,
  Cpu,
  LayoutDashboard,
  LogOut,
  Menu,
  Sprout,
  UserCircle,
  Users,
  X,
} from "lucide-react";
import { useAuth } from "../auth/context";
import { useI18n } from "../i18n/context";
import LanguageSwitcher from "./LanguageSwitcher";

function navFor(role, t) {
  if (role === "admin") {
    return [
      { to: "/admin", label: "Overview", icon: LayoutDashboard, end: true },
      { to: "/admin/farmers", label: "Farmers", icon: Users },
      { to: "/admin/devices", label: "Devices", icon: Cpu },
      { to: "/admin/model", label: "AI model", icon: BrainCircuit },
      { to: "/admin/health", label: "Health & logs", icon: Activity },
      { to: "/account", label: "My account", icon: UserCircle },
    ];
  }
  return [
    { to: "/farm", label: t("nav.myFarms"), icon: Sprout, end: true },
    { to: "/account", label: t("nav.account"), icon: UserCircle },
  ];
}

export default function AppShell() {
  const { user, logout } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const items = navFor(user.role, t);

  function signOut() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="shell">
      <aside className={`sidebar ${menuOpen ? "sidebar-open" : ""}`}>
        <div className="brand">
          <div className="brand-icon">
            <Sprout size={22} />
          </div>
          <div>
            <h1>{t("app.name")}</h1>
            <p>{user.role === "admin" ? "Admin console" : t("app.tagline")}</p>
          </div>
          <button className="menu-close" onClick={() => setMenuOpen(false)} aria-label="Close menu">
            <X size={20} />
          </button>
        </div>

        <nav className="nav">
          {items.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} onClick={() => setMenuOpen(false)}
              className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="user-chip">
            <UserCircle size={30} />
            <div>
              <strong>{user.name || user.username}</strong>
              <span>{user.role === "admin" ? "Administrator" : user.village || user.username}</span>
            </div>
          </div>
          <button className="nav-link logout" onClick={signOut}>
            <LogOut size={18} />
            {t("common.logout")}
          </button>
        </div>
      </aside>
      {menuOpen && <div className="scrim" onClick={() => setMenuOpen(false)} />}

      <div className="main">
        <header className="topbar">
          <button className="menu-button" onClick={() => setMenuOpen(true)} aria-label="Open menu">
            <Menu size={22} />
          </button>
          <div className="topbar-spacer" />
          <LanguageSwitcher />
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
