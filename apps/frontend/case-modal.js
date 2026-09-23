// Shared "Case Detail" modal for APD Detection, Vehicle Violation, and
// Case Violation pages — identical behavior everywhere a violation row
// can be clicked, so it lives once instead of three times.
//
// RBAC is enforced here AND on the backend (see auth.get_current_manager
// in apps/backend/app/main.py) — hiding a control client-side is a UX
// nicety, not the actual access control.

const CaseModal = {
  _auth: null,
  _onChange: null,
  _current: null,
  _operators: null, // cached list of {username, name} — fetched once, see init()
  // Namespaced onto the object (not a top-level const) on purpose: this
  // script and the page that loads it are both plain classic <script>
  // tags sharing one global scope, not modules — a top-level `const
  // STATUS_META` here collided with cases.html's own top-level
  // `STATUS_META` and threw "Identifier 'STATUS_META' has already been
  // declared" the moment the second script tag tried to run, silently
  // killing everything after it on that page.
  _STATUS_META: {
    baru: { label: "Baru" },
    diproses: { label: "Diproses" },
    selesai: { label: "Selesai" },
  },

  init(auth, { onChange } = {}) {
    this._auth = auth;
    this._onChange = onChange || (() => {});
    document.getElementById("caseModalRoot").addEventListener("click", (e) => {
      if (e.target.dataset.close !== undefined || e.target.id === "caseModalOverlay") this.close();
    });
  },

  async open(id) {
    const res = await this._auth.apiFetch(`/api/violations/${id}`);
    if (!res.ok) return;
    this._current = await res.json();
    await this._render();
  },

  close() {
    this._current = null;
    document.getElementById("caseModalRoot").innerHTML = "";
  },

  canManage() { return this._auth.hasAnyRole(["admin", "supervisor"]); },

  async _render() {
    const v = this._current;

    // Real operator accounts from Keycloak (User Management), fetched
    // once and cached — replaces an earlier hardcoded name list. Only
    // fetched when actually needed: a plain Operator never sees this
    // dropdown, and the endpoint is Supervisor/Admin-only anyway.
    if (v.is_case && this.canManage() && this._operators === null) {
      try {
        const res = await this._auth.apiFetch("/api/users/operators");
        this._operators = res.ok ? await res.json() : [];
      } catch {
        this._operators = [];
      }
    }
    const categoryLabel = v.category === "vehicle" ? "Vehicle Violation" : "APD Detection";

    const detailGridHtml = `
      <div class="detail-grid">
        <div><div class="k">Kategori</div><div class="v">${categoryLabel}</div></div>
        <div><div class="k">Kamera</div><div class="v">${v.camera_name || "Kamera #" + v.camera_id}</div></div>
        <div><div class="k">Waktu Deteksi</div><div class="v">${new Date(v.created_at).toLocaleString("id-ID")}</div></div>
      </div>`;

    const snapshotHtml = `
      <div class="snapshot-box">
        ${v.has_snapshot
          ? `<img src="/api/violations/${v.id}/snapshot?token=${encodeURIComponent(this._auth.accessToken)}&t=${Date.now()}" alt="Snapshot" id="caseSnapshotImg" />`
          : `<div class="placeholder"><svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 8l4-3h6l2 3h4a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z"/><circle cx="12" cy="13" r="3.2"/></svg><span style="font-size:0.76rem;color:var(--text-muted);">Tidak ada snapshot</span></div>`}
      </div>`;

    let bodyHtml;
    if (!v.is_case) {
      // Plain alert — every AI detection lands here first (ADR-0012). No
      // status/assign/notes yet; the only action is choosing to promote
      // it into a tracked case.
      bodyHtml = `
        ${snapshotHtml}
        ${detailGridHtml}
        <div style="display:flex; justify-content:flex-end;">
          <button class="btn-primary" id="casePromoteBtn">Jadikan Kasus Investigasi</button>
        </div>`;
    } else {
      const canManage = this.canManage();
      const statusStepsHtml = ["baru", "diproses", "selesai"].map((s) => {
        const disabled = s === "selesai" && !canManage;
        return `<button class="status-step${v.status === s ? " active-" + s : ""}" ${disabled ? "disabled" : ""} data-status="${s}">${this._STATUS_META[s].label}</button>`;
      }).join("");

      const assignHtml = canManage
        ? `<select id="caseAssignSelect">
             <option value="">Belum ditugaskan</option>
             ${(this._operators || []).map((op) => `<option value="${op.name}" ${v.assigned_to === op.name ? "selected" : ""}>${op.name}</option>`).join("")
               || `<option value="" disabled>Tidak ada operator terdaftar — lihat Manajemen User</option>`}
           </select>`
        : `<div class="readonly-note">${v.assigned_to || "Belum ditugaskan"} <span class="hint">&middot; hanya Supervisor/Admin yang bisa mengubah</span></div>`;

      const notesHtml = v.notes.length
        ? `<div class="notes-list">${v.notes.map((n) => `
            <div class="note-item">
              <div class="author">${n.author} <span class="time">&middot; ${new Date(n.created_at).toLocaleString("id-ID")}</span></div>
              <div class="text">${n.text}</div>
            </div>`).join("")}</div>`
        : `<div style="font-size:0.85rem;color:var(--text-muted);">Belum ada catatan.</div>`;

      bodyHtml = `
        ${snapshotHtml}
        ${detailGridHtml}
        <div style="margin-bottom:1.25rem;">
          <div style="font-size:0.78rem;font-weight:600;margin-bottom:0.5rem;">Status Penanganan</div>
          <div class="status-stepper">${statusStepsHtml}</div>
        </div>
        <div style="margin-bottom:1.25rem;">
          <label style="display:block;font-size:0.78rem;font-weight:600;margin-bottom:0.4rem;">Ditugaskan ke</label>
          ${assignHtml}
        </div>
        <div style="margin-bottom:1.25rem;">
          <div style="font-size:0.78rem;font-weight:600;margin-bottom:0.5rem;">Catatan Investigasi</div>
          ${notesHtml}
          <form class="note-form" id="caseNoteForm">
            <input type="text" id="caseNoteInput" placeholder="Tambah catatan..." required />
            <button type="submit" class="btn-primary">Kirim</button>
          </form>
        </div>
        <div style="display:flex; justify-content:flex-end; border-top:1px solid var(--border); padding-top:1rem;">
          <button class="link-btn" style="color:var(--text-muted);" id="caseUnpromoteBtn">Batalkan status kasus (kembalikan jadi alert biasa)</button>
        </div>`;
    }

    document.getElementById("caseModalRoot").innerHTML = `
      <div class="modal-overlay" id="caseModalOverlay">
        <div class="modal wide">
          <div class="modal-head">
            <div>
              <h3>${v.is_case ? `Detail Kasus — CASE-${String(v.id).padStart(4, "0")}` : "Detail Alert"}</h3>
              <div style="font-size:0.8rem;color:var(--text-muted);margin-top:0.15rem;">${v.label}</div>
            </div>
            <button class="modal-close" data-close>&times;</button>
          </div>
          <div class="modal-body">${bodyHtml}</div>
        </div>
      </div>`;

    const promoteBtn = document.getElementById("casePromoteBtn");
    if (promoteBtn) promoteBtn.addEventListener("click", () => this._setCase(true));
    const unpromoteBtn = document.getElementById("caseUnpromoteBtn");
    if (unpromoteBtn) unpromoteBtn.addEventListener("click", () => this._setCase(false));
    document.querySelectorAll(".status-step").forEach((btn) => {
      btn.addEventListener("click", () => this._setStatus(btn.dataset.status));
    });
    const assignSelect = document.getElementById("caseAssignSelect");
    if (assignSelect) assignSelect.addEventListener("change", () => this._assign(assignSelect.value));
    const noteForm = document.getElementById("caseNoteForm");
    if (noteForm) noteForm.addEventListener("submit", (e) => {
      e.preventDefault();
      this._addNote(document.getElementById("caseNoteInput").value.trim());
    });
  },

  async _setCase(is_case) {
    const res = await this._auth.apiFetch(`/api/violations/${this._current.id}/case`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ is_case }),
    });
    if (res.ok) {
      this._current = { ...this._current, ...(await res.json()) };
      await this._render();
      this._onChange();
    }
  },

  async _setStatus(status) {
    const res = await this._auth.apiFetch(`/api/violations/${this._current.id}/status`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }),
    });
    if (res.ok) {
      this._current = { ...this._current, ...(await res.json()) };
      await this._render();
      this._onChange();
    }
  },

  async _assign(assigned_to) {
    const res = await this._auth.apiFetch(`/api/violations/${this._current.id}/assign`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ assigned_to: assigned_to || null }),
    });
    if (res.ok) {
      this._current = { ...this._current, ...(await res.json()) };
      this._onChange();
    }
  },

  async _addNote(text) {
    if (!text) return;
    const res = await this._auth.apiFetch(`/api/violations/${this._current.id}/notes`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }),
    });
    if (res.ok) {
      document.getElementById("caseNoteInput").value = "";
      await this.open(this._current.id);
    }
  },
};
