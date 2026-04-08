let activeProjectId = null;
let activeProjectDefaultName = "thermoanalyzer_project.thermozip";
let selectedDatasetKey = null;
let selectedResultId = null;
let currentDatasets = [];
let currentResults = [];
let exportableResults = [];
let currentActiveDatasetKey = null;
let compareSelectedDatasetKeys = new Set();
let currentDatasetDetail = null;
let currentResultDetail = null;
let activeView = "home";
let currentLanguage = "tr";
let libraryCloudToken = null;
let lastLibrarySearchPayload = null;
const lastAnalysisRuns = {
  DSC: null,
  DTA: null,
  TGA: null,
  FTIR: null,
  RAMAN: null,
  XRD: null,
};

const I18N = {
  tr: {
    nav: {
      home: "Veri Al",
      dsc: "DSC Analizi",
      dta: "DTA Analizi",
      tga: "TGA Analizi",
      ftir: "FTIR Analizi",
      raman: "Raman Analizi",
      xrd: "XRD Analizi",
      compare: "Karşılaştırma",
      library: "Kütüphane",
      export: "Rapor Merkezi",
      project: "Proje Alanı",
      license: "Lisans ve Marka",
      diagnostics: "Tanılama",
    },
    status: {
      healthUnknown: "Sağlık: bilinmiyor",
      health: "Sağlık: {status}",
      healthFailed: "Sağlık: başarısız",
      versionUnknown: "Sürüm: bilinmiyor",
      version: "Sürüm: {version}",
      versionFailed: "Sürüm: başarısız",
      workspace: "Çalışma Alanı: {workspace}",
    },
    common: {
      na: "N/A",
      none: "yok",
      noPreviewRows: "Önizleme satırı yok.",
      noCompareSelected: "Karşılaştırma için seçili veri seti yok.",
      unknown: "bilinmiyor",
      selected: "Seçili",
      batch: "Batch",
      available: "mevcut",
      notRun: "çalıştırılmadı",
      yes: "evet",
      no: "hayır",
    },
    home: {
      stepWorkspaceReady: "Çalışma alanı hazır",
      stepWorkspacePending: "Çalışma alanı oluştur/aç",
      stepImportDone: "{count} veri seti içe aktarıldı",
      stepImportPending: "En az bir veri seti içe aktar",
      stepCompareDone: "{count} karşılaştırma seçimi",
      stepComparePending: "Karşılaştırma seçimlerini belirle",
      stepRunDone: "{count} sonuç kaydedildi",
      stepRunPending: "DSC/DTA/TGA analizi çalıştır",
      nextCreate: "Yeni proje oluştur veya mevcut projeyi aç.",
      nextImport: "İlk veri setini içe aktar.",
      nextInspect: "Doğrulama ve karşılaştırma seçimlerini incele.",
      nextRun: "DSC/DTA/TGA veya Compare batch adımına geç.",
      nextSave: "Projeyi kaydet veya dışa aktarıma geç.",
    },
    compare: {
      analysisType: "Analiz Tipi",
      selectedCount: "Seçili Koşu",
      savedAt: "Kaydedildi",
      batchRunId: "Batch Çalıştırma ID",
      batchTemplate: "Batch Şablonu",
      notes: "Notlar",
      notesEmpty: "(boş)",
      summaryPending: "Karşılaştırma alanı özeti burada görünecek.",
    },
  },
  en: {
    nav: {
      home: "Import Runs",
      dsc: "DSC Analysis",
      dta: "DTA Analysis",
      tga: "TGA Analysis",
      ftir: "FTIR Analysis",
      raman: "Raman Analysis",
      xrd: "XRD Analysis",
      compare: "Compare Workspace",
      library: "Library",
      export: "Report Center",
      project: "Project Workspace",
      license: "License & Branding",
      diagnostics: "Diagnostics",
    },
    status: {
      healthUnknown: "Health: unknown",
      health: "Health: {status}",
      healthFailed: "Health: failed",
      versionUnknown: "Version: unknown",
      version: "Version: {version}",
      versionFailed: "Version: failed",
      workspace: "Workspace: {workspace}",
    },
    common: {
      na: "N/A",
      none: "none",
      noPreviewRows: "No preview rows.",
      noCompareSelected: "No compare-selected datasets.",
      unknown: "unknown",
      selected: "Selected",
      batch: "Batch",
      available: "available",
      notRun: "not run",
      yes: "yes",
      no: "no",
    },
    home: {
      stepWorkspaceReady: "Workspace ready",
      stepWorkspacePending: "Create/open workspace",
      stepImportDone: "{count} dataset(s) imported",
      stepImportPending: "Import at least one dataset",
      stepCompareDone: "{count} selected for compare",
      stepComparePending: "Select compare datasets",
      stepRunDone: "{count} result(s) saved",
      stepRunPending: "Run DSC/DTA/TGA analysis",
      nextCreate: "Create or open a workspace.",
      nextImport: "Import your first dataset.",
      nextInspect: "Inspect validation and compare selection.",
      nextRun: "Run DSC/DTA/TGA analysis or batch from Compare.",
      nextSave: "Save project or continue with export.",
    },
    compare: {
      analysisType: "Analysis Type",
      selectedCount: "Selected Runs",
      savedAt: "Saved At",
      batchRunId: "Batch Run ID",
      batchTemplate: "Batch Template",
      notes: "Notes",
      notesEmpty: "(empty)",
      summaryPending: "Compare workspace summary will appear here.",
    },
  },
};

const viewTitleKeys = {
  home: "nav.home",
  dsc: "nav.dsc",
  dta: "nav.dta",
  tga: "nav.tga",
  ftir: "nav.ftir",
  raman: "nav.raman",
  xrd: "nav.xrd",
  compare: "nav.compare",
  library: "nav.library",
  export: "nav.export",
  project: "nav.project",
  license: "nav.license",
  diagnostics: "nav.diagnostics",
};
function lookupI18n(key) {
  const locale = I18N[currentLanguage] || I18N.tr;
  const fallback = I18N.en;
  const parts = String(key || "").split(".");
  let node = locale;
  for (const part of parts) {
    node = node && node[part];
  }
  if (typeof node === "string") return node;
  let fallbackNode = fallback;
  for (const part of parts) {
    fallbackNode = fallbackNode && fallbackNode[part];
  }
  return typeof fallbackNode === "string" ? fallbackNode : key;
}

function t(key, vars = {}) {
  let template = lookupI18n(key);
  for (const [name, value] of Object.entries(vars || {})) {
    template = template.replaceAll(`{${name}}`, String(value));
  }
  return template;
}

function el(id) {
  return document.getElementById(id);
}

function setText(id, text) {
  const node = el(id);
  if (node) node.textContent = text;
}

function setHtml(id, html) {
  const node = el(id);
  if (node) node.innerHTML = html;
}

function setDisabled(id, disabled) {
  const node = el(id);
  if (node && "disabled" in node) node.disabled = disabled;
}

function setSelectOptionText(selectId, optionValue, text) {
  const select = el(selectId);
  if (!select) return;
  const option = Array.from(select.options || []).find((item) => item.value === optionValue);
  if (option) option.textContent = text;
}

function setLanguage(lang) {
  currentLanguage = lang === "en" ? "en" : "tr";
  window.localStorage.setItem("taDesktopLanguage", currentLanguage);
  const trBtn = el("langTrBtn");
  const enBtn = el("langEnBtn");
  if (trBtn && enBtn) {
    trBtn.classList.toggle("active", currentLanguage === "tr");
    enBtn.classList.toggle("active", currentLanguage === "en");
  }
  applyStaticLanguage();
  switchView(activeView);
  refreshStatus().catch(() => undefined);
  refreshWorkspaceViews().catch(() => undefined);
}

function applyStaticLanguage() {
  document.documentElement.lang = currentLanguage === "tr" ? "tr" : "en";
  const trBtn = el("langTrBtn");
  const enBtn = el("langEnBtn");
  if (trBtn && enBtn) {
    trBtn.classList.toggle("active", currentLanguage === "tr");
    enBtn.classList.toggle("active", currentLanguage === "en");
  }

  setText("primaryGroupLabel", currentLanguage === "tr" ? "Ana Akış" : "Primary");
  setText("previewGroupLabel", currentLanguage === "tr" ? "Laboratuvar Önizlemesi" : "Lab Preview");
  setText("systemGroupLabel", currentLanguage === "tr" ? "Sistem" : "System");
  setText(
    "brandSubtitle",
    currentLanguage === "tr"
      ? "Cihazdan bağımsız DSC/DTA/TGA/FTIR/RAMAN/XRD çalışma alanı"
      : "Vendor-independent DSC/DTA/TGA/FTIR/RAMAN/XRD workbench"
  );
  setText(
    "previewToggleLabel",
    currentLanguage === "tr"
      ? "Laboratuvar Önizleme Modüllerini Göster"
      : "Show Lab Preview Modules"
  );
  setText(
    "sidebarAboutTitle",
    currentLanguage === "tr" ? "ThermoAnalyzer Hakkında" : "About ThermoAnalyzer"
  );
  setText(
    "sidebarAboutCopy",
    currentLanguage === "tr"
      ? "Kararlı kapsam: DSC/DTA/TGA/FTIR/RAMAN/XRD, Karşılaştırma Alanı, Kütüphane erişimi, Toplu Şablon Uygulayıcı, proje arşivi ve CSV/DOCX çıktıları."
      : "Stable scope: DSC/DTA/TGA/FTIR/RAMAN/XRD, Compare Workspace, library access, Batch Template Runner, project archive, and CSV/DOCX outputs."
  );

  setText("navHomeBtn", t("nav.home"));
  setText("navDscBtn", t("nav.dsc"));
  setText("navDtaBtn", t("nav.dta"));
  setText("navTgaBtn", t("nav.tga"));
  setText("navFtirBtn", t("nav.ftir"));
  setText("navRamanBtn", t("nav.raman"));
  setText("navXrdBtn", t("nav.xrd"));
  setText("navCompareBtn", t("nav.compare"));
  setText("navLibraryBtn", t("nav.library"));
  setText("navExportBtn", t("nav.export"));
  setText("navProjectBtn", t("nav.project"));
  setText("navLicenseBtn", t("nav.license"));
  setText("navDiagnosticsBtn", t("nav.diagnostics"));
  setText(
    "navPreviewKineticsBtn",
    currentLanguage === "tr" ? "Kinetik Analiz (Deneysel)" : "Kinetic Analysis (Experimental)"
  );
  setText(
    "navPreviewDeconvBtn",
    currentLanguage === "tr" ? "Pik Dekonvolüsyonu (Deneysel)" : "Peak Deconvolution (Experimental)"
  );

  setText("homeViewTitle", t("nav.home"));
  setText(
    "homeViewCopy",
    currentLanguage === "tr"
      ? "Termal ve spektral koşuları içe aktar, metadata’yı gözden geçir ve kararlı analiz akışına hazırla."
      : "Import thermal and spectral runs, review metadata, and prepare stable analysis workflow execution."
  );
  setText("homeHeroTitle", currentLanguage === "tr" ? "Çalışma Başlangıcı" : "Workspace Entry");
  setText(
    "homeHeroCopy",
    currentLanguage === "tr"
      ? "Projeyi aç, veriyi içe aktar ve analiz/karşılaştırma öncesi doğrulama sinyallerini kontrol et."
      : "Open your project, import data, and confirm validation signals before analysis/compare."
  );
  setText("newWorkspaceBtn", currentLanguage === "tr" ? "Yeni Proje" : "New Project");
  setText("openProjectBtn", currentLanguage === "tr" ? ".thermozip Aç" : "Open .thermozip");
  setText("saveProjectBtn", currentLanguage === "tr" ? "Projeyi Kaydet" : "Save Workspace");
  setText("refreshWorkspaceContextBtn", currentLanguage === "tr" ? "Bağlamı Yenile" : "Refresh Context");
  setText("homeWorkflowTitle", currentLanguage === "tr" ? "Program Rehberi ve İş Akışı" : "Program Guide and Workflow");
  setText(
    "homeWorkflowSubtitle",
    currentLanguage === "tr"
      ? "Kararlı zincir: Veri Al → Karşılaştırma → DSC/DTA/TGA/FTIR/RAMAN → Toplu Şablon → Rapor/Proje"
      : "Stable chain: Import → Compare → DSC/DTA/TGA/FTIR/RAMAN → Batch Template → Report/Project"
  );
  setText("homeImportTitle", currentLanguage === "tr" ? "Veri İçe Aktar" : "Import Runs");
  setText(
    "homeImportSubtitle",
    currentLanguage === "tr"
      ? "Dosyayı yükle, import güvenini ve doğrulama uyarılarını incele, sonra analize geç."
      : "Upload run files, review import confidence and validation warnings, then continue to analysis."
  );
  setText("importDatasetBtn", currentLanguage === "tr" ? "Veri Seti İçe Aktar" : "Import Dataset");
  setText("datasetTypeOverrideLabel", currentLanguage === "tr" ? "Tip Geçersiz Kılma" : "Type Override");
  setSelectOptionText("datasetTypeSelect", "", currentLanguage === "tr" ? "Otomatik" : "Auto");
  setText("homeWorkspaceDatasetsTitle", currentLanguage === "tr" ? "Çalışma Alanı Veri Setleri" : "Workspace Datasets");
  setText(
    "homeWorkspaceDatasetsSubtitle",
    currentLanguage === "tr"
      ? "Aktif veri setini seç, karşılaştırma seçimini güncelle ve doğrulama durumunu denetle."
      : "Set active dataset, update compare selection, and inspect validation readiness."
  );
  setText("homeDatasetDetailTitle", currentLanguage === "tr" ? "Seçili Veri Seti Detayı" : "Selected Dataset Detail");

  setText("compareViewTitle", t("nav.compare"));
  setText(
    "compareViewCopy",
    currentLanguage === "tr"
      ? "Uyumlu koşuları seç, çalışma alanı notlarını kaydet ve ortak şablonla toplu yürütmeye geç."
      : "Select compatible runs, keep workspace notes, and execute a shared template batch."
  );
  setText(
    "compareStep1Title",
    currentLanguage === "tr"
      ? "Adım 1 - Karşılaştırma alanı durumunu gözden geçir"
      : "Step 1 - Review compare workspace status"
  );
  setText(
    "compareStep2Title",
    currentLanguage === "tr"
      ? "Adım 2 - Seçili veri setlerini ve notları yönet"
      : "Step 2 - Manage selected datasets and notes"
  );
  setText(
    "compareStep3Title",
    currentLanguage === "tr"
      ? "Adım 3 - Seçili veri setlerinde toplu şablonu çalıştır"
      : "Step 3 - Run batch template on selected datasets"
  );
  setText("compareAnalysisTypeLabel", t("compare.analysisType"));
  setText("addSelectedToCompareBtn", currentLanguage === "tr" ? "Seçili Veri Setini Ekle" : "Add Selected Dataset");
  setText("removeSelectedFromCompareBtn", currentLanguage === "tr" ? "Seçili Veri Setini Çıkar" : "Remove Selected Dataset");
  setText("clearCompareSelectionBtn", currentLanguage === "tr" ? "Karşılaştırma Seçimini Temizle" : "Clear Compare Selection");
  setText("compareNotesLabel", currentLanguage === "tr" ? "Çalışma Alanı Notları" : "Workspace Notes");
  setText("refreshCompareBtn", currentLanguage === "tr" ? "Karşılaştırmayı Yenile" : "Refresh Compare");
  setText("saveCompareBtn", currentLanguage === "tr" ? "Karşılaştırma Seçimini Kaydet" : "Save Compare Selection");
  setText("batchAnalysisLabel", currentLanguage === "tr" ? "Analiz" : "Analysis");
  setText("batchTemplateLabel", currentLanguage === "tr" ? "Şablon ID" : "Template ID");
  setText("runBatchBtn", currentLanguage === "tr" ? "Karşılaştırma Seçiminde Batch Çalıştır" : "Run Batch On Compare Selection");

  setText("dscViewTitle", currentLanguage === "tr" ? "DSC Analizi" : "DSC Analysis");
  setText(
    "dscViewCopy",
    currentLanguage === "tr"
      ? "Veri seti bağlamı, doğrulama görünürlüğü ve şablon sürekliliği ile DSC akışını adım adım yürüt."
      : "Run guided DSC workflow with dataset context, validation visibility, and template continuity."
  );
  setText("dscStep1Title", currentLanguage === "tr" ? "Adım 1 - Aktif veri seti ve yöntem bağlamı" : "Step 1 - Active dataset and method context");
  setText("dscStep2Title", currentLanguage === "tr" ? "Adım 2 - Doğrulama ve hazır olma kontrolleri" : "Step 2 - Validation and readiness checks");
  setText("dscStep3Title", currentLanguage === "tr" ? "Adım 3 - DSC analizini çalıştır" : "Step 3 - Run DSC analysis");
  setText("dscStep4Title", currentLanguage === "tr" ? "Adım 4 - Kayıtlı sonuç bağlamı" : "Step 4 - Saved result context");
  setText("runDscAnalysisBtn", currentLanguage === "tr" ? "DSC Analizini Çalıştır" : "Run DSC Analysis");
  setText("inspectSelectedDatasetBtn", currentLanguage === "tr" ? "Seçili Veri Setini İncele" : "Inspect Selected Dataset");

  setText("dtaViewTitle", currentLanguage === "tr" ? "DTA Analizi" : "DTA Analysis");
  setText(
    "dtaViewCopy",
    currentLanguage === "tr"
      ? "Kararlı DTA akışını veri seti bağlamı, doğrulama görünürlüğü ve şablon sürekliliği ile adım adım yürüt."
      : "Run guided stable DTA workflow with dataset context, validation visibility, and template continuity."
  );
  setText("dtaStep1Title", currentLanguage === "tr" ? "Adım 1 - Aktif veri seti ve yöntem bağlamı" : "Step 1 - Active dataset and method context");
  setText("dtaStep2Title", currentLanguage === "tr" ? "Adım 2 - Doğrulama ve hazır olma kontrolleri" : "Step 2 - Validation and readiness checks");
  setText("dtaStep3Title", currentLanguage === "tr" ? "Adım 3 - DTA analizini çalıştır" : "Step 3 - Run DTA analysis");
  setText("dtaStep4Title", currentLanguage === "tr" ? "Adım 4 - Kayıtlı sonuç bağlamı" : "Step 4 - Saved result context");
  setText("runDtaAnalysisBtn", currentLanguage === "tr" ? "DTA Analizini Çalıştır" : "Run DTA Analysis");
  setText("inspectSelectedDatasetBtn3", currentLanguage === "tr" ? "Seçili Veri Setini İncele" : "Inspect Selected Dataset");

  setText("tgaViewTitle", currentLanguage === "tr" ? "TGA Analizi" : "TGA Analysis");
  setText(
    "tgaViewCopy",
    currentLanguage === "tr"
      ? "Birim/review bağlamı, doğrulama kontrolleri ve şablon görünürlüğü ile TGA akışını adım adım yürüt."
      : "Run guided TGA workflow with unit/review context, validation checks, and template visibility."
  );
  setText("tgaStep1Title", currentLanguage === "tr" ? "Adım 1 - Aktif veri seti ve birim bağlamı" : "Step 1 - Active dataset and unit context");
  setText("tgaStep2Title", currentLanguage === "tr" ? "Adım 2 - Doğrulama ve review uyarıları" : "Step 2 - Validation and review warnings");
  setText("tgaStep3Title", currentLanguage === "tr" ? "Adım 3 - TGA analizini çalıştır" : "Step 3 - Run TGA analysis");
  setText("tgaStep4Title", currentLanguage === "tr" ? "Adım 4 - Kayıtlı sonuç bağlamı" : "Step 4 - Saved result context");
  setText("runTgaAnalysisBtn", currentLanguage === "tr" ? "TGA Analizini Çalıştır" : "Run TGA Analysis");
  setText("inspectSelectedDatasetBtn2", currentLanguage === "tr" ? "Seçili Veri Setini İncele" : "Inspect Selected Dataset");

  setText("exportViewTitle", currentLanguage === "tr" ? "Rapor Merkezi" : "Report Center");
  setText(
    "exportViewCopy",
    currentLanguage === "tr"
      ? "Kayıtlı sonuçlardan export paketini hazırla ve CSV/DOCX çıktıları üret."
      : "Prepare exports from saved results and generate CSV/DOCX deliverables."
  );
  setText("exportStep1Title", currentLanguage === "tr" ? "Adım 1 - Export bağlamını hazırla" : "Step 1 - Prepare export context");
  setText("exportStep2Title", currentLanguage === "tr" ? "Adım 2 - Kayıtlı sonuçları seç" : "Step 2 - Choose saved results");
  setText("exportStep3Title", currentLanguage === "tr" ? "Adım 3 - Çıktıları üret" : "Step 3 - Generate deliverables");
  setText("refreshExportPrepBtn", currentLanguage === "tr" ? "Export Bağlamını Yenile" : "Refresh Export Context");
  setText("exportCsvBtn", currentLanguage === "tr" ? "Sonuç CSV Üret" : "Generate Results CSV");
  setText("exportDocxBtn", currentLanguage === "tr" ? "DOCX Rapor Üret" : "Generate DOCX Report");
  setText(
    "exportStep3Hint",
    currentLanguage === "tr"
      ? "Çıktılar mevcut çalışma alanından üretilir ve seçilen dosya yoluna kaydedilir."
      : "Artifacts are generated from the current workspace and saved to your chosen path."
  );

  setText("projectViewTitle", currentLanguage === "tr" ? "Proje Alanı" : "Project Workspace");
  setText(
    "projectViewCopy",
    currentLanguage === "tr"
      ? "Arşiv güvenini yönet, kayıtlı sonuçları denetle ve proje durumunu güvenle kalıcılaştır."
      : "Manage archive confidence, inspect saved results, and persist project state safely."
  );
  setText("projectStep1Title", currentLanguage === "tr" ? "Proje arşivi kontrolleri" : "Project archive controls");
  setText("projectStep2Title", currentLanguage === "tr" ? "Kayıtlı sonuç arşivi" : "Saved results archive");
  setText("projectStep3Title", currentLanguage === "tr" ? "Seçili sonuç detayı" : "Selected result detail");
  setText(
    "projectStep2Hint",
    currentLanguage === "tr"
      ? "Kayıtları denetle, doğrulama/provenance durumunu doğrula ve detay inceleme için bir sonuç seç."
      : "Inspect saved records, verify validation/provenance, and open result details."
  );
  setText("saveProjectBtnProjectView", currentLanguage === "tr" ? "Projeyi Kaydet" : "Save Workspace");
  setText("refreshWorkspaceContextBtnProjectView", currentLanguage === "tr" ? "Bağlamı Yenile" : "Refresh Context");

  setText("licenseViewTitle", currentLanguage === "tr" ? "Lisans ve Marka" : "License & Branding");
  setText(
    "licenseViewCopy",
    currentLanguage === "tr"
      ? "Masaüstü build bilgisi, yayın kapsamı ve demo notları."
      : "Desktop build information, release scope, and demo notes."
  );
  setText("licenseVersionLabel", currentLanguage === "tr" ? "Uygulama Sürümü" : "App Version");
  setText("licenseProjectExtLabel", currentLanguage === "tr" ? "Proje Uzantısı" : "Project Extension");
  setText("licenseFocusLabel", currentLanguage === "tr" ? "Desktop Build Odağı" : "Desktop Release Focus");
  setText(
    "licenseFocusValue",
    currentLanguage === "tr"
      ? "Kararlı DSC/DTA/TGA/FTIR/RAMAN akışları, karşılaştırma alanı, proje arşivi ve CSV/DOCX çıktıları"
      : "Stable DSC/DTA/TGA/FTIR/RAMAN workflows, compare workspace, project archive, and CSV/DOCX outputs"
  );
  setText("licenseNotesTitle", currentLanguage === "tr" ? "Profesör Demo Notları" : "Professor Demo Notes");
  setText(
    "licenseNotesSubtitle",
    currentLanguage === "tr"
      ? "Bu masaüstü build kararlı öğretim/demo akışları için optimize edildi."
      : "This desktop build is optimized for stable teaching/demo workflows."
  );
  const notesList = el("licenseNotesList");
  if (notesList) {
    notesList.innerHTML = currentLanguage === "tr"
      ? [
          "<li>Kararlı odak: DSC/DTA/TGA/FTIR/RAMAN analizi, karşılaştırma alanı, proje arşivi kaydet/yükle, CSV/DOCX çıktıları.</li>",
          "<li>Önizleme modülleri (kinetik, dekonvolüsyon) demo sözü kapsamı dışındadır.</li>",
          "<li>Streamlit fallback/reference implementation olarak dokunulmadan korunur.</li>",
        ].join("")
      : [
          "<li>Stable focus: DSC/DTA/TGA/FTIR/RAMAN analysis, compare workspace, save/load project archives, CSV/DOCX artifacts.</li>",
          "<li>Preview modules (kinetics, deconvolution) remain outside the demo promise.</li>",
          "<li>Streamlit remains available as untouched fallback/reference implementation.</li>",
        ].join("");
  }

  setText("diagnosticsViewTitle", currentLanguage === "tr" ? "Tanılama" : "Diagnostics");
  setText(
    "diagnosticsViewCopy",
    currentLanguage === "tr"
      ? "Sorun giderme için teknik payload ve log alanı. Normal ürün akışının parçası değildir."
      : "Technical payloads and logs for troubleshooting. Not part of the normal product flow."
  );
  setText("diagWorkspaceTitle", currentLanguage === "tr" ? "Çalışma Alanı Bağlam Payload" : "Workspace Context Payload");
  setText("diagDatasetTitle", currentLanguage === "tr" ? "Veri Seti Detay Payload" : "Dataset Detail Payload");
  setText("diagResultTitle", currentLanguage === "tr" ? "Sonuç Detay Payload" : "Result Detail Payload");
  setText("diagCompareTitle", currentLanguage === "tr" ? "Karşılaştırma Payload" : "Compare Payload");
  setText("diagBatchTitle", currentLanguage === "tr" ? "Batch Payload" : "Batch Payload");
  setText("diagExportTitle", currentLanguage === "tr" ? "Export Payload" : "Export Payload");
  setText("diagLogTitle", currentLanguage === "tr" ? "Log" : "Log");
}
function appendLog(message) {
  const node = el("log");
  if (!node) return;
  const now = new Date().toLocaleTimeString();
  node.textContent = `${node.textContent}\n[${now}] ${message}`.trim();
}

function switchView(name) {
  activeView = name;
  document.querySelectorAll(".view").forEach((node) => node.classList.remove("active"));
  document.querySelectorAll(".nav-item[data-view]").forEach((node) => node.classList.remove("active"));
  const view = el(`view-${name}`);
  if (view) view.classList.add("active");
  const nav = document.querySelector(`.nav-item[data-view="${name}"]`);
  if (nav) nav.classList.add("active");
  const titleKey = viewTitleKeys[name];
  setText("pageTitle", titleKey ? t(titleKey) : "ThermoAnalyzer Desktop");
}

function updateStatusWorkspace() {
  setText("statusWorkspace", t("status.workspace", { workspace: activeProjectId || t("common.none") }));
}

function updateAnalysisActionState() {
  const enabled = Boolean(activeProjectId && selectedDatasetKey);
  setDisabled("runDscAnalysisBtn", !enabled);
  setDisabled("runDtaAnalysisBtn", !enabled);
  setDisabled("runTgaAnalysisBtn", !enabled);
  setDisabled("inspectSelectedDatasetBtn", !enabled);
  setDisabled("inspectSelectedDatasetBtn3", !enabled);
  setDisabled("inspectSelectedDatasetBtn2", !enabled);
  setDisabled("addSelectedToCompareBtn", !enabled);
  setDisabled("removeSelectedFromCompareBtn", !enabled);
}

function setWorkflowEnabled(enabled) {
  setDisabled("saveProjectBtn", !enabled);
  setDisabled("saveProjectBtnProjectView", !enabled);
  setDisabled("refreshWorkspaceContextBtn", !enabled);
  setDisabled("refreshWorkspaceContextBtnProjectView", !enabled);
  setDisabled("importDatasetBtn", !enabled);
  setDisabled("refreshCompareBtn", !enabled);
  setDisabled("saveCompareBtn", !enabled);
  setDisabled("clearCompareSelectionBtn", !enabled);
  setDisabled("runBatchBtn", !enabled);
  setDisabled("refreshExportPrepBtn", !enabled);
  setDisabled("exportCsvBtn", !enabled);
  setDisabled("exportDocxBtn", !enabled);
  updateAnalysisActionState();
}

function escapeHtml(text) {
  return String(text || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function safeJson(value) {
  return JSON.stringify(value || {}, null, 2);
}

function setDiagnostic(name, value) {
  const map = {
    workspace: "diagWorkspaceContext",
    dataset: "diagDatasetDetail",
    result: "diagResultDetail",
    compare: "diagComparePayload",
    batch: "diagBatchPayload",
    export: "diagExportPayload",
  };
  const targetId = map[name];
  if (targetId) {
    setText(targetId, safeJson(value));
  }
}

function valueOr(value, fallback = "N/A") {
  if (value === undefined || value === null || value === "") {
    return fallback;
  }
  return String(value);
}

function keyGrid(items) {
  return `<div class="kv-grid">${(items || [])
    .map(
      (item) => `
      <div class="kv-item">
        <div class="kv-label">${escapeHtml(item.label)}</div>
        <div class="kv-value">${escapeHtml(item.value)}</div>
      </div>`
    )
    .join("")}</div>`;
}

function renderIssueList(title, items) {
  if (!items || !items.length) {
    return `<p class="small muted">${escapeHtml(title)}: ${escapeHtml(t("common.none"))}</p>`;
  }
  return `<p class="small"><strong>${escapeHtml(title)}:</strong></p><ul class="list-box">${items
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("")}</ul>`;
}

function renderRowsPreview(rows) {
  const data = Array.isArray(rows) ? rows.slice(0, 8) : [];
  if (!data.length) return `<p class="small muted">${escapeHtml(t("common.noPreviewRows"))}</p>`;
  const keys = Object.keys(data[0] || {}).slice(0, 6);
  if (!keys.length) return `<p class="small muted">${escapeHtml(t("common.noPreviewRows"))}</p>`;
  return `<table><thead><tr>${keys.map((key) => `<th>${escapeHtml(key)}</th>`).join("")}</tr></thead><tbody>${data
    .map((row) => `<tr>${keys.map((key) => `<td>${escapeHtml(row[key])}</td>`).join("")}</tr>`)
    .join("")}</tbody></table>`;
}

function asArray(value) {
  if (Array.isArray(value)) return value;
  if (typeof value === "string" && value.trim()) return [value.trim()];
  return [];
}

function toneBadgeClass(statusToken) {
  const token = String(statusToken || "").toLowerCase();
  if (token === "pass" || token === "ok" || token === "saved") return "badge badge-ok";
  if (token === "warn" || token === "warning" || token === "blocked") return "badge badge-warn";
  if (token === "fail" || token === "error" || token === "failed") return "badge badge-fail";
  return "badge badge-neutral";
}

function renderCompareSelectionChips(selectedKeys) {
  const keys = selectedKeys || [];
  if (!keys.length) {
    setHtml("compareSelectedDatasetsPanel", `<span class="dataset-chip">${escapeHtml(t("common.noCompareSelected"))}</span>`);
    return;
  }
  const chips = keys
    .map((key) => {
      const dataset = currentDatasets.find((item) => item.key === key);
      const suffix = dataset ? `${dataset.data_type}` : t("common.unknown");
      return `<span class="dataset-chip">${escapeHtml(key)} (${escapeHtml(suffix)})</span>`;
    })
    .join("");
  setHtml("compareSelectedDatasetsPanel", chips);
}

function renderHomeWorkflowSteps(context) {
  const summary = (context && context.summary) || {};
  const compareWorkspace = (context && context.compare_workspace) || {};
  const datasetCount = Number(summary.dataset_count || 0);
  const resultCount = Number(summary.result_count || 0);
  const selectedCompareCount = (compareWorkspace.selected_datasets || []).length;

  setText("homeStepWorkspaceStatus", activeProjectId ? t("home.stepWorkspaceReady") : t("home.stepWorkspacePending"));
  setText("homeStepImportStatus", datasetCount > 0 ? t("home.stepImportDone", { count: datasetCount }) : t("home.stepImportPending"));
  setText("homeStepCompareStatus", selectedCompareCount > 0 ? t("home.stepCompareDone", { count: selectedCompareCount }) : t("home.stepComparePending"));
  setText("homeStepRunStatus", resultCount > 0 ? t("home.stepRunDone", { count: resultCount }) : t("home.stepRunPending"));

  let nextStep = t("home.nextCreate");
  if (activeProjectId) nextStep = t("home.nextImport");
  if (datasetCount > 0) nextStep = t("home.nextInspect");
  if (selectedCompareCount > 0) nextStep = t("home.nextRun");
  if (resultCount > 0) nextStep = t("home.nextSave");
  setText("homeNextStepValue", nextStep);
}

function renderCompareWorkspaceSummary(compareWorkspace) {
  const payload = compareWorkspace || {};
  const selectedCount = (payload.selected_datasets || []).length;
  setHtml(
    "compareSummaryPanel",
    `
    ${keyGrid([
      { label: t("compare.analysisType"), value: valueOr(payload.analysis_type, "DSC") },
      { label: t("compare.selectedCount"), value: String(selectedCount) },
      { label: t("compare.savedAt"), value: valueOr(payload.saved_at, t("common.na")) },
      { label: t("compare.batchRunId"), value: valueOr(payload.batch_run_id, t("common.none")) },
      { label: t("compare.batchTemplate"), value: valueOr(payload.batch_template_id, t("common.none")) },
      { label: t("compare.notes"), value: valueOr(payload.notes, t("compare.notesEmpty")) },
    ])}
    <div style="margin-top:8px;">
      <span class="${toneBadgeClass(selectedCount > 0 ? "ok" : "warning")}">${escapeHtml(t("common.selected"))}: ${selectedCount}</span>
      <span class="${toneBadgeClass(payload.batch_run_id ? "saved" : "neutral")}">${escapeHtml(t("common.batch"))}: ${payload.batch_run_id ? escapeHtml(t("common.available")) : escapeHtml(t("common.notRun"))}</span>
    </div>
    `
  );
  renderCompareSelectionChips(payload.selected_datasets || []);
}

function isDatasetEligibleForAnalysis(analysisType, datasetType) {
  const token = String(analysisType || "").toUpperCase();
  const dtype = String(datasetType || "UNKNOWN").toUpperCase();
  if (token === "DSC") return dtype === "DSC" || dtype === "DTA" || dtype === "UNKNOWN";
  if (token === "DTA") return dtype === "DTA" || dtype === "UNKNOWN";
  if (token === "TGA") return dtype === "TGA" || dtype === "UNKNOWN";
  if (token === "FTIR") return dtype === "FTIR" || dtype === "UNKNOWN";
  if (token === "RAMAN") return dtype === "RAMAN" || dtype === "UNKNOWN";
  return false;
}

function findLatestResultByType(analysisType) {
  const token = String(analysisType || "").toUpperCase();
  const filtered = (currentResults || []).filter((item) => String(item.analysis_type || "").toUpperCase() === token);
  if (!filtered.length) return null;
  const sorted = [...filtered].sort((a, b) => {
    const aTime = Date.parse(a.saved_at_utc || "") || 0;
    const bTime = Date.parse(b.saved_at_utc || "") || 0;
    return bTime - aTime;
  });
  return sorted[0];
}

function renderAnalysisPage(analysisType) {
  const token = String(analysisType || "").toUpperCase();
  const profile = {
    DSC: { prefix: "dsc", defaultTemplate: "dsc.general" },
    DTA: { prefix: "dta", defaultTemplate: "dta.general" },
    TGA: { prefix: "tga", defaultTemplate: "tga.general" },
    FTIR: { prefix: "dsc", defaultTemplate: "ftir.general" },
    RAMAN: { prefix: "dsc", defaultTemplate: "raman.general" },
  }[token] || { prefix: "dsc", defaultTemplate: "dsc.general" };
  const isTr = currentLanguage === "tr";
  const prefix = profile.prefix;
  const defaultTemplate = profile.defaultTemplate;
  const dataset = (currentDatasets || []).find((item) => item.key === selectedDatasetKey) || null;
  const detail = currentDatasetDetail && currentDatasetDetail.dataset && currentDatasetDetail.dataset.key === selectedDatasetKey
    ? currentDatasetDetail
    : null;
  const validation = (detail && detail.validation) || {};
  const metadata = (detail && detail.metadata) || {};
  const units = (detail && detail.units) || {};
  const importWarnings = asArray(metadata.import_warnings);
  const issues = validation.issues || [];
  const warnings = validation.warnings || [];
  const reviewRequired = Boolean(metadata.import_review_required);
  const confidence = valueOr(metadata.import_confidence || metadata.import_confidence_level, isTr ? "kayıt_yok" : "not_recorded");
  const eligible = dataset ? isDatasetEligibleForAnalysis(token, dataset.data_type) : false;

  const latestResult = findLatestResultByType(token);
  const focusedResult = currentResultDetail && currentResultDetail.result && String(currentResultDetail.result.analysis_type || "").toUpperCase() === token
    ? currentResultDetail
    : null;
  const runInfo = lastAnalysisRuns[token];

  setHtml(
    `${prefix}ActiveDatasetContextPanel`,
    dataset
      ? `
      ${keyGrid([
        { label: isTr ? "Veri Seti Anahtarı" : "Dataset Key", value: valueOr(dataset.key) },
        { label: isTr ? "Veri Seti Tipi" : "Dataset Type", value: valueOr(dataset.data_type, isTr ? "bilinmiyor" : "unknown") },
        { label: isTr ? "Numune" : "Sample", value: valueOr(dataset.sample_name, isTr ? "adlandırılmamış" : "not named") },
        { label: isTr ? "Çalışma Alanında Aktif" : "Active In Workspace", value: dataset.key === currentActiveDatasetKey ? (isTr ? "evet" : "yes") : (isTr ? "hayır" : "no") },
      ])}
      <div style="margin-top:8px;">
        <span class="${toneBadgeClass(eligible ? "ok" : "warning")}">${token} ${isTr ? "uygunluk" : "eligibility"}: ${eligible ? (isTr ? "uyumlu" : "compatible") : (isTr ? "veri tipini gözden geçir" : "review dataset type")}</span>
      </div>
      `
      : (isTr ? "Analiz bağlamını başlatmak için Veri Al sayfasından bir veri seti seç." : "Select a dataset from Home / Import to begin analysis context.")
  );

  setHtml(
    `${prefix}MethodContextPanel`,
    token === "DSC"
      ? `
      ${keyGrid([
        { label: isTr ? "Önerilen İş Akışı Şablonu" : "Suggested Workflow Template", value: defaultTemplate },
        { label: isTr ? "Seçili Veri Tipi" : "Selected Dataset Type", value: valueOr(dataset && dataset.data_type, t("common.none")) },
        { label: isTr ? "Doğrulama Durumu" : "Validation Status", value: valueOr(validation.status, dataset ? dataset.validation_status : t("common.unknown")) },
      ])}
      `
      : token === "DTA"
      ? `
      ${keyGrid([
        { label: isTr ? "Önerilen İş Akışı Şablonu" : "Suggested Workflow Template", value: defaultTemplate },
        { label: isTr ? "Seçili Veri Tipi" : "Selected Dataset Type", value: valueOr(dataset && dataset.data_type, t("common.none")) },
        { label: isTr ? "Sinyal Birimi" : "Signal Unit", value: valueOr(units.signal, "n/a") },
      ])}
      `
      : `
      ${keyGrid([
        { label: isTr ? "Önerilen İş Akışı Şablonu" : "Suggested Workflow Template", value: defaultTemplate },
        { label: isTr ? "Seçili Veri Tipi" : "Selected Dataset Type", value: valueOr(dataset && dataset.data_type, t("common.none")) },
        { label: isTr ? "Sinyal Birimi" : "Signal Unit", value: valueOr(units.signal, "n/a") },
      ])}
      `
  );

  const validationContextHtml = `
    <div>
      <span class="${toneBadgeClass(validation.status || (dataset && dataset.validation_status))}">${isTr ? "Doğrulama" : "Validation"}: ${escapeHtml(valueOr(validation.status || (dataset && dataset.validation_status), t("common.unknown")))}</span>
      <span class="${toneBadgeClass(reviewRequired ? "warning" : "ok")}">${isTr ? "Import Review Gerekli" : "Import Review Required"}: ${reviewRequired ? (isTr ? "evet" : "yes") : (isTr ? "hayır" : "no")}</span>
      <span class="badge badge-neutral">${isTr ? "Import Güveni" : "Import Confidence"}: ${escapeHtml(confidence)}</span>
    </div>
    ${renderIssueList(isTr ? "Doğrulama uyarıları" : "Validation warnings", warnings)}
    ${renderIssueList(isTr ? "Doğrulama sorunları" : "Validation issues", issues)}
    ${renderIssueList(isTr ? "Import uyarıları" : "Import warnings", importWarnings)}
  `;
  setHtml(`${prefix}ValidationPanel`, validationContextHtml);

  if (token === "TGA") {
    setHtml(
      "tgaUnitContextPanel",
      `
      ${keyGrid([
        { label: isTr ? "Sıcaklık Birimi" : "Temperature Unit", value: valueOr(units.temperature, "n/a") },
        { label: isTr ? "Sinyal Birimi" : "Signal Unit", value: valueOr(units.signal, "n/a") },
        { label: isTr ? "Çıkarılan Sinyal Birimi" : "Inferred Signal Unit", value: valueOr(metadata.inferred_signal_unit, "n/a") },
        { label: isTr ? "Import Review Gerekli" : "Import Review Required", value: reviewRequired ? (isTr ? "evet" : "yes") : (isTr ? "hayır" : "no") },
      ])}
      `
    );
  }

  const templateFromResult = focusedResult && focusedResult.processing
    ? valueOr(focusedResult.processing.workflow_template_id, defaultTemplate)
    : defaultTemplate;
  setHtml(
    `${prefix}TemplateContextPanel`,
    `
    ${keyGrid([
      { label: isTr ? "Şablon ID" : "Template ID", value: templateFromResult },
      { label: isTr ? "Sayfa Analiz Tipi" : "Page Analysis Type", value: token },
      { label: isTr ? "Çalıştırmaya Hazır" : "Ready To Run", value: dataset && eligible ? (isTr ? "evet" : "yes") : (isTr ? "uyumlu veri seti seç" : "select compatible dataset") },
    ])}
    <p class="small">${isTr ? "Çalıştırma, aynı proje sonuç deposuna kaydeder ve doğrulama/provenance bağlamını korur." : "Run will save into the same project result store and preserve validation/provenance context."}</p>
    `
  );

  const resultPanelId = `${prefix}ResultSummaryPanel`;
  if (focusedResult) {
    setHtml(
      resultPanelId,
      `
      ${keyGrid([
        { label: isTr ? "Odak Sonuç ID" : "Focused Result ID", value: valueOr(focusedResult.result.id) },
        { label: isTr ? "Durum" : "Status", value: valueOr(focusedResult.result.status) },
        { label: isTr ? "Veri Seti" : "Dataset", value: valueOr(focusedResult.result.dataset_key) },
        { label: isTr ? "Şablon" : "Template", value: valueOr(focusedResult.processing && focusedResult.processing.workflow_template_id, "n/a") },
        { label: isTr ? "Kaydedilme (UTC)" : "Saved At (UTC)", value: valueOr(focusedResult.provenance && focusedResult.provenance.saved_at_utc, "n/a") },
      ])}
      <div style="margin-top:8px;">
        <span class="${toneBadgeClass(focusedResult.validation && focusedResult.validation.status)}">${isTr ? "Doğrulama" : "Validation"}: ${escapeHtml(valueOr(focusedResult.validation && focusedResult.validation.status, t("common.unknown")))}</span>
        <span class="badge badge-neutral">${isTr ? "Kalibrasyon" : "Calibration"}: ${escapeHtml(valueOr(focusedResult.provenance && focusedResult.provenance.calibration_state, t("common.unknown")))}</span>
        <span class="badge badge-neutral">${isTr ? "Referans" : "Reference"}: ${escapeHtml(valueOr(focusedResult.provenance && focusedResult.provenance.reference_state, t("common.unknown")))}</span>
      </div>
      `
    );
  } else if (latestResult) {
    setHtml(
      resultPanelId,
      `
      ${keyGrid([
        { label: isTr ? "Son Kayıtlı Sonuç" : "Latest Saved Result", value: valueOr(latestResult.id) },
        { label: isTr ? "Durum" : "Status", value: valueOr(latestResult.status) },
        { label: isTr ? "Veri Seti" : "Dataset", value: valueOr(latestResult.dataset_key) },
        { label: isTr ? "Doğrulama" : "Validation", value: valueOr(latestResult.validation_status, t("common.unknown")) },
        { label: isTr ? "Kaydedilme (UTC)" : "Saved At (UTC)", value: valueOr(latestResult.saved_at_utc, "n/a") },
      ])}
      <p class="small">${isTr ? "Tam işleme/provenance detayları için bu sonucu Proje Alanı'ndan aç." : "Open this result from Project page to inspect full processing/provenance details."}</p>
      `
    );
  } else {
    setHtml(resultPanelId, isTr ? `Henüz ${token} sonuç bağlamı yok.` : `No ${token} result context yet.`);
  }

  if (runInfo) {
    const infoText = isTr
      ? `${token} ${runInfo.dataset_key}: ${runInfo.execution_status}${runInfo.result_id ? ` (${runInfo.result_id})` : ""}${runInfo.failure_reason ? ` - ${runInfo.failure_reason}` : ""}`
      : `${token} on ${runInfo.dataset_key}: ${runInfo.execution_status}${runInfo.result_id ? ` (${runInfo.result_id})` : ""}${runInfo.failure_reason ? ` - ${runInfo.failure_reason}` : ""}`;
    setText(`${prefix}AnalysisInfo`, infoText);
  } else if (!dataset) {
    setText(`${prefix}AnalysisInfo`, isTr ? `Henüz ${token} analizi çalıştırılmadı.` : `No ${token} analysis executed yet.`);
  }
}

function renderAnalysisPages() {
  renderAnalysisPage("DSC");
  renderAnalysisPage("DTA");
  renderAnalysisPage("TGA");
}

function applyWorkspaceContext(context) {
  currentActiveDatasetKey = context.active_dataset_key || null;
  compareSelectedDatasetKeys = new Set((context.compare_workspace && context.compare_workspace.selected_datasets) || []);
  const compareCount = context.compare_workspace && context.compare_workspace.selected_datasets
    ? context.compare_workspace.selected_datasets.length
    : 0;
  const latestResultText = context.latest_result && context.latest_result.id ? context.latest_result.id : t("common.none");
  const compareWorkspace = context.compare_workspace || {};

  setText(
    "homeProjectInfo",
    currentLanguage === "tr"
      ? `Çalışma Alanı ${activeProjectId} | veri=${context.summary.dataset_count} | sonuç=${context.summary.result_count}`
      : `Workspace ${activeProjectId} | datasets=${context.summary.dataset_count} | results=${context.summary.result_count}`
  );
  setText("homeDatasetCountValue", String(context.summary.dataset_count || 0));
  setText("homeResultCountValue", String(context.summary.result_count || 0));
  setText(
    "projectViewInfo",
    currentLanguage === "tr"
      ? `Çalışma Alanı ${activeProjectId} | görsel=${context.summary.figure_count} | geçmiş=${context.summary.analysis_history_count}`
      : `Workspace ${activeProjectId} | figures=${context.summary.figure_count} | history=${context.summary.analysis_history_count}`
  );
  setText("projectDatasetCountValue", String(context.summary.dataset_count || 0));
  setText("projectResultCountValue", String(context.summary.result_count || 0));
  setText("projectHistoryCountValue", String(context.summary.analysis_history_count || 0));
  setText("projectFigureCountValue", String(context.summary.figure_count || 0));
  const projectConfidence =
    Number(context.summary.dataset_count || 0) === 0
      ? (currentLanguage === "tr"
        ? "Proje arşivi için temel oluşturmak üzere veri seti içe aktar."
        : "Import datasets to establish project archive baseline.")
      : Number(context.summary.result_count || 0) === 0
      ? (currentLanguage === "tr"
        ? "Veriler içe aktarıldı. Sonuç geçmişi için analizleri çalıştır."
        : "Datasets imported. Run analyses to build saved result history.")
      : (currentLanguage === "tr"
        ? "Çalışma alanında kayıtlı sonuçlar var; proje arşivi ve export için hazır."
        : "Workspace has saved results and is ready for archive save/export.");
  setText("projectConfidenceMessage", projectConfidence);
  setText("homeActiveDatasetValue", currentActiveDatasetKey || t("common.none"));
  setText("homeLatestResultValue", latestResultText);
  setText("homeCompareCountValue", String(compareCount));
  setText("homeWorkspaceSavedAtValue", valueOr(compareWorkspace.saved_at, t("common.na")));
  setText(
    "compareMeta",
    currentLanguage === "tr"
      ? `Seçili koşu: ${compareCount} | Kaydedildi: ${valueOr(compareWorkspace.saved_at, t("common.na"))}`
      : `Selected datasets: ${compareCount} | Saved at: ${valueOr(compareWorkspace.saved_at, t("common.na"))}`
  );
  renderCompareWorkspaceSummary(compareWorkspace);
  renderHomeWorkflowSteps(context);
  setDiagnostic("workspace", {
    summary: context.summary,
    active_dataset: context.active_dataset,
    latest_result: context.latest_result,
    compare_workspace: compareWorkspace,
    compare_selected_datasets: context.compare_selected_datasets,
    recent_history: context.recent_history,
  });
  updateStatusWorkspace();
}

function renderCompareDatasetChecks(selectedDatasets) {
  const container = el("compareDatasetChecks");
  if (!currentDatasets.length) {
    container.innerHTML = `<div class='panel-soft small'>${escapeHtml(currentLanguage === "tr" ? "Kullanılabilir veri seti yok." : "No datasets available.")}</div>`;
    return;
  }

  const selected = new Set(selectedDatasets || []);
  container.innerHTML = currentDatasets
    .map((dataset) => {
      const checked = selected.has(dataset.key) ? "checked" : "";
      const cardClass = selected.has(dataset.key) ? "compare-pick selected" : "compare-pick";
      const isActive = dataset.key === currentActiveDatasetKey
        ? (currentLanguage === "tr" ? "Aktif çalışma alanı veri seti" : "Active workspace dataset")
        : (currentLanguage === "tr" ? "Aktif değil" : "Not active");
      return `
      <label class="${cardClass}">
        <div class="small">
          <input type="checkbox" class="compare-dataset-check" value="${escapeHtml(dataset.key)}" ${checked}>
          <strong>${escapeHtml(dataset.key)}</strong> (${escapeHtml(dataset.data_type)})
        </div>
        <div class="small muted">${escapeHtml(valueOr(dataset.sample_name, currentLanguage === "tr" ? "numune adı yok" : "sample not named"))}</div>
        <div class="small">
          <span class="${toneBadgeClass(dataset.validation_status)}">${currentLanguage === "tr" ? "Doğrulama" : "Validation"}: ${escapeHtml(valueOr(dataset.validation_status, t("common.unknown")))}</span>
          <span class="badge badge-neutral">${currentLanguage === "tr" ? "Uyarı" : "Warnings"}: ${escapeHtml(valueOr(dataset.warning_count, "0"))}</span>
          <span class="badge badge-neutral">${currentLanguage === "tr" ? "Sorun" : "Issues"}: ${escapeHtml(valueOr(dataset.issue_count, "0"))}</span>
        </div>
        <div class="small muted">${escapeHtml(isActive)}</div>
      </label>`;
    })
    .join("");
}

function collectCompareSelectedDatasets() {
  return Array.from(document.querySelectorAll(".compare-dataset-check"))
    .filter((node) => node.checked)
    .map((node) => node.value);
}

function collectSelectedExportResultIds() {
  return Array.from(document.querySelectorAll(".export-result-check"))
    .filter((node) => node.checked)
    .map((node) => node.value);
}

async function loadDatasetDetail(datasetKey) {
  if (!activeProjectId || !datasetKey) return;
  try {
    const isTr = currentLanguage === "tr";
    const detail = await window.taDesktop.getDatasetDetail(activeProjectId, datasetKey);
    currentDatasetDetail = detail;
    const validation = detail.validation || {};
    const metadata = detail.metadata || {};
    const importWarnings = asArray(metadata.import_warnings);
    const confidence = valueOr(metadata.import_confidence || metadata.import_confidence_level || "not_recorded", "not_recorded");
    const reviewRequired = Boolean(metadata.import_review_required);
    const inferredType = valueOr(metadata.inferred_analysis_type, "n/a");
    const inferredUnit = valueOr(metadata.inferred_signal_unit, "n/a");
    const inferredVendor = valueOr(metadata.inferred_vendor, "n/a");
    setText(
      "datasetDetailInfo",
      isTr
        ? `Veri seti ${detail.dataset.key} | Tip ${detail.dataset.data_type} | Doğrulama ${validation.status || "bilinmiyor"}`
        : `Dataset ${detail.dataset.key} | Type ${detail.dataset.data_type} | Validation ${validation.status || "unknown"}`
    );
    setHtml(
      "homeSelectedDatasetPanel",
      `
      ${keyGrid([
        { label: isTr ? "Seçili Veri Seti" : "Selected Dataset", value: detail.dataset.key },
        { label: isTr ? "Tip" : "Type", value: detail.dataset.data_type },
        { label: isTr ? "Numune" : "Sample", value: valueOr(detail.dataset.sample_name) },
        { label: isTr ? "Doğrulama" : "Validation", value: valueOr(validation.status, t("common.unknown")) },
        { label: isTr ? "Uyarı" : "Warnings", value: String((validation.warnings || []).length) },
        { label: isTr ? "Sorun" : "Issues", value: String((validation.issues || []).length) },
      ])}
      `
    );
    setHtml(
      "homeImportQualityPanel",
      `
      <div>
        <span class="${toneBadgeClass(validation.status)}">${isTr ? "Doğrulama" : "Validation"}: ${escapeHtml(valueOr(validation.status, t("common.unknown")))}</span>
        <span class="${toneBadgeClass(reviewRequired ? "warning" : "ok")}">${isTr ? "Review Gerekli" : "Review Required"}: ${reviewRequired ? t("common.yes") : t("common.no")}</span>
        <span class="badge badge-neutral">${isTr ? "Import Güveni" : "Import Confidence"}: ${escapeHtml(confidence)}</span>
      </div>
      ${keyGrid([
        { label: isTr ? "Çıkarılan Tip" : "Inferred Type", value: inferredType },
        { label: isTr ? "Çıkarılan Sinyal Birimi" : "Inferred Signal Unit", value: inferredUnit },
        { label: isTr ? "Çıkarılan Cihaz/Vendor" : "Inferred Vendor", value: inferredVendor },
      ])}
      ${renderIssueList(isTr ? "Import uyarıları" : "Import warnings", importWarnings)}
      `
    );
    setHtml(
      "datasetDetailPanel",
      `
      ${keyGrid([
        { label: isTr ? "Veri Seti Anahtarı" : "Dataset Key", value: detail.dataset.key },
        { label: isTr ? "Tip" : "Type", value: detail.dataset.data_type },
        { label: isTr ? "Numune" : "Sample", value: valueOr(detail.dataset.sample_name) },
        { label: isTr ? "Doğrulama" : "Validation", value: valueOr(validation.status, t("common.unknown")) },
        { label: isTr ? "Uyarı" : "Warnings", value: String((validation.warnings || []).length) },
        { label: isTr ? "Sorun" : "Issues", value: String((validation.issues || []).length) },
      ])}
      ${renderIssueList(isTr ? "Uyarılar" : "Warnings", validation.warnings || [])}
      ${renderIssueList(isTr ? "Sorunlar" : "Issues", validation.issues || [])}
      <p class="small"><strong>Metadata</strong></p>
      ${keyGrid(
        Object.entries(detail.metadata || {})
          .slice(0, 8)
          .map(([key, value]) => ({ label: key, value: valueOr(value) }))
      )}
      <p class="small"><strong>${isTr ? "Birimler / Kolonlar" : "Units / Columns"}</strong></p>
      ${keyGrid([
        { label: isTr ? "Sıcaklık Birimi" : "Temperature Unit", value: valueOr(detail.units && detail.units.temperature) },
        { label: isTr ? "Sinyal Birimi" : "Signal Unit", value: valueOr(detail.units && detail.units.signal) },
        { label: isTr ? "Orijinal Kolonlar" : "Original Columns", value: valueOr((detail.original_columns || []).join(", "), t("common.none")) },
        { label: isTr ? "Karşılaştırmada Seçili" : "Compare Selected", value: detail.compare_selected ? t("common.yes") : t("common.no") },
      ])}
      <p class="small"><strong>${isTr ? "Veri Önizleme" : "Data Preview"}</strong></p>
      ${renderRowsPreview(detail.data_preview || [])}
      `
    );
    setDiagnostic("dataset", detail);
    renderAnalysisPages();
  } catch (error) {
    const isTr = currentLanguage === "tr";
    currentDatasetDetail = null;
    setText("datasetDetailInfo", isTr ? `Veri seti detayı okunamadı: ${error}` : `Dataset detail failed: ${error}`);
    setHtml("datasetDetailPanel", isTr ? "<p class='fail'>Veri seti detayı kullanılamıyor.</p>" : "<p class='fail'>Dataset detail unavailable.</p>");
    setHtml("homeImportQualityPanel", isTr ? "<p class='fail'>Import güveni detayı kullanılamıyor.</p>" : "<p class='fail'>Import confidence details unavailable.</p>");
    setDiagnostic("dataset", { error: String(error) });
    renderAnalysisPages();
  }
}

async function loadResultDetail(resultId) {
  if (!activeProjectId || !resultId) return;
  try {
    const isTr = currentLanguage === "tr";
    const detail = await window.taDesktop.getResultDetail(activeProjectId, resultId);
    currentResultDetail = detail;
    const validation = detail.validation || {};
    const processing = detail.processing || {};
    const provenance = detail.provenance || {};
    setText(
      "resultDetailInfo",
      isTr
        ? `Sonuç ${detail.result.id} | ${detail.result.analysis_type} | durum=${detail.result.status}`
        : `Result ${detail.result.id} | ${detail.result.analysis_type} | status=${detail.result.status}`
    );
    setHtml(
      "resultDetailPanel",
      `
      ${keyGrid([
        { label: isTr ? "Sonuç ID" : "Result ID", value: detail.result.id },
        { label: isTr ? "Analiz Tipi" : "Analysis Type", value: detail.result.analysis_type },
        { label: isTr ? "Durum" : "Status", value: detail.result.status },
        { label: isTr ? "Veri Seti" : "Dataset", value: detail.result.dataset_key },
        { label: isTr ? "Doğrulama" : "Validation", value: valueOr(validation.status, t("common.unknown")) },
        { label: isTr ? "Kaydedilme (UTC)" : "Saved At (UTC)", value: valueOr(provenance.saved_at_utc) },
      ])}
      <p class="small"><strong>${isTr ? "İşleme / Şablon" : "Processing / Template"}</strong></p>
      ${keyGrid([
        { label: isTr ? "Şablon ID" : "Template ID", value: valueOr(processing.workflow_template_id, "n/a") },
        { label: isTr ? "Şablon Etiketi" : "Template Label", value: valueOr(processing.workflow_template_label, "n/a") },
        { label: isTr ? "Şema Sürümü" : "Schema Version", value: valueOr(processing.schema_version, "n/a") },
        { label: isTr ? "Kalibrasyon" : "Calibration", value: valueOr(provenance.calibration_state, t("common.unknown")) },
        { label: isTr ? "Referans" : "Reference", value: valueOr(provenance.reference_state, t("common.unknown")) },
        { label: isTr ? "Satır Sayısı" : "Row Count", value: valueOr(detail.row_count, "0") },
      ])}
      ${renderIssueList(isTr ? "Uyarılar" : "Warnings", validation.warnings || [])}
      ${renderIssueList(isTr ? "Sorunlar" : "Issues", validation.issues || [])}
      <p class="small"><strong>${isTr ? "Satır Önizleme" : "Rows Preview"}</strong></p>
      ${renderRowsPreview(detail.rows_preview || [])}
      `
    );
    setDiagnostic("result", detail);
    renderAnalysisPages();
  } catch (error) {
    const isTr = currentLanguage === "tr";
    currentResultDetail = null;
    setText("resultDetailInfo", isTr ? `Sonuç detayı okunamadı: ${error}` : `Result detail failed: ${error}`);
    setHtml("resultDetailPanel", isTr ? "<p class='fail'>Sonuç detayı kullanılamıyor.</p>" : "<p class='fail'>Result detail unavailable.</p>");
    setDiagnostic("result", { error: String(error) });
    renderAnalysisPages();
  }
}

function renderDatasets(datasets) {
  const body = el("datasetsBody");
  currentDatasets = datasets;
  const isTr = currentLanguage === "tr";
  if (!datasets.length) {
    body.innerHTML = `<tr><td colspan='10'>${isTr ? "Yüklü veri seti yok." : "No datasets loaded."}</td></tr>`;
    selectedDatasetKey = null;
    currentDatasetDetail = null;
    updateAnalysisActionState();
    setText("datasetDetailInfo", isTr ? "Veri seti detayı seçilmedi." : "No dataset detail selected.");
    setHtml("datasetDetailPanel", isTr ? "Metadata, doğrulama ve önizleme satırları için bir veri seti seç." : "Select a dataset to inspect metadata, validation, and preview rows.");
    setHtml("homeSelectedDatasetPanel", isTr ? "Aktif veri seti seçilmedi." : "No active dataset selected.");
    setHtml("homeImportQualityPanel", isTr ? "Import güveni ve review rehberi, veri seti incelendikten sonra burada görünür." : "Import confidence and review guidance will appear here after dataset inspection.");
    setDiagnostic("dataset", {});
    renderCompareDatasetChecks([]);
    renderAnalysisPages();
    return;
  }

  if (!selectedDatasetKey || !datasets.some((item) => item.key === selectedDatasetKey)) {
    selectedDatasetKey = datasets[0].key;
  }
  updateAnalysisActionState();

  body.innerHTML = datasets
    .map((item) => {
      const checked = item.key === selectedDatasetKey ? "checked" : "";
      const active = item.key === currentActiveDatasetKey ? (isTr ? "Aktif" : "Active") : "";
      const compareSelected = compareSelectedDatasetKeys.has(item.key);
      return `
      <tr>
        <td><input type="radio" name="datasetPick" value="${escapeHtml(item.key)}" ${checked}></td>
        <td>
          <button class="set-active-btn" data-dataset-key="${escapeHtml(item.key)}">${isTr ? "Aktif Yap" : "Set Active"}</button>
          <div class="small">${escapeHtml(active)}</div>
        </td>
        <td>
          <button class="toggle-compare-btn" data-dataset-key="${escapeHtml(item.key)}">${compareSelected ? (isTr ? "Çıkar" : "Remove") : (isTr ? "Ekle" : "Add")}</button>
          <div class="small">${compareSelected ? (isTr ? "Seçili" : "Selected") : (isTr ? "Seçili değil" : "Not selected")}</div>
        </td>
        <td><button class="inspect-dataset-btn" data-dataset-key="${escapeHtml(item.key)}">${isTr ? "İncele" : "View"}</button></td>
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
    node.addEventListener("change", async (event) => {
      selectedDatasetKey = event.target.value;
      updateAnalysisActionState();
      appendLog(currentLanguage === "tr" ? `Seçili veri seti: ${selectedDatasetKey}` : `Selected dataset: ${selectedDatasetKey}`);
      await loadDatasetDetail(selectedDatasetKey);
    });
  });

  body.querySelectorAll(".set-active-btn").forEach((node) => {
    node.addEventListener("click", async () => {
      const key = node.getAttribute("data-dataset-key");
      await onSetActiveDataset(key);
    });
  });

  body.querySelectorAll(".toggle-compare-btn").forEach((node) => {
    node.addEventListener("click", async () => {
      const key = node.getAttribute("data-dataset-key");
      await onToggleCompareDataset(key);
    });
  });

  body.querySelectorAll(".inspect-dataset-btn").forEach((node) => {
    node.addEventListener("click", async () => {
      const key = node.getAttribute("data-dataset-key");
      selectedDatasetKey = key;
      const radio = Array.from(body.querySelectorAll("input[name='datasetPick']")).find((item) => item.value === key);
      if (radio) radio.checked = true;
      updateAnalysisActionState();
      await loadDatasetDetail(key);
    });
  });

  renderAnalysisPages();
}

function renderResults(results) {
  const body = el("resultsBody");
  currentResults = results;
  const isTr = currentLanguage === "tr";
  if (!results.length) {
    body.innerHTML = `<tr><td colspan='10'>${isTr ? "Kayıtlı sonuç yok." : "No results saved."}</td></tr>`;
    selectedResultId = null;
    currentResultDetail = null;
    setText("resultDetailInfo", isTr ? "Sonuç detayı seçilmedi." : "No result detail selected.");
    setHtml("resultDetailPanel", isTr ? "İşleme, provenance ve doğrulama detayları için kayıtlı bir sonuç seç." : "Select a saved result to inspect processing, provenance, and validation.");
    setDiagnostic("result", {});
    renderAnalysisPages();
    return;
  }

  if (!selectedResultId || !results.some((item) => item.id === selectedResultId)) {
    selectedResultId = results[0].id;
  }
  if (currentResultDetail && currentResultDetail.result && !results.some((item) => item.id === currentResultDetail.result.id)) {
    currentResultDetail = null;
  }

  body.innerHTML = results
    .map(
      (item) => `
      <tr>
        <td>${item.id === selectedResultId ? (isTr ? "Seçili" : "Selected") : ""}</td>
        <td><button class="inspect-result-btn" data-result-id="${escapeHtml(item.id)}">${isTr ? "İncele" : "View"}</button></td>
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

  body.querySelectorAll(".inspect-result-btn").forEach((node) => {
    node.addEventListener("click", async () => {
      const resultId = node.getAttribute("data-result-id");
      selectedResultId = resultId;
      renderResults(currentResults);
      await loadResultDetail(resultId);
      const context = await refreshWorkspaceContext();
      if (!context) {
        setText(
          "homeProjectInfo",
          currentLanguage === "tr"
            ? `Aktif veri seti: ${currentActiveDatasetKey || t("common.none")} | Seçili sonuç: ${selectedResultId || t("common.none")}`
            : `Active dataset: ${currentActiveDatasetKey || "none"} | Selected result: ${selectedResultId || "none"}`
        );
      }
      renderAnalysisPages();
    });
  });
  renderAnalysisPages();
}

function renderExportableResults(results) {
  const body = el("exportResultsBody");
  exportableResults = results || [];
  const isTr = currentLanguage === "tr";
  if (!exportableResults.length) {
    body.innerHTML = `<tr><td colspan='6'>${isTr ? "Export için uygun kayıtlı sonuç yok. Önce analiz çalıştırıp sonuç kaydedin." : "No saved results are currently available for export. Run analysis and save results first."}</td></tr>`;
    setText("exportSelectionHint", isTr ? "Henüz exporta uygun kayıtlı sonuç yok. Önce en az bir kararlı sonuç üret." : "No exportable saved results yet. Generate at least one stable result first.");
    setDisabled("exportCsvBtn", true);
    setDisabled("exportDocxBtn", true);
    return;
  }

  body.innerHTML = exportableResults
    .map(
      (item) => `
      <tr>
        <td><input type="checkbox" class="export-result-check" value="${escapeHtml(item.id)}" checked></td>
        <td>${escapeHtml(item.id)}</td>
        <td>${escapeHtml(item.analysis_type)}</td>
        <td>${escapeHtml(item.status)}</td>
        <td>${escapeHtml(item.validation_status)}</td>
        <td>${escapeHtml(item.saved_at_utc)}</td>
      </tr>
    `
    )
    .join("");
  setText(
    "exportSelectionHint",
    isTr
      ? `Dahil edilecek kayıtlı sonuçları seçin. Şu anda ${exportableResults.length} sonuç export/rapor üretimine uygun.`
      : `Select the saved results to include. ${exportableResults.length} result(s) currently eligible for export/report generation.`
  );
  setDisabled("exportCsvBtn", false);
  setDisabled("exportDocxBtn", false);
}

function renderBatchSummaryRows(rows) {
  const body = el("batchSummaryBody");
  const items = rows || [];
  if (!items.length) {
    body.innerHTML = `<tr><td colspan='5'>${currentLanguage === "tr" ? "Batch özet satırı yok." : "No batch summary rows."}</td></tr>`;
    return;
  }
  body.innerHTML = items
    .map((row) => {
      return `
      <tr>
        <td>${escapeHtml(row.dataset_key)}</td>
        <td>${escapeHtml(row.execution_status)}</td>
        <td>${escapeHtml(row.validation_status)}</td>
        <td>${escapeHtml(row.result_id)}</td>
        <td>${escapeHtml(row.failure_reason)}</td>
      </tr>
    `;
    })
    .join("");
}

function renderBatchWorkspaceState(compareWorkspace) {
  const payload = compareWorkspace || {};
  const feedback = payload.batch_last_feedback || {};
  const selectedCount = (payload.selected_datasets || []).length;
  const canRun = Boolean(activeProjectId) && selectedCount > 0;
  setDisabled("runBatchBtn", !canRun);
  if (!selectedCount) {
    setText("batchInfo", currentLanguage === "tr" ? "Batch için seçili karşılaştırma veri seti yok." : "No compare-selected datasets available for batch.");
  } else if (payload.batch_run_id) {
    setText(
      "batchInfo",
      currentLanguage === "tr"
        ? `Son batch ${payload.batch_run_id}: kaydedilen=${feedback.saved || 0}, bloklanan=${feedback.blocked || 0}, başarısız=${feedback.failed || 0}`
        : `Last batch ${payload.batch_run_id}: saved=${feedback.saved || 0}, blocked=${feedback.blocked || 0}, failed=${feedback.failed || 0}`
    );
  } else {
    setText(
      "batchInfo",
      currentLanguage === "tr"
        ? `${selectedCount} seçili koşu için batch çalıştırmaya hazır.`
        : `Ready for batch run on ${selectedCount} compare-selected dataset(s).`
    );
  }
  setHtml(
    "compareBatchStatsPanel",
    `
    <div>
      <span class="badge badge-neutral">${currentLanguage === "tr" ? "Seçili koşu" : "Selected datasets"}: ${selectedCount}</span>
      <span class="badge badge-ok">${currentLanguage === "tr" ? "Kaydedilen" : "Saved"}: ${feedback.saved || 0}</span>
      <span class="badge badge-warn">${currentLanguage === "tr" ? "Bloklanan" : "Blocked"}: ${feedback.blocked || 0}</span>
      <span class="badge badge-fail">${currentLanguage === "tr" ? "Başarısız" : "Failed"}: ${feedback.failed || 0}</span>
      <span class="badge badge-neutral">${currentLanguage === "tr" ? "Şablon" : "Template"}: ${escapeHtml(valueOr(payload.batch_template_id, "n/a"))}</span>
      <span class="badge badge-neutral">${currentLanguage === "tr" ? "Çalıştırma ID" : "Run ID"}: ${escapeHtml(valueOr(payload.batch_run_id, currentLanguage === "tr" ? "çalıştırılmadı" : "not run"))}</span>
    </div>
    `
  );
  renderBatchSummaryRows(payload.batch_summary || []);
  setDiagnostic("batch", {
    batch_run_id: payload.batch_run_id,
    batch_template_id: payload.batch_template_id,
    batch_template_label: payload.batch_template_label,
    batch_completed_at: payload.batch_completed_at,
    batch_last_feedback: feedback,
    batch_result_ids: payload.batch_result_ids || [],
    batch_summary: payload.batch_summary || [],
  });
}

async function refreshCompareWorkspace() {
  if (!activeProjectId) {
    setText("compareMeta", currentLanguage === "tr" ? "Karşılaştırma metadata bilgisi henüz yüklenmedi." : "No compare metadata loaded.");
    setHtml("compareSummaryPanel", currentLanguage === "tr" ? "Karşılaştırma alanı özeti burada görünecek." : t("compare.summaryPending"));
    setHtml("compareBatchStatsPanel", "");
    renderCompareSelectionChips([]);
    setDiagnostic("compare", {});
    return;
  }
  try {
    const compare = await window.taDesktop.getCompareWorkspace(activeProjectId);
    compareSelectedDatasetKeys = new Set(compare.compare_workspace.selected_datasets || []);
    el("compareTypeSelect").value = compare.compare_workspace.analysis_type || "DSC";
    el("batchAnalysisTypeSelect").value = compare.compare_workspace.analysis_type || "DSC";
    el("compareNotes").value = compare.compare_workspace.notes || "";
    renderCompareDatasetChecks(compare.compare_workspace.selected_datasets || []);
    renderCompareWorkspaceSummary(compare.compare_workspace);
    setText(
      "compareMeta",
      currentLanguage === "tr"
        ? `Seçili koşu: ${(compare.compare_workspace.selected_datasets || []).length} | Kaydedildi: ${valueOr(compare.compare_workspace.saved_at, t("common.na"))}`
        : `Selected datasets: ${(compare.compare_workspace.selected_datasets || []).length} | Saved at: ${valueOr(compare.compare_workspace.saved_at, t("common.na"))}`
    );
    if (currentDatasets.length) {
      renderDatasets(currentDatasets);
    }
    renderBatchWorkspaceState(compare.compare_workspace);
    setDiagnostic("compare", compare.compare_workspace);
  } catch (error) {
    setText("compareMeta", currentLanguage === "tr" ? "Karşılaştırma metadata bilgisi okunamadı." : "Compare metadata unavailable.");
    setHtml(
      "compareSummaryPanel",
      `<p class='fail'>${currentLanguage === "tr" ? "Karşılaştırma alanı okunamadı" : "Compare workspace read failed"}: ${escapeHtml(String(error))}</p>`
    );
    setHtml("compareBatchStatsPanel", "");
    renderCompareSelectionChips([]);
    setText("batchInfo", currentLanguage === "tr" ? "Batch özeti alınamadı." : "Batch summary unavailable.");
    renderBatchSummaryRows([]);
    setDiagnostic("compare", { error: String(error) });
  }
}

async function refreshWorkspaceContext() {
  if (!activeProjectId) {
    setText("homeProjectInfo", currentLanguage === "tr" ? "Çalışma alanı bağlamı yüklenmedi." : "No workspace context loaded.");
    setDiagnostic("workspace", {});
    return null;
  }
  try {
    const context = await window.taDesktop.getWorkspaceContext(activeProjectId);
    applyWorkspaceContext(context);
    el("compareTypeSelect").value = context.compare_workspace.analysis_type || "DSC";
    el("batchAnalysisTypeSelect").value = context.compare_workspace.analysis_type || "DSC";
    el("compareNotes").value = context.compare_workspace.notes || "";
    renderCompareDatasetChecks(context.compare_workspace.selected_datasets || []);
    setText(
      "compareMeta",
      currentLanguage === "tr"
        ? `Seçili koşu: ${(context.compare_workspace.selected_datasets || []).length} | Kaydedildi: ${valueOr(context.compare_workspace.saved_at, t("common.na"))}`
        : `Selected datasets: ${(context.compare_workspace.selected_datasets || []).length} | Saved at: ${valueOr(context.compare_workspace.saved_at, t("common.na"))}`
    );
    renderCompareWorkspaceSummary(context.compare_workspace);
    renderBatchWorkspaceState(context.compare_workspace);
    setDiagnostic("compare", context.compare_workspace);
    if (currentDatasets.length) {
      renderDatasets(currentDatasets);
    }
    return context;
  } catch (error) {
    setText(
      "homeProjectInfo",
      currentLanguage === "tr" ? `Çalışma alanı bağlamı başarısız: ${error}` : `Workspace context failed: ${error}`
    );
    setDiagnostic("workspace", { error: String(error) });
    return null;
  }
}

async function onSetActiveDataset(datasetKey) {
  if (!activeProjectId || !datasetKey) return;
  try {
    const response = await window.taDesktop.setActiveDataset(activeProjectId, datasetKey);
    currentActiveDatasetKey = response.active_dataset_key;
    appendLog(currentLanguage === "tr" ? `Aktif veri seti güncellendi: ${response.active_dataset_key}.` : `Active dataset set to ${response.active_dataset_key}.`);
    await refreshWorkspaceViews();
  } catch (error) {
    appendLog(currentLanguage === "tr" ? `Aktif veri seti güncellenemedi: ${error}` : `Set active dataset failed: ${error}`);
  }
}

async function updateCompareSelection(operation, datasetKeys) {
  if (!activeProjectId) return;
  const response = await window.taDesktop.updateCompareSelection(activeProjectId, operation, datasetKeys);
  compareSelectedDatasetKeys = new Set(response.compare_workspace.selected_datasets || []);
  el("compareTypeSelect").value = response.compare_workspace.analysis_type || "DSC";
  el("compareNotes").value = response.compare_workspace.notes || "";
  renderCompareDatasetChecks(response.compare_workspace.selected_datasets || []);
  setText(
    "compareMeta",
    currentLanguage === "tr"
      ? `Seçili koşu: ${(response.compare_workspace.selected_datasets || []).length} | Kaydedildi: ${valueOr(response.compare_workspace.saved_at, t("common.na"))}`
      : `Selected datasets: ${(response.compare_workspace.selected_datasets || []).length} | Saved at: ${valueOr(response.compare_workspace.saved_at, t("common.na"))}`
  );
  renderCompareWorkspaceSummary(response.compare_workspace);
  setDiagnostic("compare", response.compare_workspace);
  renderBatchWorkspaceState(response.compare_workspace);
  renderDatasets(currentDatasets);
  await refreshWorkspaceContext();
}

async function onToggleCompareDataset(datasetKey) {
  if (!datasetKey) return;
  const operation = compareSelectedDatasetKeys.has(datasetKey) ? "remove" : "add";
  try {
    await updateCompareSelection(operation, [datasetKey]);
    appendLog(currentLanguage === "tr" ? `Karşılaştırma seçimi ${operation === "add" ? "eklendi" : "çıkarıldı"}: ${datasetKey}` : `Compare selection ${operation}: ${datasetKey}`);
  } catch (error) {
    appendLog(currentLanguage === "tr" ? `Karşılaştırma seçimi güncellenemedi: ${error}` : `Compare selection update failed: ${error}`);
  }
}

async function refreshExportPreparation() {
  if (!activeProjectId) {
    const isTr = currentLanguage === "tr";
    setText("exportPrepInfo", isTr ? "Export hazırlığı için çalışma alanı aç veya oluştur." : "Open or create a workspace to prepare export context.");
    setText("exportSelectionHint", isTr ? "Export paketine eklenecek kayıtlı sonuçları seç." : "Select the saved results to include in your export package.");
    setHtml("exportPrepPanel", isTr ? "Veri yükleme veya analiz sonrası export bağlamını yenile." : "Refresh export context after loading or analyzing datasets.");
    setHtml("exportActionPanel", "");
    renderExportableResults([]);
    setDiagnostic("export", {});
    return;
  }

  try {
    const isTr = currentLanguage === "tr";
    const prep = await window.taDesktop.getExportPreparation(activeProjectId);
    renderExportableResults(prep.exportable_results || []);
    setText(
      "exportPrepInfo",
      isTr
        ? `Export bağlamı hazır: ${(prep.exportable_results || []).length} exporta uygun sonuç, ${(prep.skipped_record_issues || []).length} atlanan geçersiz kayıt sorunu.`
        : `Export context ready: ${(prep.exportable_results || []).length} exportable result(s), ${(prep.skipped_record_issues || []).length} skipped invalid record issue(s).`
    );
    setHtml(
      "exportPrepPanel",
      `
      ${keyGrid([
        { label: isTr ? "Desteklenen Çıktılar" : "Supported Outputs", value: valueOr((prep.supported_outputs || []).join(", "), t("common.none")) },
        { label: isTr ? "Exporta Uygun Sonuçlar" : "Exportable Results", value: String((prep.exportable_results || []).length) },
        { label: isTr ? "Atlanan Geçersiz Kayıt" : "Skipped Invalid Records", value: String((prep.skipped_record_issues || []).length) },
        { label: isTr ? "Karşılaştırma Analizi" : "Compare Analysis", value: valueOr(prep.compare_workspace && prep.compare_workspace.analysis_type, "N/A") },
      ])}
      ${renderIssueList(isTr ? "Atlanan kayıt sorunları" : "Skipped record issues", prep.skipped_record_issues || [])}
      `
    );
    setDiagnostic("export", prep);
  } catch (error) {
    setText("exportPrepInfo", currentLanguage === "tr" ? `Export hazırlığı başarısız: ${error}` : `Export preparation failed: ${error}`);
    setHtml("exportPrepPanel", currentLanguage === "tr" ? "<p class='fail'>Export hazırlığı kullanılamıyor.</p>" : "<p class='fail'>Export preparation unavailable.</p>");
    renderExportableResults([]);
    setDiagnostic("export", { error: String(error) });
  }
}

async function refreshStatus() {
  const bootstrap = window.taDesktop.getBackendBootstrap();
  setHtml(
    "diagBootstrap",
    `Backend URL: <code>${escapeHtml(bootstrap.backendUrl || t("common.na"))}</code> | Token: <strong>${bootstrap.hasToken ? (currentLanguage === "tr" ? "var" : "present") : (currentLanguage === "tr" ? "yok" : "missing")}</strong>`
  );

  try {
    const health = await window.taDesktop.checkHealth();
    setText("statusHealth", t("status.health", { status: health.status }));
    setHtml("diagHealth", `${currentLanguage === "tr" ? "Sağlık" : "Health"}: <span class="ok">${escapeHtml(health.status)}</span> (API ${escapeHtml(health.api_version)})`);
  } catch (error) {
    setText("statusHealth", t("status.healthFailed"));
    setHtml("diagHealth", `${currentLanguage === "tr" ? "Sağlık" : "Health"}: <span class="fail">${currentLanguage === "tr" ? "başarısız" : "failed"}</span> (${escapeHtml(String(error))})`);
  }

  try {
    const version = await window.taDesktop.getVersion();
    setText("statusVersion", t("status.version", { version: version.app_version }));
    setText("licenseVersionValue", valueOr(version.app_version, t("common.unknown")));
    setText("licenseProjectExtValue", valueOr(version.project_extension, t("common.unknown")));
    setHtml("diagVersion", `${currentLanguage === "tr" ? "ThermoAnalyzer uygulama sürümü" : "ThermoAnalyzer app version"}: <strong>${escapeHtml(version.app_version)}</strong> | ${currentLanguage === "tr" ? "Proje uzantısı" : "Project extension"}: <code>${escapeHtml(version.project_extension)}</code>`);
  } catch (error) {
    setText("statusVersion", t("status.versionFailed"));
    setText("licenseVersionValue", t("common.unknown"));
    setText("licenseProjectExtValue", t("common.unknown"));
    setHtml("diagVersion", `${currentLanguage === "tr" ? "Sürüm çağrısı başarısız" : "Version call failed"}: <span class="fail">${escapeHtml(String(error))}</span>`);
  }
}

async function refreshWorkspaceViews() {
  if (!activeProjectId) {
    currentActiveDatasetKey = null;
    compareSelectedDatasetKeys = new Set();
    currentDatasetDetail = null;
    currentResultDetail = null;
    lastAnalysisRuns.DSC = null;
    lastAnalysisRuns.DTA = null;
    lastAnalysisRuns.TGA = null;
    currentResults = [];
    selectedDatasetKey = null;
    selectedResultId = null;
    setText("homeProjectInfo", currentLanguage === "tr" ? "Aktif çalışma alanı yok." : "No workspace active.");
    setText("homeDatasetCountValue", "0");
    setText("homeResultCountValue", "0");
    setText("homeActiveDatasetValue", t("common.none"));
    setText("homeLatestResultValue", t("common.none"));
    setText("homeCompareCountValue", "0");
    setText("homeNextStepValue", t("home.nextCreate"));
    setText("homeWorkspaceSavedAtValue", t("common.na"));
    setText("homeStepWorkspaceStatus", t("home.stepWorkspacePending"));
    setText("homeStepImportStatus", t("home.stepImportPending"));
    setText("homeStepCompareStatus", t("home.stepComparePending"));
    setText("homeStepRunStatus", t("home.stepRunPending"));
    setText("projectViewInfo", currentLanguage === "tr" ? "Aktif çalışma alanı yok." : "No workspace active.");
    setText("projectDatasetCountValue", "0");
    setText("projectResultCountValue", "0");
    setText("projectHistoryCountValue", "0");
    setText("projectFigureCountValue", "0");
    setText(
      "projectConfidenceMessage",
      currentLanguage === "tr"
        ? "Proje arşivi bağlamı için çalışma alanı aç veya oluştur."
        : "Open or create a workspace to establish project archive context."
    );
    renderDatasets([]);
    renderResults([]);
    setText("compareMeta", currentLanguage === "tr" ? "Karşılaştırma metadata bilgisi henüz yüklenmedi." : "No compare metadata loaded.");
    setHtml("compareSummaryPanel", currentLanguage === "tr" ? "Karşılaştırma alanı özeti burada görünecek." : t("compare.summaryPending"));
    setHtml("compareSelectedDatasetsPanel", `<span class='dataset-chip'>${escapeHtml(t("common.noCompareSelected"))}</span>`);
    setHtml("compareBatchStatsPanel", "");
    setText("batchInfo", currentLanguage === "tr" ? "Henüz batch çalıştırılmadı." : "No batch run executed.");
    renderBatchSummaryRows([]);
    setText("exportPrepInfo", currentLanguage === "tr" ? "Export hazırlığı için çalışma alanı aç veya oluştur." : "Open or create a workspace to prepare export context.");
    setText("exportSelectionHint", currentLanguage === "tr" ? "Export paketine eklenecek kayıtlı sonuçları seç." : "Select the saved results to include in your export package.");
    setHtml("exportPrepPanel", currentLanguage === "tr" ? "Veri yükleme veya analiz sonrası export bağlamını yenile." : "Refresh export context after loading or analyzing datasets.");
    setHtml("exportActionPanel", "");
    setHtml("homeImportFeedbackPanel", currentLanguage === "tr" ? "Henüz bir içe aktarma işlemi yapılmadı." : "No import action yet.");
    setHtml("homeImportQualityPanel", currentLanguage === "tr" ? "Import güveni ve review rehberi, veri seti incelendikten sonra burada görünür." : "Import confidence and review guidance will appear here after dataset inspection.");
    setHtml("homeSelectedDatasetPanel", currentLanguage === "tr" ? "Aktif veri seti seçilmedi." : "No active dataset selected.");
    setHtml("dscActiveDatasetContextPanel", currentLanguage === "tr" ? "DSC bağlamını başlatmak için Veri Al sayfasından bir veri seti seç." : "Select a dataset from Home / Import to begin DSC context.");
    setHtml("dscMethodContextPanel", currentLanguage === "tr" ? "DSC işlem bağlamı burada görünecek." : "DSC processing context will appear here.");
    setHtml("dscValidationPanel", currentLanguage === "tr" ? "Doğrulama özeti, veri seti incelendikten sonra görünür." : "Validation summary will appear after dataset inspection.");
    setHtml("dscTemplateContextPanel", currentLanguage === "tr" ? "İş akışı şablon bağlamı burada görünecek." : "Workflow template context will appear here.");
    setHtml("dscResultSummaryPanel", currentLanguage === "tr" ? "Henüz DSC sonuç bağlamı yok." : "No DSC result context yet.");
    setText("dscAnalysisInfo", currentLanguage === "tr" ? "Henüz DSC analizi çalıştırılmadı." : "No DSC analysis executed yet.");
    setHtml("dtaActiveDatasetContextPanel", currentLanguage === "tr" ? "DTA bağlamını başlatmak için Veri Al sayfasından bir veri seti seç." : "Select a dataset from Home / Import to begin DTA context.");
    setHtml("dtaMethodContextPanel", currentLanguage === "tr" ? "DTA işlem bağlamı burada görünecek." : "DTA processing context will appear here.");
    setHtml("dtaValidationPanel", currentLanguage === "tr" ? "Doğrulama özeti, veri seti incelendikten sonra görünür." : "Validation summary will appear after dataset inspection.");
    setHtml("dtaTemplateContextPanel", currentLanguage === "tr" ? "İş akışı şablon bağlamı burada görünecek." : "Workflow template context will appear here.");
    setHtml("dtaResultSummaryPanel", currentLanguage === "tr" ? "Henüz DTA sonuç bağlamı yok." : "No DTA result context yet.");
    setText("dtaAnalysisInfo", currentLanguage === "tr" ? "Henüz DTA analizi çalıştırılmadı." : "No DTA analysis executed yet.");
    setHtml("tgaActiveDatasetContextPanel", currentLanguage === "tr" ? "TGA bağlamını başlatmak için Veri Al sayfasından bir veri seti seç." : "Select a dataset from Home / Import to begin TGA context.");
    setHtml("tgaUnitContextPanel", currentLanguage === "tr" ? "TGA birim ve import-review bağlamı burada görünecek." : "TGA unit and import-review context will appear here.");
    setHtml("tgaValidationPanel", currentLanguage === "tr" ? "Doğrulama özeti, veri seti incelendikten sonra görünür." : "Validation summary will appear after dataset inspection.");
    setHtml("tgaTemplateContextPanel", currentLanguage === "tr" ? "İş akışı şablon bağlamı burada görünecek." : "Workflow template context will appear here.");
    setHtml("tgaResultSummaryPanel", currentLanguage === "tr" ? "Henüz TGA sonuç bağlamı yok." : "No TGA result context yet.");
    setText("tgaAnalysisInfo", currentLanguage === "tr" ? "Henüz TGA analizi çalıştırılmadı." : "No TGA analysis executed yet.");
    setHtml("datasetDetailPanel", currentLanguage === "tr" ? "Metadata, doğrulama ve önizleme satırları için bir veri seti seç." : "Select a dataset to inspect metadata, validation, and preview rows.");
    setHtml("resultDetailPanel", currentLanguage === "tr" ? "İşleme, provenance ve doğrulama detayları için kayıtlı bir sonuç seç." : "Select a saved result to inspect processing, provenance, and validation.");
    renderExportableResults([]);
    setDiagnostic("workspace", {});
    setDiagnostic("compare", {});
    setDiagnostic("batch", {});
    setDiagnostic("export", {});
    setDiagnostic("dataset", {});
    setDiagnostic("result", {});
    setWorkflowEnabled(false);
    updateStatusWorkspace();
    return;
  }

  const context = await window.taDesktop.getWorkspaceContext(activeProjectId);
  const datasets = await window.taDesktop.listDatasets(activeProjectId);
  const results = await window.taDesktop.listResults(activeProjectId);
  applyWorkspaceContext(context);
  compareSelectedDatasetKeys = new Set((context.compare_workspace && context.compare_workspace.selected_datasets) || []);
  renderDatasets(datasets.datasets || []);
  renderResults(results.results || []);
  setWorkflowEnabled(true);

  if (selectedDatasetKey) {
    await loadDatasetDetail(selectedDatasetKey);
  }
  if (selectedResultId) {
    await loadResultDetail(selectedResultId);
  }
  el("compareTypeSelect").value = context.compare_workspace.analysis_type || "DSC";
  el("batchAnalysisTypeSelect").value = context.compare_workspace.analysis_type || "DSC";
  el("compareNotes").value = context.compare_workspace.notes || "";
  renderCompareDatasetChecks(context.compare_workspace.selected_datasets || []);
  setText(
    "compareMeta",
    currentLanguage === "tr"
      ? `Seçili koşu: ${(context.compare_workspace.selected_datasets || []).length} | Kaydedildi: ${valueOr(context.compare_workspace.saved_at, t("common.na"))}`
      : `Selected datasets: ${(context.compare_workspace.selected_datasets || []).length} | Saved at: ${valueOr(context.compare_workspace.saved_at, t("common.na"))}`
  );
  renderCompareWorkspaceSummary(context.compare_workspace);
  setDiagnostic("compare", context.compare_workspace);
  renderBatchWorkspaceState(context.compare_workspace);
  updateAnalysisActionState();
  renderAnalysisPages();
  await refreshExportPreparation();
}

async function onNewWorkspace() {
  try {
    const created = await window.taDesktop.createWorkspace();
    activeProjectId = created.project_id;
    selectedDatasetKey = null;
    selectedResultId = null;
    activeProjectDefaultName = "thermoanalyzer_project.thermozip";
    await refreshWorkspaceViews();
    appendLog(currentLanguage === "tr" ? `Çalışma alanı oluşturuldu: ${activeProjectId}.` : `Created workspace ${activeProjectId}.`);
  } catch (error) {
    appendLog(currentLanguage === "tr" ? `Çalışma alanı oluşturulamadı: ${error}` : `Create workspace failed: ${error}`);
  }
}

async function onOpenProject() {
  try {
    const picked = await window.taDesktop.pickProjectArchive();
    if (!picked || picked.canceled) {
      appendLog(currentLanguage === "tr" ? "Proje açma işlemi iptal edildi." : "Open project canceled.");
      return;
    }
    const loaded = await window.taDesktop.loadProjectArchive(picked.archiveBase64);
    activeProjectId = loaded.project_id;
    selectedDatasetKey = null;
    selectedResultId = null;
    activeProjectDefaultName = `thermoanalyzer_project${loaded.project_extension}`;
    await refreshWorkspaceViews();
    appendLog(currentLanguage === "tr" ? `Proje yüklendi: ${picked.filePath}.` : `Loaded project from ${picked.filePath}.`);
  } catch (error) {
    appendLog(currentLanguage === "tr" ? `Proje açılamadı: ${error}` : `Open project failed: ${error}`);
  }
}

async function onSaveProject() {
  if (!activeProjectId) {
    appendLog(currentLanguage === "tr" ? "Kaydetme atlandı: aktif çalışma alanı yok." : "Save skipped: no workspace active.");
    return;
  }
  try {
    const archive = await window.taDesktop.saveProjectArchive(activeProjectId);
    const persisted = await window.taDesktop.persistProjectArchive(
      activeProjectDefaultName || archive.file_name,
      archive.archive_base64
    );
    if (!persisted || persisted.canceled) {
      appendLog(currentLanguage === "tr" ? "Çalışma alanı kaydetme iptal edildi." : "Save workspace canceled.");
      return;
    }
    appendLog(currentLanguage === "tr" ? `Çalışma alanı arşivi kaydedildi: ${persisted.filePath}.` : `Saved workspace archive to ${persisted.filePath}.`);
  } catch (error) {
    appendLog(currentLanguage === "tr" ? `Çalışma alanı kaydedilemedi: ${error}` : `Save workspace failed: ${error}`);
  }
}

async function onImportDataset() {
  if (!activeProjectId) {
    appendLog(currentLanguage === "tr" ? "İçe aktarma atlandı: aktif çalışma alanı yok." : "Import skipped: no workspace active.");
    return;
  }
  try {
    const picked = await window.taDesktop.pickDatasetFile();
    if (!picked || picked.canceled) {
      appendLog(currentLanguage === "tr" ? "Veri seti içe aktarma iptal edildi." : "Import dataset canceled.");
      return;
    }
    const dataType = el("datasetTypeSelect").value;
    const imported = await window.taDesktop.importDataset(
      activeProjectId,
      picked.fileName,
      picked.fileBase64,
      dataType
    );
    setHtml(
      "homeImportFeedbackPanel",
      `
      <div>
        <span class="${toneBadgeClass(imported.validation.status)}">${currentLanguage === "tr" ? "Doğrulama" : "Validation"}: ${escapeHtml(valueOr(imported.validation.status, t("common.unknown")))}</span>
        <span class="badge badge-neutral">${currentLanguage === "tr" ? "Uyarılar" : "Warnings"}: ${escapeHtml(valueOr(imported.validation.warning_count, "0"))}</span>
        <span class="badge badge-neutral">${currentLanguage === "tr" ? "Sorunlar" : "Issues"}: ${escapeHtml(valueOr(imported.validation.issue_count, "0"))}</span>
      </div>
      <p class="small">${currentLanguage === "tr"
        ? `İçe aktarıldı: <strong>${escapeHtml(imported.dataset.key)}</strong> (${escapeHtml(imported.dataset.data_type)}) - <strong>${escapeHtml(picked.fileName)}</strong>.`
        : `Imported <strong>${escapeHtml(imported.dataset.key)}</strong> (${escapeHtml(imported.dataset.data_type)}) from <strong>${escapeHtml(picked.fileName)}</strong>.`}</p>
      `
    );
    selectedDatasetKey = imported.dataset.key;
    await refreshWorkspaceViews();
    appendLog(
      currentLanguage === "tr"
        ? `Veri seti içe aktarıldı ${imported.dataset.key} (${imported.dataset.data_type}) | ${picked.filePath} | doğrulama=${imported.validation.status}`
        : `Imported dataset ${imported.dataset.key} (${imported.dataset.data_type}) from ${picked.filePath}. Validation=${imported.validation.status}`
    );
  } catch (error) {
    setHtml(
      "homeImportFeedbackPanel",
      currentLanguage === "tr"
        ? `<span class="badge badge-fail">İçe aktarma başarısız</span><p class="small">${escapeHtml(String(error))}</p>`
        : `<span class="badge badge-fail">Import failed</span><p class="small">${escapeHtml(String(error))}</p>`
    );
    appendLog(currentLanguage === "tr" ? `Veri seti içe aktarılamadı: ${error}` : `Import dataset failed: ${error}`);
  }
}

async function onRunAnalysis(analysisType) {
  if (!activeProjectId || !selectedDatasetKey) {
    appendLog(currentLanguage === "tr" ? `${analysisType} çalıştırma atlandı: önce bir veri seti seçin.` : `Run ${analysisType} skipped: select a dataset first.`);
    return;
  }
  const infoId = {
    DSC: "dscAnalysisInfo",
    DTA: "dtaAnalysisInfo",
    TGA: "tgaAnalysisInfo",
  }[analysisType] || "dscAnalysisInfo";
  try {
    const run = await window.taDesktop.runAnalysis(activeProjectId, selectedDatasetKey, analysisType);
    lastAnalysisRuns[analysisType] = {
      ...run,
      dataset_key: selectedDatasetKey,
    };
    setText(
      infoId,
      currentLanguage === "tr"
        ? `${analysisType} ${selectedDatasetKey}: ${run.execution_status}${run.result_id ? ` (${run.result_id})` : ""}`
        : `${analysisType} on ${selectedDatasetKey}: ${run.execution_status}${run.result_id ? ` (${run.result_id})` : ""}`
    );
    if (run.result_id) selectedResultId = run.result_id;
    await refreshWorkspaceViews();
    appendLog(
      currentLanguage === "tr"
        ? `${analysisType} ${selectedDatasetKey}: ${run.execution_status}${run.failure_reason ? ` - ${run.failure_reason}` : ""}`
        : `${analysisType} on ${selectedDatasetKey}: ${run.execution_status}${run.failure_reason ? ` - ${run.failure_reason}` : ""}`
    );
  } catch (error) {
    lastAnalysisRuns[analysisType] = {
      execution_status: "failed",
      failure_reason: String(error),
      result_id: null,
      dataset_key: selectedDatasetKey,
    };
    setText(infoId, currentLanguage === "tr" ? `${analysisType} başarısız: ${error}` : `${analysisType} failed: ${error}`);
    renderAnalysisPages();
    appendLog(currentLanguage === "tr" ? `${analysisType} çalıştırma başarısız: ${error}` : `Run ${analysisType} failed: ${error}`);
  }
}

async function onSaveCompareSelection() {
  if (!activeProjectId) return;
  try {
    const payload = {
      analysis_type: el("compareTypeSelect").value,
      selected_datasets: collectCompareSelectedDatasets(),
      notes: el("compareNotes").value,
    };
    const response = await window.taDesktop.updateCompareWorkspace(activeProjectId, payload);
    compareSelectedDatasetKeys = new Set(response.compare_workspace.selected_datasets || []);
    setText(
      "compareMeta",
      currentLanguage === "tr"
        ? `Seçili koşu: ${(response.compare_workspace.selected_datasets || []).length} | Kaydedildi: ${valueOr(response.compare_workspace.saved_at, t("common.na"))}`
        : `Selected datasets: ${(response.compare_workspace.selected_datasets || []).length} | Saved at: ${valueOr(response.compare_workspace.saved_at, t("common.na"))}`
    );
    renderCompareWorkspaceSummary(response.compare_workspace);
    setDiagnostic("compare", response.compare_workspace);
    renderBatchWorkspaceState(response.compare_workspace);
    renderDatasets(currentDatasets);
    await refreshWorkspaceContext();
    appendLog(
      currentLanguage === "tr"
        ? `Karşılaştırma alanı kaydedildi (${response.compare_workspace.analysis_type}), ${response.compare_workspace.selected_datasets.length} veri seti.`
        : `Saved compare workspace (${response.compare_workspace.analysis_type}) with ${response.compare_workspace.selected_datasets.length} dataset(s).`
    );
  } catch (error) {
    appendLog(currentLanguage === "tr" ? `Karşılaştırma alanı kaydedilemedi: ${error}` : `Save compare workspace failed: ${error}`);
  }
}

async function onAddSelectedToCompare() {
  if (!activeProjectId || !selectedDatasetKey) {
    appendLog(currentLanguage === "tr" ? "Karşılaştırmaya ekleme atlandı: önce veri seti seçin." : "Add to compare skipped: select a dataset first.");
    return;
  }
  try {
    await updateCompareSelection("add", [selectedDatasetKey]);
    appendLog(currentLanguage === "tr" ? `Karşılaştırmaya eklendi: ${selectedDatasetKey}` : `Added to compare: ${selectedDatasetKey}`);
  } catch (error) {
    appendLog(currentLanguage === "tr" ? `Karşılaştırmaya ekleme başarısız: ${error}` : `Add to compare failed: ${error}`);
  }
}

async function onRemoveSelectedFromCompare() {
  if (!activeProjectId || !selectedDatasetKey) {
    appendLog(currentLanguage === "tr" ? "Karşılaştırmadan çıkarma atlandı: önce veri seti seçin." : "Remove from compare skipped: select a dataset first.");
    return;
  }
  try {
    await updateCompareSelection("remove", [selectedDatasetKey]);
    appendLog(currentLanguage === "tr" ? `Karşılaştırmadan çıkarıldı: ${selectedDatasetKey}` : `Removed from compare: ${selectedDatasetKey}`);
  } catch (error) {
    appendLog(currentLanguage === "tr" ? `Karşılaştırmadan çıkarma başarısız: ${error}` : `Remove from compare failed: ${error}`);
  }
}

async function onClearCompareSelection() {
  if (!activeProjectId) return;
  try {
    await updateCompareSelection("clear", []);
    appendLog(currentLanguage === "tr" ? "Karşılaştırma seçimleri temizlendi." : "Cleared compare selected datasets.");
  } catch (error) {
    appendLog(currentLanguage === "tr" ? `Karşılaştırma seçimi temizlenemedi: ${error}` : `Clear compare selection failed: ${error}`);
  }
}

function onBatchAnalysisTypeChanged() {
  const analysisType = el("batchAnalysisTypeSelect").value;
  const templateInput = el("batchTemplateIdInput");
  if (
    !templateInput.value
    || templateInput.value === "dsc.general"
    || templateInput.value === "dta.general"
    || templateInput.value === "tga.general"
    || templateInput.value === "ftir.general"
    || templateInput.value === "raman.general"
  ) {
    templateInput.value = analysisType === "TGA"
      ? "tga.general"
      : analysisType === "DTA"
      ? "dta.general"
      : analysisType === "FTIR"
      ? "ftir.general"
      : analysisType === "RAMAN"
      ? "raman.general"
      : "dsc.general";
  }
}

async function onRunBatch() {
  if (!activeProjectId) return;
  try {
    const analysisType = el("batchAnalysisTypeSelect").value;
    const workflowTemplateId = (el("batchTemplateIdInput").value || "").trim();
    const response = await window.taDesktop.runBatch(activeProjectId, {
      analysis_type: analysisType,
      workflow_template_id: workflowTemplateId || null,
    });
    setText(
      "batchInfo",
      currentLanguage === "tr"
        ? `Batch ${response.batch_run_id}: kaydedilen=${response.outcomes.saved}, bloklanan=${response.outcomes.blocked}, başarısız=${response.outcomes.failed}`
        : `Batch ${response.batch_run_id}: saved=${response.outcomes.saved}, blocked=${response.outcomes.blocked}, failed=${response.outcomes.failed}`
    );
    setDiagnostic("batch", response);
    renderBatchSummaryRows(response.batch_summary || []);
    appendLog(
      currentLanguage === "tr"
        ? `Batch ${response.batch_run_id} tamamlandı (kaydedilen=${response.outcomes.saved}, bloklanan=${response.outcomes.blocked}, başarısız=${response.outcomes.failed}).`
        : `Batch run ${response.batch_run_id} finished (saved=${response.outcomes.saved}, blocked=${response.outcomes.blocked}, failed=${response.outcomes.failed}).`
    );
    await refreshWorkspaceViews();
  } catch (error) {
    appendLog(currentLanguage === "tr" ? `Batch çalıştırma başarısız: ${error}` : `Batch run failed: ${error}`);
  }
}

async function onExportResultsCsv() {
  if (!activeProjectId) return;
  try {
    const selectedResultIds = collectSelectedExportResultIds();
    if (!selectedResultIds.length) {
      setHtml(
        "exportActionPanel",
        currentLanguage === "tr"
          ? "<span class='badge badge-warn'>Sonuç seçilmedi</span><p class='small'>CSV üretmeden önce en az bir kayıtlı sonuç seç.</p>"
          : "<span class='badge badge-warn'>No results selected</span><p class='small'>Select at least one saved result before generating CSV.</p>"
      );
      return;
    }
    const artifact = await window.taDesktop.generateResultsCsv(activeProjectId, selectedResultIds);
    const saved = await window.taDesktop.persistGeneratedFile(artifact.file_name, artifact.artifact_base64);
    setHtml(
      "exportActionPanel",
      `
      <span class="badge badge-ok">${currentLanguage === "tr" ? "CSV çıktı üretildi" : "CSV artifact generated"}</span>
      ${keyGrid([
        { label: currentLanguage === "tr" ? "Çıktı" : "Artifact", value: artifact.file_name },
        { label: currentLanguage === "tr" ? "Dahil Edilen Sonuç" : "Included Results", value: String((artifact.included_result_ids || []).length) },
      ])}
      `
    );
    setDiagnostic("export", { action: "results_csv", artifact });
    if (!saved || saved.canceled) {
      appendLog(currentLanguage === "tr" ? "Sonuç CSV dışa aktarımı iptal edildi." : "Results CSV export canceled.");
      return;
    }
    appendLog(
      currentLanguage === "tr"
        ? `Sonuç CSV dışa aktarıldı: ${saved.filePath} (${artifact.included_result_ids.length} sonuç).`
        : `Results CSV exported to ${saved.filePath} (${artifact.included_result_ids.length} result(s)).`
    );
  } catch (error) {
    appendLog(currentLanguage === "tr" ? `Sonuç CSV dışa aktarımı başarısız: ${error}` : `Results CSV export failed: ${error}`);
  }
}

async function onGenerateDocxReport() {
  if (!activeProjectId) return;
  try {
    const selectedResultIds = collectSelectedExportResultIds();
    if (!selectedResultIds.length) {
      setHtml(
        "exportActionPanel",
        currentLanguage === "tr"
          ? "<span class='badge badge-warn'>Sonuç seçilmedi</span><p class='small'>DOCX üretmeden önce en az bir kayıtlı sonuç seç.</p>"
          : "<span class='badge badge-warn'>No results selected</span><p class='small'>Select at least one saved result before generating DOCX.</p>"
      );
      return;
    }
    const artifact = await window.taDesktop.generateDocxReport(activeProjectId, selectedResultIds);
    const saved = await window.taDesktop.persistGeneratedFile(artifact.file_name, artifact.artifact_base64);
    setHtml(
      "exportActionPanel",
      `
      <span class="badge badge-ok">${currentLanguage === "tr" ? "DOCX çıktı üretildi" : "DOCX artifact generated"}</span>
      ${keyGrid([
        { label: currentLanguage === "tr" ? "Çıktı" : "Artifact", value: artifact.file_name },
        { label: currentLanguage === "tr" ? "Dahil Edilen Sonuç" : "Included Results", value: String((artifact.included_result_ids || []).length) },
      ])}
      `
    );
    setDiagnostic("export", { action: "report_docx", artifact });
    if (!saved || saved.canceled) {
      appendLog(currentLanguage === "tr" ? "DOCX rapor kaydetme iptal edildi." : "DOCX report save canceled.");
      return;
    }
    appendLog(
      currentLanguage === "tr"
        ? `DOCX rapor kaydedildi: ${saved.filePath} (${artifact.included_result_ids.length} sonuç).`
        : `DOCX report saved to ${saved.filePath} (${artifact.included_result_ids.length} result(s)).`
    );
  } catch (error) {
    appendLog(currentLanguage === "tr" ? `DOCX rapor üretimi başarısız: ${error}` : `DOCX report generation failed: ${error}`);
  }
}

document.querySelectorAll(".nav-item[data-view]").forEach((node) => {
  node.addEventListener("click", () => {
    switchView(node.getAttribute("data-view"));
  });
});

el("newWorkspaceBtn").addEventListener("click", onNewWorkspace);
el("openProjectBtn").addEventListener("click", onOpenProject);
el("saveProjectBtn").addEventListener("click", onSaveProject);
el("saveProjectBtnProjectView").addEventListener("click", onSaveProject);
el("refreshWorkspaceContextBtn").addEventListener("click", refreshWorkspaceContext);
el("refreshWorkspaceContextBtnProjectView").addEventListener("click", refreshWorkspaceContext);
el("importDatasetBtn").addEventListener("click", onImportDataset);
el("runDscAnalysisBtn").addEventListener("click", () => onRunAnalysis("DSC"));
el("runDtaAnalysisBtn").addEventListener("click", () => onRunAnalysis("DTA"));
el("runTgaAnalysisBtn").addEventListener("click", () => onRunAnalysis("TGA"));
el("inspectSelectedDatasetBtn").addEventListener("click", async () => {
  if (!selectedDatasetKey) return;
  switchView("home");
  await loadDatasetDetail(selectedDatasetKey);
});
el("inspectSelectedDatasetBtn3").addEventListener("click", async () => {
  if (!selectedDatasetKey) return;
  switchView("home");
  await loadDatasetDetail(selectedDatasetKey);
});
el("inspectSelectedDatasetBtn2").addEventListener("click", async () => {
  if (!selectedDatasetKey) return;
  switchView("home");
  await loadDatasetDetail(selectedDatasetKey);
});
el("refreshCompareBtn").addEventListener("click", refreshCompareWorkspace);
el("saveCompareBtn").addEventListener("click", onSaveCompareSelection);
el("addSelectedToCompareBtn").addEventListener("click", onAddSelectedToCompare);
el("removeSelectedFromCompareBtn").addEventListener("click", onRemoveSelectedFromCompare);
el("clearCompareSelectionBtn").addEventListener("click", onClearCompareSelection);
el("batchAnalysisTypeSelect").addEventListener("change", onBatchAnalysisTypeChanged);
el("runBatchBtn").addEventListener("click", onRunBatch);
el("refreshExportPrepBtn").addEventListener("click", refreshExportPreparation);
el("exportCsvBtn").addEventListener("click", onExportResultsCsv);
el("exportDocxBtn").addEventListener("click", onGenerateDocxReport);
el("langTrBtn").addEventListener("click", () => setLanguage("tr"));
el("langEnBtn").addEventListener("click", () => setLanguage("en"));
el("previewModulesToggle").addEventListener("change", (event) => {
  const previewGroup = el("previewNavGroup");
  if (previewGroup) {
    previewGroup.style.display = event.target.checked ? "block" : "none";
  }
});

const savedLang = window.localStorage.getItem("taDesktopLanguage");
currentLanguage = savedLang === "en" ? "en" : "tr";
applyStaticLanguage();
switchView("home");
setWorkflowEnabled(false);
updateStatusWorkspace();
setText("statusHealth", t("status.healthUnknown"));
setText("statusVersion", t("status.versionUnknown"));
refreshWorkspaceViews();
refreshStatus();
