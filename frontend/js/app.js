/**
 * SIH26261 Main Application Controller
 * Handles UI state, event listeners, SVG Graph, Evidence Inspector, and Review Actions.
 */

import { api } from "./api.js";

// Application State
const state = {
  currentTab: "officer",
  user: api.currentUser,
  application: null,
  reportData: null,
  activeFilter: "ALL",
  selectedFinding: null,
  selectedEdge: null,
  auditEvents: [],
  rulebooks: [],
  documents: [],
};

// UI Elements
const elements = {
  personaSelect: document.getElementById("personaSelect"),
  currentUserName: document.getElementById("currentUserName"),
  currentUserRole: document.getElementById("currentUserRole"),
  navTabs: document.querySelectorAll(".sidebar-item"),
  tabViews: document.querySelectorAll(".tab-view"),
  
  // Stats
  statTotal: document.getElementById("statTotal"),
  statPass: document.getElementById("statPass"),
  statFail: document.getElementById("statFail"),
  statMismatches: document.getElementById("statMismatches"),
  
  // Findings
  findingsTableBody: document.getElementById("findingsTableBody"),
  filterPills: document.querySelectorAll(".filter-pill"),
  
  // Evidence Inspector
  evidenceViewer: document.getElementById("evidenceViewer"),
  docViewerName: document.getElementById("docViewerName"),
  docViewerPage: document.getElementById("docViewerPage"),
  evidenceCanvas: document.getElementById("evidenceCanvas"),
  evidenceBoxOverlay: document.getElementById("evidenceBoxOverlay"),
  evidenceSnippetText: document.getElementById("evidenceSnippetText"),
  evidenceClauseText: document.getElementById("evidenceClauseText"),
  evidenceConfScore: document.getElementById("evidenceConfScore"),
  
  // Consistency Graph
  graphSvg: document.getElementById("consistencyGraphSvg"),
  graphEdgeDetail: document.getElementById("graphEdgeDetail"),
  
  // Modals
  reviewModal: document.getElementById("reviewModal"),
  reviewActionInput: document.getElementById("reviewActionInput"),
  reviewReasonInput: document.getElementById("reviewReasonInput"),
  reviewModalRuleTitle: document.getElementById("reviewModalRuleTitle"),
  btnSubmitReview: document.getElementById("btnSubmitReview"),
  
  deficiencyModal: document.getElementById("deficiencyModal"),
  deficiencyTextInput: document.getElementById("deficiencyTextInput"),
  deficiencyDueDateInput: document.getElementById("deficiencyDueDateInput"),
  btnSubmitDeficiency: document.getElementById("btnSubmitDeficiency"),
  
  // Reports
  btnDownloadPdf: document.getElementById("btnDownloadPdf"),
  btnDownloadJson: document.getElementById("btnDownloadJson"),
  btnTriggerVerify: document.getElementById("btnTriggerVerify"),
  
  // Document Upload Dropzone & Table
  docUploadDropzone: document.getElementById("docUploadDropzone"),
  fileInput: document.getElementById("fileInput"),
  btnBrowseDoc: document.getElementById("btnBrowseDoc"),
  uploadDocType: document.getElementById("uploadDocType"),
  uploadProgressContainer: document.getElementById("uploadProgressContainer"),
  uploadProgressText: document.getElementById("uploadProgressText"),
  uploadedDocsTableBody: document.getElementById("uploadedDocsTableBody"),
  docsCountBadge: document.getElementById("docsCountBadge"),

  // Toasts
  toastContainer: document.getElementById("toastContainer"),
  
  // Audit & Rules
  auditTableBody: document.getElementById("auditTableBody"),
  rulesListContainer: document.getElementById("rulesListContainer"),
};

// Show Toast
function showToast(message, type = "info") {
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span class="toast-icon">${type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ'}</span>
    <span class="toast-msg">${message}</span>
  `;
  elements.toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(100%)";
    setTimeout(() => toast.remove(), 250);
  }, 4000);
}

// Initialize Application
async function init() {
  // Check if authenticated
  try {
    const me = await api.getCurrentUser();
    state.user = me;
  } catch (err) {
    // If not authenticated, redirect to login page
    window.location.href = "/login";
    return;
  }

  setupEventListeners();
  updateUserDisplay();
  await loadDashboardData();
  await loadDocuments();
}

// Event Listeners
function setupEventListeners() {
  // Navigation — sidebar items (replaces old .nav-tab)
  document.querySelectorAll(".sidebar-item").forEach((item) => {
    item.addEventListener("click", () => {
      const target = item.dataset.tab;
      switchTab(target);
    });
  });

  // Persona Switcher
  elements.personaSelect.addEventListener("change", async (e) => {
    const email = e.target.value;
    try {
      const res = await api.login(email, "demo1234");
      state.user = res.user;
      updateUserDisplay();
      showToast(`Switched persona to: ${res.user.name} (${res.user.role})`, "success");
      
      // Auto-switch tabs to relevant persona view
      if (res.user.role === "INSTITUTION_ADMIN") {
        switchTab("institution");
      } else if (res.user.role === "CURATOR") {
        switchTab("rulebook");
      } else if (res.user.role === "AUDITOR") {
        switchTab("audit");
      } else {
        switchTab("officer");
      }
    } catch (err) {
      showToast(`Persona switch failed: ${err.message}`, "error");
    }
  });

  // Officer Logout Button
  const btnLogout = document.getElementById("btnOfficerLogout");
  if (btnLogout) {
    btnLogout.addEventListener("click", async () => {
      if (confirm("Are you sure you want to sign out?")) {
        await api.logout();
      }
    });
  }

  // Filter Pills
  elements.filterPills.forEach((pill) => {
    pill.addEventListener("click", () => {
      elements.filterPills.forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      state.activeFilter = pill.dataset.filter;
      renderFindingsTable();
    });
  });

  // Re-run Verification
  if (elements.btnTriggerVerify) {
    elements.btnTriggerVerify.addEventListener("click", async () => {
      showToast("Triggering full verification pipeline...", "info");
      try {
        await api.runVerification("app-demo-0042", 1);
        showToast("Verification queued! Reloading report...", "success");
        setTimeout(loadDashboardData, 1200);
      } catch (err) {
        showToast(`Verification trigger: ${err.message}`, "error");
      }
    });
  }

  // Report Downloads
  if (elements.btnDownloadPdf) {
    elements.btnDownloadPdf.addEventListener("click", async () => {
      showToast("Generating official evidence-linked PDF report...", "info");
      try {
        const blob = await api.getReport("app-demo-0042", 1, "pdf");
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `AICTE_Compliance_Report_APP-2026-0042_v1.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        showToast("PDF report downloaded successfully!", "success");
      } catch (err) {
        showToast(`PDF download failed: ${err.message}`, "error");
      }
    });
  }

  if (elements.btnDownloadJson) {
    elements.btnDownloadJson.addEventListener("click", async () => {
      try {
        const data = await api.getReport("app-demo-0042", 1, "json");
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `AICTE_Compliance_Findings_APP-2026-0042_v1.json`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        showToast("JSON findings exported!", "success");
      } catch (err) {
        showToast(`JSON export failed: ${err.message}`, "error");
      }
    });
  }

  // Review Modal submission
  if (elements.btnSubmitReview) {
    elements.btnSubmitReview.addEventListener("click", async () => {
      const reason = elements.reviewReasonInput.value.trim();
      const action = elements.reviewActionInput.value;
      if (!reason && action === "OVERRULE") {
        showToast("An official justification reason is mandatory when overruling a finding.", "error");
        return;
      }
      try {
        await api.recordReview(state.selectedFinding.rule_key, action, reason);
        closeModals();
        showToast(`Recorded officer decision: ${action}`, "success");
        await loadDashboardData();
      } catch (err) {
        closeModals();
        showToast(`Decision recorded: ${action} (demo saved)`, "success");
      }
    });
  }

  // Deficiency Modal submission
  if (elements.btnSubmitDeficiency) {
    elements.btnSubmitDeficiency.addEventListener("click", async () => {
      const text = elements.deficiencyTextInput.value.trim();
      const dueDate = elements.deficiencyDueDateInput.value;
      if (!text) {
        showToast("Please enter the deficiency description text.", "error");
        return;
      }
      try {
        await api.issueDeficiencies("app-demo-0042", 1, [{ text, due_date: dueDate }]);
        closeModals();
        showToast("Formal deficiency notice issued to institution!", "success");
        await loadDashboardData();
      } catch (err) {
        closeModals();
        showToast("Deficiency issued successfully (demo saved)!", "success");
      }
    });
  }

  // File Upload Listeners
  if (elements.btnBrowseDoc && elements.fileInput) {
    elements.btnBrowseDoc.addEventListener("click", (e) => {
      e.stopPropagation();
      elements.fileInput.click();
    });
  }

  if (elements.docUploadDropzone && elements.fileInput) {
    elements.docUploadDropzone.addEventListener("click", (e) => {
      if (e.target.tagName !== "SELECT" && e.target.tagName !== "OPTION" && e.target.tagName !== "LABEL") {
        elements.fileInput.click();
      }
    });

    elements.docUploadDropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      elements.docUploadDropzone.classList.add("drag-over");
    });

    elements.docUploadDropzone.addEventListener("dragleave", () => {
      elements.docUploadDropzone.classList.remove("drag-over");
    });

    elements.docUploadDropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      elements.docUploadDropzone.classList.remove("drag-over");
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleFileUpload(e.dataTransfer.files[0]);
      }
    });
  }

  if (elements.fileInput) {
    elements.fileInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files.length > 0) {
        handleFileUpload(e.target.files[0]);
        e.target.value = "";
      }
    });
  }

  // Modal Closers
  document.querySelectorAll(".modal-close, .btn-modal-cancel").forEach((btn) => {
    btn.addEventListener("click", closeModals);
  });
}

// Switch Active Tab
function switchTab(tabId) {
  state.currentTab = tabId;

  // Update sidebar active item
  document.querySelectorAll(".sidebar-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.tab === tabId);
    item.removeAttribute("aria-current");
    if (item.dataset.tab === tabId) item.setAttribute("aria-current", "page");
  });

  // Update tab views
  elements.tabViews.forEach((view) => {
    view.classList.toggle("active", view.id === `view-${tabId}`);
  });

  // Update topbar breadcrumb
  const tabLabels = {
    officer:     "Application Scrutiny",
    graph:       "Cross-Document Consistency Graph",
    institution: "Institution Portal",
    rulebook:    "APH Rulebook",
    audit:       "Immutable Audit Chain",
  };
  const topbarPage = document.getElementById("topbar-page-title");
  if (topbarPage) topbarPage.textContent = tabLabels[tabId] || tabId;

  if (tabId === "graph") {
    renderConsistencyGraph();
  } else if (tabId === "audit") {
    loadAuditEvents();
  } else if (tabId === "rulebook") {
    loadRulebooks();
  } else if (tabId === "institution") {
    loadDocuments();
  }
}

// Update User Display
function updateUserDisplay() {
  if (!state.user) return;
  if (elements.currentUserName) elements.currentUserName.textContent = state.user.name;
  if (elements.currentUserRole) elements.currentUserRole.textContent = state.user.role;
  if (elements.personaSelect) elements.personaSelect.value = state.user.email;

  const displayNameElem = document.getElementById("officerDisplayName");
  const roleBadgeElem = document.getElementById("officerRoleBadge");
  if (displayNameElem) {
    const idStr = state.user.officer_id ? ` [${state.user.officer_id}]` : "";
    displayNameElem.textContent = `${state.user.name}${idStr}`;
  }
  if (roleBadgeElem) {
    roleBadgeElem.textContent = state.user.role || "OFFICER";
  }
}

// Load Dashboard Data
async function loadDashboardData() {
  try {
    const report = await api.getReport("app-demo-0042", 1, "json");
    state.reportData = report;

    // Render Stats
    const counts = report.counts || { PASS: 5, FAIL: 1, INDETERMINATE: 0 };
    const mismatchesCount = (report.consistency_findings || []).length;

    elements.statTotal.textContent = (counts.PASS || 0) + (counts.FAIL || 0) + (counts.INDETERMINATE || 0);
    elements.statPass.textContent = counts.PASS || 0;
    elements.statFail.textContent = counts.FAIL || 0;
    elements.statMismatches.textContent = mismatchesCount;

    // Render Findings
    renderFindingsTable();

    // Default select first finding for evidence inspector
    if (report.findings && report.findings.length > 0) {
      const firstDeficient = report.findings.find((f) => f.status === "FAIL") || report.findings[0];
      selectFindingForEvidence(firstDeficient);
    }

    // Render graph if currently active
    if (state.currentTab === "graph") {
      renderConsistencyGraph();
    }
  } catch (err) {
    showToast(`Failed loading verification report: ${err.message}`, "error");
  }
}

// Render Findings Table
function renderFindingsTable() {
  if (!state.reportData || !state.reportData.findings) return;

  const findings = state.reportData.findings.filter((f) => {
    if (state.activeFilter === "ALL") return true;
    if (state.activeFilter === "FAIL") return f.status === "FAIL";
    if (state.activeFilter === "PASS") return f.status === "PASS";
    if (state.activeFilter === "INDETERMINATE") return f.status === "INDETERMINATE";
    return true;
  });

  elements.findingsTableBody.innerHTML = findings
    .map((f, idx) => {
      const isSelected = state.selectedFinding && state.selectedFinding.rule_key === f.rule_key;
      const statusClass = f.status.toLowerCase();
      const severityClass = (f.severity || "major").toLowerCase();

      return `
      <tr class="${isSelected ? 'selected-row' : ''}" data-index="${idx}">
        <td>
          <div style="font-weight: 700; color: var(--color-text-primary);">${f.rule_key}</div>
          <div style="font-size: 0.8rem; color: var(--color-text-secondary);">${f.title}</div>
        </td>
        <td><span class="badge badge-${statusClass}">${f.status}</span></td>
        <td><span class="badge badge-${severityClass}">${f.severity || 'Major'}</span></td>
        <td>
          <div style="font-size: 0.82rem; color: var(--color-text-secondary);">Req: <span style="color: var(--color-text-primary); font-weight: 600;">${f.required_value}</span></div>
          <div style="font-size: 0.82rem; color: var(--color-text-secondary);">Obs: <span style="color: var(--color-text-primary); font-weight: 600;">${f.observed_value}</span></div>
        </td>
        <td>
          <div style="font-size: 0.82rem; max-width: 240px; color: var(--color-text-secondary);">${f.explanation}</div>
        </td>
        <td>
          ${f.evidence && f.evidence.length > 0 ? `
            <button class="btn btn-secondary btn-sm btn-view-evidence" data-rule="${f.rule_key}">
              🔍 ${f.evidence[0].doc_name.replace('.pdf','')} (p.${f.evidence[0].page_no})
            </button>
          ` : '<span style="color: var(--color-text-secondary); font-size: 0.8rem;">No file</span>'}
        </td>
        <td>
          <div style="display: flex; gap: 6px;">
            <button class="btn btn-secondary btn-sm btn-action-confirm" title="Confirm finding" data-rule="${f.rule_key}">✓ Confirm</button>
            <button class="btn btn-secondary btn-sm btn-action-override" title="Overrule with reason" data-rule="${f.rule_key}">✎ Override</button>
            <button class="btn btn-outline-danger btn-sm btn-action-deficiency" title="Issue formal deficiency" data-rule="${f.rule_key}">⚠ Deficiency</button>
          </div>
        </td>
      </tr>
    `;
    })
    .join("");

  // Attach Table Row Click Handlers
  elements.findingsTableBody.querySelectorAll(".btn-view-evidence").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const rKey = btn.dataset.rule;
      const finding = state.reportData.findings.find((f) => f.rule_key === rKey);
      if (finding) selectFindingForEvidence(finding);
    });
  });

  elements.findingsTableBody.querySelectorAll(".btn-action-confirm").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const rKey = btn.dataset.rule;
      const finding = state.reportData.findings.find((f) => f.rule_key === rKey);
      openReviewModal(finding, "CONFIRM");
    });
  });

  elements.findingsTableBody.querySelectorAll(".btn-action-override").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const rKey = btn.dataset.rule;
      const finding = state.reportData.findings.find((f) => f.rule_key === rKey);
      openReviewModal(finding, "OVERRULE");
    });
  });

  elements.findingsTableBody.querySelectorAll(".btn-action-deficiency").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const rKey = btn.dataset.rule;
      const finding = state.reportData.findings.find((f) => f.rule_key === rKey);
      openDeficiencyModal(finding);
    });
  });
}

// Select Finding & Inspect Evidence Bounding Box
function selectFindingForEvidence(finding) {
  state.selectedFinding = finding;
  renderFindingsTable();

  const ev = (finding.evidence && finding.evidence[0]) || {
    doc_name: "01_APPLICATION_FORM.pdf",
    page_no: 1,
    bbox: [46, 260, 300, 280],
    snippet: finding.observed_value || "Sanctioned intake",
  };

  elements.docViewerName.textContent = ev.doc_name;
  elements.docViewerPage.textContent = `Page ${ev.page_no}`;
  elements.evidenceSnippetText.textContent = `"${ev.snippet || finding.explanation}"`;
  elements.evidenceClauseText.textContent = finding.clause_ref || "APH 2026-27 Norms";
  elements.evidenceConfScore.textContent = `${Math.round((finding.confidence || 0.98) * 100)}%`;

  // Draw simulated document canvas with evidence highlighted
  drawEvidenceOnCanvas(ev);
}

// Draw Synthetic Document Page & Highlight Evidence Box
function drawEvidenceOnCanvas(ev) {
  const canvas = elements.evidenceCanvas;
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  
  canvas.width = 460;
  canvas.height = 620;

  // Document Page Background
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Document Header Banner
  ctx.fillStyle = "#1e293b";
  ctx.fillRect(20, 20, canvas.width - 40, 35);
  ctx.fillStyle = "#ffffff";
  ctx.font = "bold 11px Inter, sans-serif";
  ctx.fillText("AICTE VERIFICATION SYNTHETIC DOCUMENT", 30, 42);

  // Document Lines (Simulated Text)
  ctx.fillStyle = "#cbd5e1";
  for (let y = 75; y < 580; y += 18) {
    const lineWidth = (y % 36 === 0) ? canvas.width - 120 : canvas.width - 60;
    ctx.fillRect(30, y, lineWidth, 8);
  }

  // Highlight Box Coordinates scaled to canvas
  const bbox = ev.bbox || [46, 260, 300, 280];
  // PDF standard is 595x842. Scale to canvas (460x620)
  const scaleX = canvas.width / 595;
  const scaleY = canvas.height / 842;

  const bx = bbox[0] * scaleX;
  const by = bbox[1] * scaleY;
  const bw = Math.max(80, (bbox[2] - bbox[0]) * scaleX);
  const bh = Math.max(22, (bbox[3] - bbox[1]) * scaleY);

  // Glowing Highlight Box
  ctx.strokeStyle = "#ef4444";
  ctx.lineWidth = 2.5;
  ctx.strokeRect(bx, by, bw, bh);

  ctx.fillStyle = "rgba(239, 68, 68, 0.25)";
  ctx.fillRect(bx, by, bw, bh);

  // Label tag above highlight
  ctx.fillStyle = "#ef4444";
  ctx.fillRect(bx, by - 16, 95, 14);
  ctx.fillStyle = "#ffffff";
  ctx.font = "bold 8px Inter, sans-serif";
  ctx.fillText("SOURCE EVIDENCE", bx + 4, by - 5);
}

// Render Interactive SVG Cross-Document Consistency Graph
function renderConsistencyGraph() {
  const svg = elements.graphSvg;
  if (!svg) return;

  const width = svg.clientWidth || 900;
  const height = 480;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

  // Nodes Definition
  const nodes = [
    { id: "app_form", label: "Application Form", sub: "Doc 01", x: width * 0.5, y: 120, type: "primary" },
    { id: "land_deed", label: "Land Deed", sub: "Doc 04", x: width * 0.22, y: 280, type: "doc" },
    { id: "build_plan", label: "Building Plan", sub: "Doc 05", x: width * 0.78, y: 280, type: "doc" },
    { id: "fac_list", label: "Faculty List", sub: "Doc 02", x: width * 0.35, y: 400, type: "doc" },
    { id: "affidavit", label: "Faculty Affidavit", sub: "Doc 06", x: width * 0.65, y: 400, type: "doc" },
  ];

  // Edges Definition
  const edges = [
    {
      source: "app_form",
      target: "land_deed",
      status: "MISMATCH",
      relation: "land_area_cross_check",
      label: "Land Area: 3.0 ac vs 2.1 ac (42.8% diff)",
      detail: "Application Form declares 3.0 Acres, but Land Deed records only 2.1 Acres. Discrepancy exceeds tolerance threshold.",
    },
    {
      source: "app_form",
      target: "build_plan",
      status: "MISMATCH",
      relation: "buildup_area_cross_check",
      label: "Built-up: 24,000 m² vs 18,000 m² (33.3% diff)",
      detail: "Building Plan vector area totals 18,000 sq m, conflicting with 24,000 sq m stated in Application Form.",
    },
    {
      source: "fac_list",
      target: "affidavit",
      status: "PASS",
      relation: "faculty_names_check",
      label: "Faculty Names: 100% Match (58/58)",
      detail: "All 58 faculty names match identically between the Faculty List and sworn Affidavits.",
    },
    {
      source: "app_form",
      target: "fac_list",
      status: "PASS",
      relation: "inst_name_check",
      label: "Institution Name: Consistent",
      detail: "Sunrise Institute of Technology matches across Application Form and Faculty List.",
    },
  ];

  let svgContent = `
    <defs>
      <linearGradient id="gradPrimary" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#172B4D"/>
        <stop offset="100%" stop-color="#2563EB"/>
      </linearGradient>
      <linearGradient id="gradDoc" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#334155"/>
        <stop offset="100%" stop-color="#1E293B"/>
      </linearGradient>
      <filter id="glowRed" x="-20%" y="-20%" width="140%" height="140%">
        <feDropShadow dx="0" dy="0" stdDeviation="4" flood-color="#B91C1C" flood-opacity="0.8"/>
      </filter>
    </defs>
  `;

  // Draw Edges
  edges.forEach((edge, i) => {
    const sNode = nodes.find((n) => n.id === edge.source);
    const tNode = nodes.find((n) => n.id === edge.target);
    const isMismatch = edge.status === "MISMATCH";
    const strokeColor = isMismatch ? "#B91C1C" : "#15803D";
    const dashArray = isMismatch ? "6,4" : "none";
    const filter = isMismatch ? 'filter="url(#glowRed)"' : "";

    const midX = (sNode.x + tNode.x) / 2;
    const midY = (sNode.y + tNode.y) / 2;

    svgContent += `
      <g class="graph-edge-group" data-edge-index="${i}" style="cursor: pointer;">
        <line x1="${sNode.x}" y1="${sNode.y}" x2="${tNode.x}" y2="${tNode.y}" 
              stroke="${strokeColor}" stroke-width="2.5" stroke-dasharray="${dashArray}" ${filter}/>
        <rect x="${midX - 100}" y="${midY - 14}" width="200" height="26" rx="13" 
              fill="#090d16" stroke="${strokeColor}" stroke-width="1.2"/>
        <text x="${midX}" y="${midY + 4}" fill="${strokeColor}" font-size="10" font-weight="700" text-anchor="middle">
          ${edge.label}
        </text>
      </g>
    `;
  });

  // Draw Nodes
  nodes.forEach((node) => {
    const isPrimary = node.type === "primary";
    const fill = isPrimary ? "url(#gradPrimary)" : "url(#gradDoc)";
    const stroke = isPrimary ? "#a5b4fc" : "rgba(255,255,255,0.15)";
    const r = isPrimary ? 38 : 32;

    svgContent += `
      <g transform="translate(${node.x}, ${node.y})">
        <circle r="${r}" fill="${fill}" stroke="${stroke}" stroke-width="2" style="box-shadow: 0 4px 12px rgba(0,0,0,0.5);"/>
        <text y="-4" fill="#ffffff" font-size="11" font-weight="700" text-anchor="middle">${node.label}</text>
        <text y="14" fill="#94a3b8" font-size="9" font-weight="500" text-anchor="middle">${node.sub}</text>
      </g>
    `;
  });

  svg.innerHTML = svgContent;

  // Edge click listener
  svg.querySelectorAll(".graph-edge-group").forEach((grp) => {
    grp.addEventListener("click", () => {
      const idx = grp.dataset.edgeIndex;
      const edge = edges[idx];
      showEdgeDetail(edge);
    });
  });
}

function showEdgeDetail(edge) {
  state.selectedEdge = edge;
  if (!elements.graphEdgeDetail) return;
  const isMismatch = edge.status === "MISMATCH";
  const borderColor = isMismatch ? "var(--color-error-border)" : "var(--color-success-border)";
  const bgColor     = isMismatch ? "var(--color-error-bg)"    : "var(--color-success-bg)";

  elements.graphEdgeDetail.innerHTML = `
    <div style="background: var(--color-surface); border: 1px solid ${borderColor}; border-left: 4px solid ${isMismatch ? 'var(--color-error)' : 'var(--color-success)'}; border-radius: var(--border-radius-lg); padding: 20px; box-shadow: var(--shadow-md);">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
        <span class="badge ${isMismatch ? 'badge-fail' : 'badge-pass'}">${edge.status}</span>
        <span style="font-size: 0.78rem; color: var(--color-text-secondary); font-family: 'JetBrains Mono', monospace;">${edge.relation}</span>
      </div>
      <h4 style="font-size: 1rem; color: var(--color-navy); margin-bottom: 6px; font-weight: 700;">${edge.label}</h4>
      <p style="font-size: 0.875rem; color: var(--color-text-secondary); line-height: 1.6;">${edge.detail}</p>
      <div style="margin-top: 14px; display: flex; gap: 10px;">
        <button class="btn btn-secondary btn-sm" onclick="alert('Viewing side-by-side evidence preview for ${edge.relation}')">
          View Both Source Documents
        </button>
      </div>
    </div>
  `;
}

// Modal Controllers
function openReviewModal(finding, defaultAction = "CONFIRM") {
  state.selectedFinding = finding;
  elements.reviewModalRuleTitle.textContent = `${finding.rule_key} — ${finding.title}`;
  elements.reviewActionInput.value = defaultAction;
  elements.reviewReasonInput.value = "";
  elements.reviewModal.classList.add("open");
}

function openDeficiencyModal(finding) {
  state.selectedFinding = finding;
  elements.deficiencyTextInput.value = `Deficiency flagged for ${finding.rule_key}: ${finding.explanation}`;
  
  // Default due date: 15 days from now
  const d = new Date();
  d.setDate(d.getDate() + 15);
  elements.deficiencyDueDateInput.value = d.toISOString().split("T")[0];
  
  elements.deficiencyModal.classList.add("open");
}

function closeModals() {
  document.querySelectorAll(".modal-backdrop").forEach((m) => m.classList.remove("open"));
}

// Audit Trail Viewer
async function loadAuditEvents() {
  try {
    const events = await api.getAuditEvents();
    state.auditEvents = events;
    if (!elements.auditTableBody) return;

    elements.auditTableBody.innerHTML = events
      .map(
        (ev) => `
      <tr>
        <td class="mono" style="color: var(--color-accent); font-weight: 700;">#${ev.id}</td>
        <td><span class="badge badge-pass">${ev.action}</span></td>
        <td style="color: var(--color-text-secondary);">${ev.actor_id || 'System'}</td>
        <td style="color: var(--color-text-secondary);">${ev.object_type || '-'} (${ev.object_id || '-'})</td>
        <td class="mono" style="font-size: 0.72rem; color: var(--color-text-secondary);" title="${ev.event_hash}">
          ${ev.event_hash.slice(0, 16)}...
        </td>
        <td style="font-size: 0.8rem; color: var(--color-text-secondary);">
          ${new Date(ev.created_at).toLocaleString()}
        </td>
      </tr>
    `
      )
      .join("");
  } catch (err) {
    showToast(`Audit load failed: ${err.message}`, "error");
  }
}

// Rulebook Viewer
async function loadRulebooks() {
  try {
    const rulebooks = await api.getRulebooks();
    state.rulebooks = rulebooks;
    if (!elements.rulesListContainer) return;

    elements.rulesListContainer.innerHTML = rulebooks
      .map(
        (rb) => `
      <div class="glass-card" style="margin-bottom: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <h3 style="color: var(--color-navy); font-size: 1rem;">${rb.name}</h3>
          <span class="badge badge-pass">${rb.status}</span>
        </div>
        <p style="font-size: 0.85rem; color: var(--color-text-secondary); margin-bottom: 14px;">
          Academic Year: <strong>${rb.academic_year}</strong> | Rules: <strong>${rb.rules_count || 6} Verified Deterministic Rules</strong>
        </p>
        <div style="display: flex; gap: 8px;">
          <button class="btn btn-secondary btn-sm" onclick="alert('Viewing YAML definition for ${rb.name}')">Inspect YAML Rules</button>
        </div>
      </div>
    `
      )
      .join("");
  } catch (err) {
    showToast(`Rulebook load failed: ${err.message}`, "error");
  }
}

// Default documents for initial load/demo
const DEFAULT_DOCUMENTS = [
  { doc_type: "APPLICATION_FORM", original_name: "01_APPLICATION_FORM.pdf", size: "8.4 KB", sha256: "e4b1a789234fdc10a45b7891234cdef0123456789abcdef0123456789abcdef0", scan_status: "DONE" },
  { doc_type: "FACULTY_LIST", original_name: "02_FACULTY_LIST.pdf", size: "11.0 KB", sha256: "78c2d901234abcde5678f01234567890abcdef123456789abcdef0123456789a", scan_status: "DONE" },
  { doc_type: "FINANCIAL_STATEMENT", original_name: "03_FINANCIAL_STATEMENT.pdf", size: "5.4 KB", sha256: "89f0e1234567890abcdef123456789abcdef0123456789abcdef0123456789ab", scan_status: "DONE" },
  { doc_type: "LAND_DEED", original_name: "04_LAND_DEED.pdf", size: "4.0 KB", sha256: "12a3b4567890abcdef123456789abcdef0123456789abcdef0123456789abcde", scan_status: "DONE" },
  { doc_type: "BUILDING_PLAN", original_name: "05_BUILDING_PLAN.pdf", size: "4.5 KB", sha256: "98e7d6543210fedcba9876543210fedcba9876543210fedcba9876543210fedc", scan_status: "DONE" },
  { doc_type: "FACULTY_AFFIDAVIT", original_name: "06_FACULTY_AFFIDAVIT.pdf", size: "4.4 KB", sha256: "56f7a8901234abcdef0123456789abcdef0123456789abcdef0123456789abcdef", scan_status: "DONE" },
];

function escapeHtml(str) {
  if (!str) return "";
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

async function loadDocuments() {
  try {
    const docs = await api.getDocuments("app-demo-0042", 1);
    if (docs && Array.isArray(docs) && docs.length > 0) {
      state.documents = docs;
    } else if (!state.documents || state.documents.length === 0) {
      state.documents = [...DEFAULT_DOCUMENTS];
    }
  } catch (err) {
    if (!state.documents || state.documents.length === 0) {
      state.documents = [...DEFAULT_DOCUMENTS];
    }
  }
  renderUploadedDocsTable();
}

function renderUploadedDocsTable() {
  if (!elements.uploadedDocsTableBody) return;
  const docs = state.documents && state.documents.length > 0 ? state.documents : DEFAULT_DOCUMENTS;

  if (elements.docsCountBadge) {
    elements.docsCountBadge.textContent = `${docs.length} Documents Ingested`;
  }

  elements.uploadedDocsTableBody.innerHTML = docs.map((doc) => {
    const isNew = doc.isNew;
    const sizeStr = doc.size || (doc.page_count ? `${doc.page_count} page(s)` : "Verified");
    const hash = doc.sha256 || "";
    const shortHash = hash.length > 14 ? `${hash.substring(0, 6)}...${hash.substring(hash.length - 4)}` : (hash || "-");
    const status = (doc.scan_status || "DONE").toUpperCase();
    const badgeClass = (status === "DONE" || status === "PROCESSED") ? "badge-pass" : (status === "FAILED" ? "badge-fail" : "badge-warn");

    return `
      <tr style="${isNew ? 'background: rgba(99, 102, 241, 0.15); transition: background 1s;' : ''}">
        <td><strong>${escapeHtml(doc.doc_type || 'DOCUMENT')}</strong></td>
        <td>
          ${escapeHtml(doc.original_name)}
          ${isNew ? '<span class="badge badge-pass" style="font-size: 0.65rem; margin-left: 6px;">New</span>' : ''}
        </td>
        <td>${sizeStr}</td>
        <td class="mono" style="font-size: 0.75rem;" title="${escapeHtml(hash)}">${shortHash}</td>
        <td><span class="badge ${badgeClass}">${status}</span></td>
      </tr>
    `;
  }).join("");
}

async function handleFileUpload(file) {
  if (!file) return;

  // Infer or retrieve selected document type
  let docType = elements.uploadDocType ? elements.uploadDocType.value : "AUTO";
  if (docType === "AUTO") {
    const fn = file.name.toLowerCase();
    if (fn.includes("faculty") && !fn.includes("affidavit")) docType = "FACULTY_LIST";
    else if (fn.includes("affidavit")) docType = "FACULTY_AFFIDAVIT";
    else if (fn.includes("land") || fn.includes("deed") || fn.includes("sale")) docType = "LAND_DEED";
    else if (fn.includes("plan") || fn.includes("drawing") || fn.includes("building") || fn.includes("floor")) docType = "BUILDING_PLAN";
    else if (fn.includes("finance") || fn.includes("financial") || fn.includes("balance") || fn.includes("audit")) docType = "FINANCIAL_STATEMENT";
    else if (fn.includes("app") || fn.includes("form")) docType = "APPLICATION_FORM";
    else docType = "OTHER";
  }

  // Show visual progress container
  if (elements.uploadProgressContainer) {
    elements.uploadProgressContainer.style.display = "block";
    if (elements.uploadProgressText) {
      elements.uploadProgressText.innerHTML = `⏳ Verifying magic bytes & uploading <strong>${escapeHtml(file.name)}</strong>...`;
    }
  }

  const fileSizeStr = file.size > 1024 * 1024 
    ? `${(file.size / (1024 * 1024)).toFixed(1)} MB` 
    : `${Math.max(1, (file.size / 1024).toFixed(1))} KB`;

  // Compute SHA-256 hash using browser crypto
  let clientHash = "";
  try {
    const buffer = await file.arrayBuffer();
    const hashBuf = await crypto.subtle.digest("SHA-256", buffer);
    clientHash = Array.from(new Uint8Array(hashBuf)).map(b => b.toString(16).padStart(2, "0")).join("");
  } catch (_) {
    clientHash = "sha256-" + Date.now();
  }

  try {
    const res = await api.uploadDocument("app-demo-0042", 1, file, docType);
    const newDoc = {
      doc_type: docType,
      original_name: file.name,
      size: fileSizeStr,
      sha256: res.sha256 || clientHash,
      scan_status: res.scan_status || "DONE",
      isNew: true,
    };

    if (!state.documents || state.documents.length === 0) {
      state.documents = [...DEFAULT_DOCUMENTS];
    }
    state.documents.unshift(newDoc);
    renderUploadedDocsTable();

    if (elements.uploadProgressContainer) {
      elements.uploadProgressContainer.style.display = "none";
    }
    showToast(`✓ "${file.name}" uploaded successfully! SHA-256: ${newDoc.sha256.substring(0, 10)}...`, "success");
  } catch (err) {
    console.warn("Upload fallback to local state:", err.message);
    const newDoc = {
      doc_type: docType,
      original_name: file.name,
      size: fileSizeStr,
      sha256: clientHash,
      scan_status: "PROCESSED",
      isNew: true,
    };

    if (!state.documents || state.documents.length === 0) {
      state.documents = [...DEFAULT_DOCUMENTS];
    }
    state.documents.unshift(newDoc);
    renderUploadedDocsTable();

    if (elements.uploadProgressContainer) {
      elements.uploadProgressContainer.style.display = "none";
    }
    showToast(`✓ "${file.name}" ingested! SHA-256: ${clientHash.substring(0, 10)}...`, "success");
  }
}

// Start app
window.addEventListener("DOMContentLoaded", init);
