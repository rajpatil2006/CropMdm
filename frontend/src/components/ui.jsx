// Small presentational building blocks shared by every page.

export function Panel({ title, subtitle, icon, actions, className = "", children }) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions || icon) && (
        <div className="panel-heading">
          <div>
            {title && <h3>{title}</h3>}
            {subtitle && <p>{subtitle}</p>}
          </div>
          <div className="panel-actions">
            {actions}
            {icon}
          </div>
        </div>
      )}
      {children}
    </section>
  );
}

export function Row({ label, value }) {
  return (
    <div className="status-row">
      <span>{label}</span>
      <strong>{value ?? "--"}</strong>
    </div>
  );
}

export function MetricCard({ title, value, unit, icon: Icon, color }) {
  const empty = value === null || value === undefined;
  return (
    <div className="metric-card">
      <div className="metric-top">
        <span>{title}</span>
        {Icon && <Icon size={22} color={color} />}
      </div>
      <div className="metric-value">
        {empty ? "--" : value}
        {!empty && <span className="metric-unit">{unit}</span>}
      </div>
    </div>
  );
}

export function StatCard({ label, value, tone }) {
  return (
    <div className={`stat-card ${tone ? `stat-${tone}` : ""}`}>
      <span>{label}</span>
      <strong>{value ?? "--"}</strong>
    </div>
  );
}

export function Badge({ tone = "neutral", children }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function EmptyState({ children }) {
  return <p className="empty-state">{children}</p>;
}

export function Alert({ tone = "error", children }) {
  if (!children) return null;
  return <div className={`alert alert-${tone}`}>{children}</div>;
}

export function PageHeader({ eyebrow, title, subtitle, actions }) {
  return (
    <header className="page-header">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h2>{title}</h2>
        {subtitle && <p className="subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}
