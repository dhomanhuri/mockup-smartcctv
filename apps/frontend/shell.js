// Shared header + sidebar shell for every authenticated page (Dashboard,
// APD Detection, Vehicle Violation, Case Violation, Laporan & Analitik,
// Pengaturan). admin.html keeps its own simpler header-only layout since
// it's already a distinct "portal" by role, not part of the main nav.
//
// This factors out what the design canvas mockup duplicated per-artboard
// (an accepted limitation there — "artboards share nothing at runtime")
// into one real module, since the real app has no such constraint. Each
// page calls `Shell.mount({active})` once, after `Auth.init()` resolves,
// so the header/sidebar can reflect the actual logged-in user's real
// role — there is no "preview as" switcher here like the mockup had;
// production just shows what the token says.

// Global safety net, in addition to each page's own try/catch around its
// init IIFE — catches anything that slips past that (an error thrown from
// an event handler, an unhandled promise rejection) so a real failure is
// never just silent whitespace where the dashboard should be.
window.addEventListener("error", (e) => Shell.showFatalError(e.error || e.message));
window.addEventListener("unhandledrejection", (e) => Shell.showFatalError(e.reason));

const ROLE_LABELS = { admin: "Admin", supervisor: "Supervisor", operator: "Operator" };

function primaryRoleLabel(roles) {
  if (roles.includes("admin")) return ROLE_LABELS.admin;
  if (roles.includes("supervisor")) return ROLE_LABELS.supervisor;
  return ROLE_LABELS.operator;
}

function initials(name) {
  return (name || "?").split(" ").filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
}

const ICONS = {
  dashboard: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></svg>',
  hardhat: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M4 15.5V15a8 8 0 0 1 16 0v0.5"/><rect x="3" y="15.5" width="18" height="3" rx="1.2"/><path d="M12 6.5v2.2"/></svg>',
  truck: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="2" y="6" width="11" height="10" rx="1"/><path d="M13 10h4l3 3v3h-7z"/><circle cx="6.5" cy="18" r="1.8"/><circle cx="17" cy="18" r="1.8"/></svg>',
  case: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M9 3h6a1 1 0 0 1 1 1v1H8V4a1 1 0 0 1 1-1z"/><rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 12.5l2 2 4-4.5"/></svg>',
  reports: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M4 19V11"/><path d="M10 19V5"/><path d="M16 19v-7"/><path d="M4 19h16"/></svg>',
  settings: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><line x1="4" y1="6" x2="20" y2="6"/><circle cx="9" cy="6" r="1.8" fill="#fff"/><line x1="4" y1="12" x2="20" y2="12"/><circle cx="15" cy="12" r="1.8" fill="#fff"/><line x1="4" y1="18" x2="20" y2="18"/><circle cx="7" cy="18" r="1.8" fill="#fff"/></svg>',
  users: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
};

const NAV = [
  { group: "Overview", items: [{ key: "dashboard", href: "index.html", label: "Dashboard", icon: "dashboard" }] },
  { group: "Deteksi", items: [
    { key: "apd", href: "apd.html", label: "APD Detection", icon: "hardhat" },
    { key: "vehicle", href: "vehicle.html", label: "Vehicle Violation", icon: "truck" },
  ] },
  { group: "Operasional", items: [
    { key: "cases", href: "cases.html", label: "Case Violation", icon: "case" },
    { key: "reports", href: "reports.html", label: "Laporan & Analitik", icon: "reports" },
  ] },
  { group: "Platform", items: [
    { key: "settings", href: "settings.html", label: "Pengaturan", icon: "settings", adminOnly: true },
    { key: "admin", href: "admin.html", label: "Manajemen User", icon: "users", adminOnly: true },
  ] },
];

const Shell = {
  headerHtml(auth) {
    const roleLabel = primaryRoleLabel(auth.roles || []);
    return `
      <div class="brand">
        <img src="pertamina-ep-logo.jpg" alt="Pertamina EP" />
        <div class="divider"></div>
        <div>
          <h1>Smart CCTV AI</h1>
          <div class="sub">Safety &amp; Vehicle Violation Detection</div>
        </div>
      </div>
      <div class="header-right">
        <span class="portal-pill${roleLabel === "Admin" ? " admin" : ""}">${roleLabel}</span>
        <div class="user-chip">
          <div class="avatar">${initials(auth.name)}</div>
          <span class="name">${auth.name || auth.username || ""}</span>
          <button class="logout-btn" id="shellLogoutBtn">Keluar</button>
        </div>
      </div>`;
  },

  sidebarHtml(active, auth) {
    const roles = auth.roles || [];
    const isAdmin = roles.includes("admin");
    return NAV.map(({ group, items }) => {
      const visible = items.filter((it) => !it.adminOnly || isAdmin);
      if (!visible.length) return "";
      const rows = visible.map((it) => `
        <a class="nav-item${it.key === active ? " active" : ""}" href="${it.href}">
          ${ICONS[it.icon]}
          <span>${it.label}</span>
        </a>`).join("");
      return `<div class="nav-group-label">${group}</div>${rows}`;
    }).join("");
  },

  mount({ active, auth }) {
    const headerSlot = document.getElementById("shell-header");
    const sidebarSlot = document.getElementById("shell-sidebar");
    if (headerSlot) headerSlot.innerHTML = this.headerHtml(auth);
    if (sidebarSlot) sidebarSlot.innerHTML = this.sidebarHtml(active, auth);
    const logoutBtn = document.getElementById("shellLogoutBtn");
    if (logoutBtn) logoutBtn.addEventListener("click", () => auth.logout());
  },

  // A page's init script can silently do nothing if any step throws —
  // the async IIFE just stops, leaving whatever already rendered (often
  // just the static shell) with no visible sign anything went wrong.
  // Every page's top-level script wraps its init in
  // `try { ... } catch (err) { Shell.showFatalError(err); }` so a real
  // failure is visible on the page itself, not only in the console.
  showFatalError(err){
    console.error(err);
    const box = document.createElement("div");
    box.style.cssText = "position:fixed;inset:auto 1rem 1rem 1rem;max-width:640px;margin:0 auto;background:#A3001A;color:#fff;padding:0.9rem 1.1rem;border-radius:8px;font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:0.78rem;white-space:pre-wrap;z-index:999;box-shadow:0 10px 30px -10px rgba(0,0,0,0.5);";
    box.textContent = `Halaman gagal memuat data: ${err && err.message ? err.message : err}`;
    document.body.appendChild(box);
  },
};
