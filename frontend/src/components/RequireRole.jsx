import { Navigate, Outlet, useLocation } from "react-router-dom";
import { homeFor, useAuth } from "../auth/context";

/** Only render child routes for logged-in users with one of `roles`. */
export default function RequireRole({ roles }) {
  const { user, ready } = useAuth();
  const location = useLocation();

  if (!ready) return <div className="splash">CropMind…</div>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (roles && !roles.includes(user.role)) return <Navigate to={homeFor(user)} replace />;
  return <Outlet />;
}
