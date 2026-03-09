let loadedProjectId = null;
let loadedProjectDefaultName = "thermoanalyzer_project.thermozip";

function setText(id, text) {
  const node = document.getElementById(id);
  if (node) {
    node.textContent = text;
  }
}

function appendLog(message) {
  const node = document.getElementById("log");
  const now = new Date().toLocaleTimeString();
  node.textContent = `${node.textContent}\n[${now}] ${message}`.trim();
}

function setHtml(id, html) {
  const node = document.getElementById(id);
  if (node) {
    node.innerHTML = html;
  }
}

function setSaveEnabled(enabled) {
  const saveBtn = document.getElementById("saveProjectBtn");
  if (saveBtn) {
    saveBtn.disabled = !enabled;
  }
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

async function onOpenProject() {
  try {
    const picked = await window.taDesktop.pickProjectArchive();
    if (!picked || picked.canceled) {
      appendLog("Open project canceled.");
      return;
    }

    const loaded = await window.taDesktop.loadProjectArchive(picked.archiveBase64);
    loadedProjectId = loaded.project_id;
    loadedProjectDefaultName = `thermoanalyzer_project${loaded.project_extension}`;
    setSaveEnabled(true);
    setText("projectInfo", `Loaded project_id: ${loaded.project_id}`);
    setText("projectSummary", JSON.stringify(loaded.summary, null, 2));
    appendLog(`Loaded project from ${picked.filePath}.`);
  } catch (error) {
    appendLog(`Open project failed: ${error}`);
  }
}

async function onSaveProject() {
  if (!loadedProjectId) {
    appendLog("Save skipped: no project loaded.");
    return;
  }

  try {
    const archive = await window.taDesktop.saveProjectArchive(loadedProjectId);
    const persisted = await window.taDesktop.persistProjectArchive(
      loadedProjectDefaultName || archive.file_name,
      archive.archive_base64
    );
    if (!persisted || persisted.canceled) {
      appendLog("Save project canceled.");
      return;
    }
    appendLog(`Saved archive to ${persisted.filePath}.`);
  } catch (error) {
    appendLog(`Save project failed: ${error}`);
  }
}

document.getElementById("openProjectBtn").addEventListener("click", onOpenProject);
document.getElementById("saveProjectBtn").addEventListener("click", onSaveProject);

refreshStatus();

