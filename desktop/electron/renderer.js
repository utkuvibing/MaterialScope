let activeProjectId = null;
let activeProjectDefaultName = "thermoanalyzer_project.thermozip";
let selectedDatasetKey = null;

function setText(id, text) {
  const node = document.getElementById(id);
  if (node) node.textContent = text;
}

function setHtml(id, html) {
  const node = document.getElementById(id);
  if (node) node.innerHTML = html;
}

function appendLog(message) {
  const node = document.getElementById("log");
  const now = new Date().toLocaleTimeString();
  node.textContent = `${node.textContent}\n[${now}] ${message}`.trim();
}

function setWorkflowEnabled(enabled) {
  document.getElementById("saveProjectBtn").disabled = !enabled;
  document.getElementById("importDatasetBtn").disabled = !enabled;
  document.getElementById("runAnalysisBtn").disabled = !enabled || !selectedDatasetKey;
}

function escapeHtml(text) {
  return String(text || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderDatasets(datasets) {
  const body = document.getElementById("datasetsBody");
  if (!datasets.length) {
    body.innerHTML = "<tr><td colspan='7'>No datasets loaded.</td></tr>";
    selectedDatasetKey = null;
    document.getElementById("runAnalysisBtn").disabled = true;
    return;
  }

  if (!selectedDatasetKey || !datasets.some((item) => item.key === selectedDatasetKey)) {
    selectedDatasetKey = datasets[0].key;
  }

  body.innerHTML = datasets
    .map((item) => {
      const checked = item.key === selectedDatasetKey ? "checked" : "";
      return `
      <tr>
        <td><input type="radio" name="datasetPick" value="${escapeHtml(item.key)}" ${checked}></td>
        <td>${escapeHtml(item.key)}</td>
        <td>${escapeHtml(item.data_type)}</td>
        <td>${escapeHtml(item.sample_name)}</td>
        <td>${escapeHtml(item.validation_status)}</td>
        <td>${escapeHtml(item.warning_count)}</td>
        <td>${escapeHtml(item.issue_count)}</td>
      </tr>
    `;
    })
    .join("");

  body.querySelectorAll("input[name='datasetPick']").forEach((node) => {
    node.addEventListener("change", (event) => {
      selectedDatasetKey = event.target.value;
      document.getElementById("runAnalysisBtn").disabled = !activeProjectId || !selectedDatasetKey;
      appendLog(`Selected dataset: ${selectedDatasetKey}`);
    });
  });
}

function renderResults(results) {
  const body = document.getElementById("resultsBody");
  if (!results.length) {
    body.innerHTML = "<tr><td colspan='8'>No results saved.</td></tr>";
    return;
  }
  body.innerHTML = results
    .map(
      (item) => `
      <tr>
        <td>${escapeHtml(item.id)}</td>
        <td>${escapeHtml(item.analysis_type)}</td>
        <td>${escapeHtml(item.status)}</td>
        <td>${escapeHtml(item.dataset_key)}</td>
        <td>${escapeHtml(item.validation_status)}</td>
        <td>${escapeHtml(item.calibration_state)}</td>
        <td>${escapeHtml(item.reference_state)}</td>
        <td>${escapeHtml(item.saved_at_utc)}</td>
      </tr>
    `
    )
    .join("");
}

async function refreshStatus() {
  const bootstrap = window.taDesktop.getBackendBootstrap();
  setHtml(
    "bootstrap",
    `Backend URL: <code>${bootstrap.backendUrl || "N/A"}</code> | Token: <strong>${bootstrap.hasToken ? "present" : "missing"}</strong>`
  );

  try {
    const health = await window.taDesktop.checkHealth();
    setHtml("health", `Health: <span class="ok">${health.status}</span> (API ${health.api_version})`);
  } catch (error) {
    setHtml("health", `Health: <span class="fail">failed</span> (${error})`);
  }

  try {
    const version = await window.taDesktop.getVersion();
    setHtml(
      "version",
      `ThermoAnalyzer app version: <strong>${version.app_version}</strong> | Project extension: <code>${version.project_extension}</code>`
    );
  } catch (error) {
    setHtml("version", `Version call failed: <span class="fail">${error}</span>`);
  }
}

async function refreshWorkspaceViews() {
  if (!activeProjectId) {
    setText("projectInfo", "No workspace active.");
    setText("projectSummary", "");
    renderDatasets([]);
    renderResults([]);
    setWorkflowEnabled(false);
    return;
  }

  const summary = await window.taDesktop.getWorkspaceSummary(activeProjectId);
  const datasets = await window.taDesktop.listDatasets(activeProjectId);
  const results = await window.taDesktop.listResults(activeProjectId);
  setText("projectInfo", `Workspace: ${activeProjectId}`);
  setText("projectSummary", JSON.stringify(summary.summary, null, 2));
  renderDatasets(datasets.datasets || []);
  renderResults(results.results || []);
  setWorkflowEnabled(true);
}

async function onNewWorkspace() {
  try {
    const created = await window.taDesktop.createWorkspace();
    activeProjectId = created.project_id;
    selectedDatasetKey = null;
    activeProjectDefaultName = "thermoanalyzer_project.thermozip";
    await refreshWorkspaceViews();
    appendLog(`Created workspace ${activeProjectId}.`);
  } catch (error) {
    appendLog(`Create workspace failed: ${error}`);
  }
}

async function onOpenProject() {
  try {
    const picked = await window.taDesktop.pickProjectArchive();
    if (!picked || picked.canceled) {
      appendLog("Open project canceled.");
      return;
    }
    const loaded = await window.taDesktop.loadProjectArchive(picked.archiveBase64);
    activeProjectId = loaded.project_id;
    selectedDatasetKey = null;
    activeProjectDefaultName = `thermoanalyzer_project${loaded.project_extension}`;
    await refreshWorkspaceViews();
    appendLog(`Loaded project from ${picked.filePath}.`);
  } catch (error) {
    appendLog(`Open project failed: ${error}`);
  }
}

async function onSaveProject() {
  if (!activeProjectId) {
    appendLog("Save skipped: no workspace active.");
    return;
  }
  try {
    const archive = await window.taDesktop.saveProjectArchive(activeProjectId);
    const persisted = await window.taDesktop.persistProjectArchive(
      activeProjectDefaultName || archive.file_name,
      archive.archive_base64
    );
    if (!persisted || persisted.canceled) {
      appendLog("Save workspace canceled.");
      return;
    }
    appendLog(`Saved workspace archive to ${persisted.filePath}.`);
  } catch (error) {
    appendLog(`Save workspace failed: ${error}`);
  }
}

async function onImportDataset() {
  if (!activeProjectId) {
    appendLog("Import skipped: no workspace active.");
    return;
  }
  try {
    const picked = await window.taDesktop.pickDatasetFile();
    if (!picked || picked.canceled) {
      appendLog("Import dataset canceled.");
      return;
    }
    const dataType = document.getElementById("datasetTypeSelect").value;
    const imported = await window.taDesktop.importDataset(
      activeProjectId,
      picked.fileName,
      picked.fileBase64,
      dataType
    );
    selectedDatasetKey = imported.dataset.key;
    await refreshWorkspaceViews();
    appendLog(
      `Imported dataset ${imported.dataset.key} (${imported.dataset.data_type}) from ${picked.filePath}. Validation=${imported.validation.status}`
    );
  } catch (error) {
    appendLog(`Import dataset failed: ${error}`);
  }
}

async function onRunAnalysis() {
  if (!activeProjectId || !selectedDatasetKey) {
    appendLog("Run analysis skipped: select a dataset first.");
    return;
  }
  try {
    const analysisType = document.getElementById("analysisTypeSelect").value;
    const run = await window.taDesktop.runAnalysis(activeProjectId, selectedDatasetKey, analysisType);
    setText(
      "analysisInfo",
      `Analysis ${analysisType} on ${selectedDatasetKey}: ${run.execution_status}${run.result_id ? ` (${run.result_id})` : ""}`
    );
    setText("analysisSummary", JSON.stringify(run, null, 2));
    await refreshWorkspaceViews();
    appendLog(
      `Analysis ${analysisType} on ${selectedDatasetKey}: ${run.execution_status}${run.failure_reason ? ` - ${run.failure_reason}` : ""}`
    );
  } catch (error) {
    appendLog(`Run analysis failed: ${error}`);
  }
}

document.getElementById("newWorkspaceBtn").addEventListener("click", onNewWorkspace);
document.getElementById("openProjectBtn").addEventListener("click", onOpenProject);
document.getElementById("saveProjectBtn").addEventListener("click", onSaveProject);
document.getElementById("importDatasetBtn").addEventListener("click", onImportDataset);
document.getElementById("runAnalysisBtn").addEventListener("click", onRunAnalysis);

setWorkflowEnabled(false);
refreshStatus();
