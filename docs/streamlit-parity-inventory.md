# Streamlit parity / deprecation inventory

> **Status:** Read-only inventory (PR-6). No removal authorised by this document.

- **Inspected revision:** 17ee1017003554768435999821f118e855387f78 (main, PR-5)
- **Inspection date:** 2026-09-05 (Europe/Istanbul)
- **Runtime observed:** Python 3.12.8, Streamlit 1.54.0, Dash 4.4.1, FastAPI 0.134.0, Plotly 6.5.2, Kaleido 1.2.0
- **Roadmap context:** [Phase 0 / PR-6](roadmap.md#phase-0--stabilize-truth-in-progress)

This document implements the PR-6 Phase 0 plan as a source, route, dependency, test, packaging, and documentation inventory. It does not delete, rename, move, disable, or retarget any runtime or packaging asset. A future removal or migration work package must separately approve its scope and satisfy the prerequisites in section 12.

## 1. Executive findings

The current repository contains two application surfaces and several different launch paths:

- app.py declares 15 Streamlit page objects: 13 always-present pages and 2 pages gated by MATERIALSCOPE_ENABLE_PREVIEW_MODULES (kinetics and deconvolution). The plan working note said 16; the count in this inventory is the verified st.Page( count at the inspected revision.
- dash_app registers 11 Dash pages: home, project, export, compare, DSC, TGA, DTA, FTIR, Raman, XRD, and about.
- The four Streamlit routes with no Dash page counterpart are library, license, kinetics, and deconvolution. Backend library and branding endpoints do not by themselves constitute a user-facing Dash page.
- Dash has a broad counterpart for the stable import, project, compare, export, and scientific-analysis workflows. The conservative classifications below mark controls as PARTIAL_PARITY until defaults, option domains, disabled states, persistence semantics, downloads, and browser-rendered behavior are verified together.
- dash_app.i18n, dash_app.layout, and every Dash page module that imports the shared translation helper are blocked when Streamlit is made unavailable: utils/i18n.py imports Streamlit at module import time. A bare import of dash_app.app or dash_app.server is not sufficient evidence that the running Dash shell is Streamlit-independent.
- The Windows installer remains a Streamlit launch path. Its launcher imports streamlit.web.bootstrap, prefers port 8501, creates a user .streamlit directory, and is packaged by the PyInstaller spec. The spec also lists source/document bundle paths that are absent from the tracked main tree.
- There is no tracked .streamlit configuration directory. The requested legacy guide filenames and docs/scout-report.md are also absent from the tracked tree at this revision; local untracked copies exist in this worktree and were not treated as committed product evidence.

The only new artifact from this implementation is this Markdown inventory. Existing untracked planning files (docs/index.html, docs/roadmap.md, and docs/scout-report.md) were preserved.

## 2. Classification rubric

The labels below are evidence labels, not approval to remove anything. A row receives one label only.

| Label | Objective rule used in this inventory |
| --- | --- |
| PARITY_CONFIRMED | A Dash surface is reachable; every user-visible input has the same domain, options, units, and ranges; both surfaces call the same core behavior (directly or through Dash → API → backend → core); outputs and persisted state are materially equivalent; and at least one Dash or shared-core test covers the behavior with only thin wiring left. |
| PARTIAL_PARITY | A counterpart exists, but at least one input, option, default, persistence behavior, output, gating rule, or browser-level contract differs or is not yet proven. The row's Delta names the difference or the missing evidence. |
| NO_DASH_EQUIVALENT | No user-facing Dash page or component counterpart was found. A backend endpoint alone does not upgrade this label. Shared scientific or service code is recorded separately in Tables D and E. |
| SHARED / NOT STREAMLIT-OWNED | The file is imported by the backend, Dash, core, tools, or non-Streamlit tests, or it contains framework-neutral behavior used by more than one surface. It is not safe to classify it as removable Streamlit-only code. |
| DOCS/PACKAGING/TEST DEBT | The finding is a non-runtime manifest, lint, workflow, packaging, documentation, test, or source-assertion reference. It is recorded for a future work package rather than changed here. |

The inventory intentionally uses PARTIAL_PARITY when the source and tests establish the workflow shape but not exact browser behavior. “Same feature name” is not treated as proof of parity.

### Verbatim acceptance criteria from plan section 5

A row may carry a label only if all listed conditions hold and the evidence column cites file plus anchor, and a test name where applicable. When in doubt, downgrade (PARITY → PARTIAL → NONE). Name similarity is never evidence.

#### PARITY_CONFIRMED

- A Dash page/component is reachable from the Dash sidebar or a documented route.
- Every user-visible input the Streamlit capability offers has a Dash counterpart with the same value domain (same options/units/ranges), verified by reading both sources.
- Both paths call the same core function(s) or the Dash path calls a backend endpoint that wraps the same core function. Trace the call: Dash callback → api_client → backend/app.py route → core.
- Outputs are materially equivalent: same artefact types (figure/table/download formats) and the same persisted state keys in the workspace/project model.
- At least one automated test exercises the Dash side of the capability (name it), or the shared core function is tested and the Dash wiring is trivially thin; state this explicitly.

#### PARTIAL_PARITY

- A Dash counterpart exists, but at least one of: missing input/option; different defaults; different persistence (for example, Streamlit session-state versus backend workspace store) that changes user-visible behaviour; missing output format; different gating (for example, preview/license); no Dash-side test.
- The Delta column enumerates each concrete difference with anchors on both sides.

#### NO_DASH_EQUIVALENT

- No Dash page/component provides the capability to a user. Existence of a backend endpoint alone does not upgrade the row; note the endpoint under the backend evidence and keep the label.
- Record whether the underlying science/logic lives in shared core (so only the UI is missing) or inside ui itself (so logic would be lost).

#### SHARED / NOT STREAMLIT-OWNED

- The module is imported statically, per the section 13.6 grep, or dynamically, per the section 13.5 probe, by backend, core, dash_app, tools, scripts, desktop, or by tests that are not Streamlit tests.
- List every importer. If the module itself imports Streamlit, add the sub-label “streamlit-bearing shared module”; it is the highest-risk category.

#### DOCS/PACKAGING/TEST DEBT

- Non-runtime artefact (manifest line, lint ignore, workflow step, doc sentence, or test) that references Streamlit or a Streamlit-only file.
- Each row states the owning future work package: removal/installer work package versus PR-7 docs pass, as a recommendation only.

Document-level acceptance for this inventory is: every file returned by the broad git grep (excluding package-lock.json) appears in at least one table; every st.Page in app.py appears in Table B; every ui/components module appears in Table D; every row has a non-empty Evidence cell; the section 13.5 probe output is included; and no sentence in the document proposes or performs a change to runtime files.

## 3. Table A — runtime entrypoints and launch paths

| Streamlit path / artifact | Kind | What it starts | Dash / FastAPI equivalent | Classification | Evidence | Notes and risks |
| --- | --- | --- | --- | --- | --- | --- |
| app.py | Source entrypoint | Imports Streamlit, calls st.set_page_config, builds the hidden Streamlit navigation, and calls pg.run. | python -m dash_app.server; dash_app.server creates the combined Dash/FastAPI ASGI application. | PARTIAL_PARITY | app.py:1-32, 910-1093; dash_app/server.py:1-126; tests/test_deployment_contract.py::test_container_entrypoint_runs_combined_dash_server_only | Different framework, port default, state model, route names, and page registration. Keep both until a separately approved retirement work package closes all deltas. |
| streamlit run app.py | Documented local launch command | Starts the Streamlit shell on its default Streamlit port, normally 8501. | python -m dash_app.server --host 127.0.0.1 --port 8050 | PARTIAL_PARITY | app.py:1-6; dash_app/server.py:19-24, 102-126; packaging/windows/launcher.py:23, 77-78 | The two commands are not interchangeable for bookmarks, installer behavior, browser automation, or port-sensitive clients. |
| packaging/windows/launcher.py | Windows launcher | Imports streamlit.web.bootstrap, sets Streamlit environment/config, selects a port, and runs app.py. | No Windows launcher for Dash was found. The desktop experiment launches the FastAPI backend separately. | NO_DASH_EQUIVALENT | packaging/windows/launcher.py:18, 57-78, 90-116; desktop/electron/backend_locator.js:26-29 | A future installer decision is blocking: retire this path, retarget it to Dash, or retain it as a supported legacy product. The decision must include shortcut, port, config, update, and test behavior. |
| packaging/windows/ThermoAnalyzerLauncher.spec | PyInstaller packaging contract | Bundles the Streamlit launcher, Streamlit data/metadata, hidden imports, app/UI/core files, sample data, hosted/mirror library build trees, and documentation paths. | No equivalent Dash PyInstaller spec was found. | DOCS/PACKAGING/TEST DEBT | packaging/windows/ThermoAnalyzerLauncher.spec:33-84 | Owner: removal/installer work package. The spec references missing tracked guide paths and build/reference_library_hosted plus build/reference_library_mirror_live paths. Do not edit the spec as part of PR-6; reconcile it after the runtime decision. |
| packaging/windows/ThermoAnalyzer_Beta.iss, packaging/windows/build_beta_installer.ps1, and packaging/windows/build_beta_installer.bat | Installer/build scripts | Build and install the Streamlit launcher bundle; the PowerShell script drives PyInstaller/Inno Setup and the batch file delegates to it. | No Dash installer path was found. | DOCS/PACKAGING/TEST DEBT | packaging/windows/ThermoAnalyzer_Beta.iss:1-57; packaging/windows/build_beta_installer.ps1:1-105; packaging/windows/build_beta_installer.bat:1-5; packaging/windows/launcher.py:90-116 | Owner: removal/installer work package. Installer behavior is part of the removal acceptance surface, not a cleanup detail. |
| Dockerfile | Container image | Installs the combined Dash/FastAPI dependencies, Chromium, and the repository; exposes 8050 and health-checks /health. | docker/start.sh executes the combined Dash server. | DOCS/PACKAGING/TEST DEBT | Dockerfile:1-; docker/start.sh:1-6; tests/test_deployment_contract.py::test_dockerfile_keeps_dash_runtime_contract | Owner: removal/installer work package. This is the current deployed web contract, not Streamlit feature parity; the inventory does not alter it. |
| docker/start.sh | Container entrypoint | Executes python -m dash_app.server with host 0.0.0.0 and PORT environment variable defaulting to 8050 as the only foreground process. | Same combined server. | DOCS/PACKAGING/TEST DEBT | docker/start.sh:1-6; tests/test_deployment_contract.py::test_container_entrypoint_runs_combined_dash_server_only | Owner: removal/installer work package. No Streamlit command is present in this entrypoint; the test proves the current Dash container contract only. |
| vercel.json | Deployment seam | Routes the service to the root Dockerfile container. | The Dockerfile/Dash contract above. | DOCS/PACKAGING/TEST DEBT | vercel.json:1-; tests/test_deployment_contract.py::test_vercel_seam_reuses_docker_contract | Owner: removal/installer work package. Vercel is not an independent UI implementation. |
| desktop/electron/* | Experimental desktop shell | main.js launches a local backend.main FastAPI process with a randomized local port/token; the renderer is a backend-facing shell. | Backend API is shared with Dash; no evidence that Electron serves the Dash page tree. | SHARED / NOT STREAMLIT-OWNED | desktop/electron/README.md:3-; desktop/electron/main.js:1-; desktop/electron/backend_locator.js:26-29; desktop/electron/renderer.js:483-488 | renderer.js explicitly treats Streamlit as a fallback/reference surface. Do not count Electron as a Dash page counterpart. |
| desktop/backend_bundle/* | Experimental backend-only desktop packaging | PyInstaller freezes backend.main for Electron; it does not bundle app.py or the Streamlit UI. | Shared FastAPI backend used by Dash; no Dash page is served by this bundle. | SHARED / NOT STREAMLIT-OWNED | desktop/backend_bundle/README.md:1-23; desktop/backend_bundle/backend_entrypoint.py:1-7; desktop/backend_bundle/build_backend.py:1-88 | The bundle is a separate distribution path. Keep it in the migration map and test its backend contract independently of either web UI. |
| STREAMLIT_BROWSER_GATHER_USAGE_STATS, THERMOANALYZER_HOME, MATERIALSCOPE_HOME | Runtime environment/config | Controls Streamlit telemetry/config and the legacy launcher data root; the combined server uses MATERIALSCOPE_HOME. | Dash server uses its own host/port/token and the shared backend workspace. | PARTIAL_PARITY | packaging/windows/launcher.py:57-78; dash_app/server.py:19-24; docker/start.sh:4-6 | Environment migration, data-root migration, and user-state compatibility are unverified. |
| Port 8501 and port 8050 | Runtime contract | Legacy Streamlit launcher prefers 8501; Dash/container defaults to 8050. | Combined Dash/FastAPI uses 8050. | PARTIAL_PARITY | packaging/windows/launcher.py:23, 77-78; dash_app/server.py:19-24; Dockerfile EXPOSE 8050 | Port-sensitive installer shortcuts, browser tests, and external links need an explicit decision. |
| .streamlit/config.toml | Framework config | No tracked file found. The Windows launcher creates user-level .streamlit state at runtime. | Dash CSS/theme configuration is under dash_app/assets and dash_app/theme.py. | DOCS/PACKAGING/TEST DEBT | git ls-files .streamlit; packaging/windows/launcher.py:57-72; dash_app/theme.py:5-95 | Owner: removal/installer work package. Absence from the tracked tree is evidence, not a request to add or remove a config file. |

## 4. Table B — user-facing page and capability parity

The Streamlit route list is taken from app.py:942-1054. The Dash route list is taken from the register_page calls in dash_app/pages/*.py. Test names in this table indicate source, shared-core, API, or Dash callback coverage; they do not imply browser-level visual equivalence.

| Streamlit page (url_path) | Dash path | Capability | Streamlit behavior | Dash behavior | Backend endpoint(s) | Tests: Streamlit or shared / Dash | Classification | Delta or evidence gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| home (import) | / | Upload files and choose modality | Multi-file uploader accepts CSV, TXT, TSV, XLSX, and XLS; modality is selected during the import flow. | Dash stages a list of uploaded contents and exposes a modality-selection wizard. | dash_app.api_client.dataset_import:139-162; backend/app.py:1736-1795 | tests/test_validation.py::test_validate_import_stage_uses_detected_spectral_modality; tests/test_backend_workflow.py::test_workspace_import_run_analysis_and_save_roundtrip | PARTIAL_PARITY | S: ui/home.py:118-156; D: dash_app/pages/home.py:746-786. Streamlit submits uploader values directly while Dash stages pending files; accepted extensions, multiplicity, disabled states, and error copy are not proven equal. |
| home (import) | / | Map columns and enter import metadata | Column mapping includes temperature, signal, optional time, sample name, mass, heating rate, and XRD wavelength. | Dash mapping and metadata controls are built from the pending preview and review callbacks. | /dataset/import; workspace dataset detail via dash_app.api_client.dataset_import:139-162 and workspace_dataset_detail:80-87; backend/app.py:895-922, 1736-1795 | tests/test_validation.py::test_validate_import_stage_uses_detected_spectral_modality; tests/test_backend_api.py::test_dataset_import_accepts_ftir_with_warning_based_validation_summary | PARTIAL_PARITY | S: ui/home.py:159-307; ui/components/column_mapper.py:28-199; D: dash_app/pages/home.py:634-683, 808-926. The controls are present on both sides, but option order, inferred defaults, metadata persistence, and warning placement need side-by-side verification. |
| home (import) | / | Review validation and data preview | Streamlit shows import warnings, validation status, raw preview, metadata, and mapped columns before or after inserting session state. | Dash builds review data, validation summary, preview, and warning components in separate callbacks. | /dataset/import and /workspace/{project_id}/datasets/{dataset_key}; backend/app.py:895-922, 1736-1795 | tests/test_validation.py::test_validate_thermal_dataset_surfaces_import_review_context; tests/test_backend_workflow.py::test_workspace_import_run_analysis_and_save_roundtrip | PARTIAL_PARITY | S: ui/components/data_preview.py:9-92; ui/home.py:285-323; D: dash_app/pages/home.py:808-1189. Both expose review data, but row limits, labels, validation timing, and browser error surfaces are not established as equivalent. |
| home (import) | / | Load built-in sample data | Sample buttons load seven named CSV fixtures and update the active Streamlit session dataset. | Dash sample controls call the same import path and refresh the workspace. | /dataset/import via dash_app.api_client.dataset_import:139-162; backend/app.py:1736-1795 | tests/test_backend_workflow.py::test_workspace_import_run_analysis_and_save_roundtrip; tests/test_backend_api.py::test_dataset_import_accepts_xrd_with_contract_metadata | PARTIAL_PARITY | S: ui/home.py:325-390; D: dash_app/pages/home.py:1342-1388. Sample names, source paths, forced modality values, post-import state, and failure messaging require comparison; numeric 8501 fixture hits are unrelated false positives. |
| home (import) | / | Select active dataset and remove a dataset | Selectbox and remove action mutate st.session_state, analysis keys, comparison selection, and saved results. | Dash active-dataset and delete callbacks update workspace state and refresh dependent panels. | workspace_set_active_dataset and workspace_delete_dataset: dash_app/api_client.py:94-101, 129-136; backend/app.py:1448-1481 | tests/test_backend_workspace.py::test_compare_selection_and_active_dataset_validation; tests/test_backend_api.py::test_dataset_detail_rejects_unknown_dataset | PARTIAL_PARITY | S: ui/home.py:421-465; D: dash_app/pages/home.py:1403-1507. Backend validation is covered, but Streamlit cascade cleanup, confirmation/toast behavior, and session-to-workspace lifecycle differ or are unverified. |
| project | /project | Create a new project/workspace | New-project and clear-without-saving actions replace Streamlit project/session state and have confirmation paths. | Dash requests a new workspace, stores project identifiers, and renders confirmation callbacks. | workspace_new: dash_app/api_client.py:59-64; backend/app.py:842-848 | tests/test_backend_workspace.py::test_workspace_context_and_active_dataset_update; tests/test_backend_api.py::test_workspace_new_and_summary | PARTIAL_PARITY | S: ui/project_page.py:75-115, 183-204; D: dash_app/pages/project.py:404-523. Streamlit can clear without saving; Dash creates a backend workspace. State-loss, token, and confirmation semantics are not equivalent by inspection. |
| project | /project | Save a project archive | Prepares a .scopezip or ThermoZip-compatible archive and downloads it from the Streamlit page. | Save callback calls project_save and returns a browser download payload. | project_save: dash_app/api_client.py:444-449; POST /project/save: backend/app.py:821-839 | tests/test_project_io.py::test_project_archive_round_trip_restores_stable_state; tests/test_backend_api.py::test_project_load_save_roundtrip_compatibility | PARTIAL_PARITY | S: ui/project_page.py:121-148; D: dash_app/pages/project.py:593-647. Shared archive round trips are covered, but Dash callback behavior, browser filename, progress, and persisted state semantics are not proven equivalent. |
| project | /project | Load a project archive | Uploads .scopezip or thermozip, asks for replacement confirmation, then restores Streamlit state. | Dash stages the upload, asks for an action, and calls project_load before refreshing workspace context. | project_load: dash_app/api_client.py:451-456; POST /project/load: backend/app.py:800-818 | tests/test_project_io.py::test_project_archive_round_trip_restores_stable_state; tests/test_backend_api.py::test_project_load_rejects_invalid_base64 | PARTIAL_PARITY | S: ui/project_page.py:218-250; D: dash_app/pages/project.py:227-259, 404-523. Archive format is shared, but replacement prompts, invalid-archive messages, active/compare restoration, and browser upload behavior require side-by-side acceptance. |
| project | /project | Project overview metrics, dataset/result tables, and comparison status | Streamlit shows project overview counts, loaded runs, saved result records, comparison workspace state, validation issues, and archive status inside the overview tab. | Dash renders dataset/result metric cards and tables plus compare-workspace/archive status from workspace context. | workspace_context/summary/datasets/results: dash_app/api_client.py:66-108; backend/app.py:849-938 | tests/test_backend_workspace.py::test_workspace_context_and_active_dataset_update; tests/test_backend_api.py::test_workspace_new_and_summary | PARTIAL_PARITY | S: ui/project_page.py:91-94,155-178,256-315; D: dash_app/pages/project.py:249-401. Both expose the overview family, but metric definitions, table columns, refresh timing, validation issue detail, and comparison/archive state persistence are not proven equivalent. |
| compare | /compare | Choose analysis type and eligible runs | Streamlit filters stable datasets, selects a run type, and defaults to eligible runs. | Dash loads compare workspace and datasets, then filters options in callbacks. | compare_workspace, workspace_datasets: dash_app/api_client.py:73-78, 398-403; backend/app.py:868-882, 1394-1423 | tests/test_compare_dash_phase2.py::test_compare_page_source_contains_phase2_controls; tests/test_backend_workspace.py::test_compare_selection_and_active_dataset_validation | PARTIAL_PARITY | S: ui/compare_page.py:27-96; D: dash_app/pages/compare.py:203-276. Eligibility filtering is implemented on both sides, but default selection, option order, and empty-state messages are not proven identical. |
| compare | /compare | Select signal, notes, and render overlay summary | Streamlit chooses best or raw signal, writes notes, and renders an overlay figure plus summary table. | Dash renders selected-run controls, summary, and overlay panels from callback state. | compare workspace and analysis-state routes: dash_app/api_client.py:115-120, 398-403; backend/app.py:939-956, 1394-1447 | tests/test_compare_dash_phase2.py::test_axis_titles_spectral_and_xrd; tests/test_dsc_tga_parity.py | PARTIAL_PARITY | S: ui/compare_page.py:99-155; D: dash_app/pages/compare.py:258-286, 378-443. Signal fallback rules, figure ordering, summary columns, and warning placement require runtime comparison. |
| compare | /compare | Save comparison workspace, run batch, and capture figure | Streamlit saves comparison selection and snapshot bytes in session state; batch mode uses a template select. | Dash persists compare workspace, runs a batch endpoint, and renders saved-result/overlay panels. | update_compare_workspace and workspace_batch_run: dash_app/api_client.py:405-442; backend/app.py:1404-1447, 1482-1559 | tests/test_compare_dash_phase2.py::test_workspace_batch_run_persists_compare_workspace_combined_app; tests/test_backend_workflow.py::test_workspace_compare_batch_run_with_dta_stable_template | PARTIAL_PARITY | S: ui/compare_page.py:157-178, 321-379; D: dash_app/pages/compare.py:296-412. Backend persistence is covered, but session snapshot keys, browser downloads, batch warnings, and per-modality option domains are not proven equivalent. |
| export (report) | /export | Prepare dataset and result exports | Streamlit selects datasets and format, shows a preview, then offers raw/result CSV or XLSX downloads. | Dash workbench loads preparation rows and exposes separate data/result export callbacks. | export_preparation, export_results_csv, export_results_xlsx: dash_app/api_client.py:308-346; backend/app.py:1576-1604, 1672-1699 | tests/test_backend_exports.py::test_export_preparation_and_csv_generation; tests/test_export_report.py::test_results_to_xlsx_writes_summary_and_detail_sheets | PARTIAL_PARITY | S: ui/export_page.py:172-280; D: dash_app/pages/export.py:329-390, 914-1030. Streamlit route is /report while Dash is /export; selection defaults, disabled states, filenames, and download feedback are not proven equivalent. |
| export (report) | /export | Generate DOCX and PDF reports | Streamlit chooses report inputs and figure inclusion, then downloads generated files. | Dash report callbacks send selected result IDs and include_figures to typed report endpoints. | export_report_docx, export_report_pdf: dash_app/api_client.py:348-382; backend/app.py:1700-1735 | tests/test_backend_exports.py::test_export_docx_generation_returns_docx_bytes; tests/test_backend_exports.py::test_export_report_pdf_generation_returns_pdf_bytes | PARTIAL_PARITY | S: ui/export_page.py:282-421; D: dash_app/pages/export.py:376-390, 1031-1062. Core artifacts are tested, but UI option domains, figure-warning presentation, filenames, and branding preview are not proven equal. |
| export (report) | /export | Support snapshot and diagnostics | Streamlit prepares a support snapshot in the export page and exposes a download button. | Dash fetches, stores, renders, and downloads a typed support snapshot. | export_support_snapshot: dash_app/api_client.py:315-320; backend/app.py:1586-1604 | tests/test_backend_workflow.py::test_export_support_snapshot_returns_json_workspace | PARTIAL_PARITY | S: ui/export_page.py:82-168; D: dash_app/pages/export.py:696-783. Payload generation is shared, but visible fields, refresh timing, copy/download controls, and error behavior need comparison. |
| export (report) | /export | Branding and write-access gating | Streamlit branding fields and license state are maintained on the License & Branding page and affect reports. | Dash loads and saves workspace branding in the export workbench and applies read-only gating. | workspace_branding and update_workspace_branding: dash_app/api_client.py:384-396; backend/app.py:1606-1670 | tests/test_export_dash_page.py::test_export_branding_layout_contains_pending_logo_feedback_slot; tests/test_license_manager.py::test_commercial_mode_requires_license_for_write_access | PARTIAL_PARITY | S: ui/license_page.py:74-131; ui/export_page.py:330-421; D: dash_app/pages/export.py:790-914. Branding has a Dash surface, but license activation/badge ownership, field defaults, logo behavior, and write-gating messages are not confirmed equivalent. |
| license | No Dash page | License activation, trial state, clear license, and license badge | Dedicated activation and branding tabs; Streamlit sidebar displays license label and write-access state. | Branding is present in Dash export, but no user-facing Dash activation, trial, clear-license, or sidebar-badge page was found. | No activation endpoint found; branding-only GET/PUT /workspace/{project_id}/branding at backend/app.py:1606-1670 | tests/test_license_manager.py::test_activate_license_key_persists_and_loads; tests/test_license_manager.py::test_trial_becomes_expired_read_only_after_end_date | NO_DASH_EQUIVALENT | S: ui/license_page.py:5-131; D: no Dash license page. Backend license services do not upgrade this row. Decide how activation, trial, clear, write gating, and user messaging remain available. |
| library | No Dash page | Installed/catalog library, sync, provider/coverage view, and installed-package status | Dedicated Streamlit page renders status metrics, installed/catalog package and reference counts, sync/refresh actions, provider coverage, and cloud availability. It has no search or prefetch controls. | Library and cloud endpoints exist, but no user-facing Dash page registers the management capability. | /library/status, /library/catalog, /library/sync, /v1/library/* at backend/app.py:667-784 | tests/test_reference_library.py::test_backend_library_routes_surface_status_catalog_and_sync; tests/test_backend_api.py::test_local_dev_bootstrap_prefers_richest_sibling_corpus | NO_DASH_EQUIVALENT | S: ui/library_page.py:23-345; D: no Dash page. Endpoint availability is not UI parity; the Streamlit surface is a status/catalog/sync/coverage UI, not a search or prefetch UI, and its future owner must be Dash, external/admin, retained legacy, or explicit retirement. |
| about | /about | About/help content and navigation | Static tabbed about page renders project information and help content in the Streamlit shell. | Static Dash about page renders translated cards, architecture, capabilities, and common chrome. | No backend endpoint; static page registration at dash_app/pages/about.py:199-274 | tests/test_ui_consistency.py::test_about_page_is_navigation_item_not_license_tab; tests/test_dash_chrome_i18n.py | PARTIAL_PARITY | S: ui/about_page.py:11-148; D: dash_app/pages/about.py:199-274. Both pages exist, but exact copy, tabs, links, responsive structure, and accessibility are not confirmed without browser evidence. |
| kinetics (preview-gated) | No Dash page | Kissinger, OFW, and Friedman kinetics workflows | Preview page exposes method-specific controls, heating rates, multi-selects, output tables, and plots. | Core kinetics algorithms are tested, but no Dash page or API route for this UI was found. | None found for the UI; core.kinetics is exercised directly | tests/test_kinetics.py::test_run_kinetic_analysis_returns_report_ready_kissinger_payload; tests/test_kinetics.py::test_run_kinetic_analysis_returns_report_ready_friedman_payload | NO_DASH_EQUIVALENT | S: ui/kinetics_page.py:121-468; D: no Dash page. The preview gate and core science must be preserved or explicitly retired by a later decision; no deletion is implied here. |
| deconvolution (preview-gated) | No Dash page | Peak count, shape, bounds, guesses, run, plot, and table | Preview page exposes interactive deconvolution controls and result plots/tables. | Core peak deconvolution is tested, but no Dash page or API route for this UI was found. | None found for the UI; core.peak_deconvolution is exercised directly | tests/test_peak_deconvolution.py::test_deconvolve_peaks_returns_residual_stats_and_fit_quality; tests/test_peak_deconvolution.py::test_serialize_deconvolution_result_populates_scientific_context | NO_DASH_EQUIVALENT | S: ui/deconvolution_page.py:43-250; D: no Dash page. The preview gate and tested core behavior require an explicit future replacement or retirement decision. |
| dsc | /dsc | Select dataset and workflow template | Streamlit selects a dataset, seeds a workflow template, and uses session-backed processing state. | Dash loads eligible datasets and workflow/preset controls into page stores. | workspace_datasets and workspace_dataset_detail: dash_app/api_client.py:73-87; backend/app.py:868-922 | tests/test_dsc_dash_page.py::test_layout_contains_parity_ids_and_stores; tests/test_dsc_dash_page.py::test_default_processing_draft_has_all_sections | PARTIAL_PARITY | S: ui/dsc_page.py:159-205; D: dash_app/pages/dsc.py:1328-1433. Dataset/template controls exist on both sides, but default template selection, session keys, and empty-state behavior are not proven equal. |
| dsc | /dsc | Apply smoothing and baseline correction | Streamlit exposes method, window, polynomial, sigma, baseline, lambda, p, order, and region controls; actions push session undo snapshots. | Dash exposes corresponding cards, disabled-parameter callbacks, and draft updates. | analysis_run after draft update: dash_app/api_client.py:164-187; backend/app.py:1796-1845 | tests/test_dsc_dash_page.py::test_overrides_from_draft_includes_all_user_sections; tests/test_dsc_dash_page.py::test_run_dsc_analysis_forwards_draft_overrides_and_refreshes | PARTIAL_PARITY | S: ui/dsc_page.py:304-491; D: dash_app/pages/dsc.py:545-762, 1719-1878. Control families overlap, but exact ranges, units, defaults, disabled behavior, and history side effects require source-by-source comparison. |
| dsc | /dsc | Detect Tg and peaks | Streamlit offers Tg region, direction, prominence, and distance controls and renders derivative/peak figures. | Dash has Tg and peak cards, draft callbacks, analysis run, and result rendering. | analysis_run and analysis_state_curves: dash_app/api_client.py:115-187; backend/app.py:939-956, 1796-1845 | tests/test_dsc_dash_page.py::test_normalize_peak_detection_values_sanitizes_direction_and_distance; tests/test_backend_workflow.py::test_analysis_run_auto_registers_figure_for_dsc_and_persists_into_exports_and_project | PARTIAL_PARITY | S: ui/dsc_page.py:543-716; D: dash_app/pages/dsc.py:768-865, 1889-1920, 2165-2346. Result concepts overlap, but option domains, default regions, figure layout, and warning behavior are not proven equivalent. |
| dsc | /dsc | Undo, redo, and reset processing state | Streamlit uses _undo_stack and _redo_stack in st.session_state and updates controls immediately. | Dash stores processing_draft, undo, and redo data in dcc.Store and handles actions in callbacks. | No persistence endpoint; browser stores in Dash page state | tests/test_session_state.py; tests/test_dsc_dash_page.py::test_undo_redo_reset_cycle_for_processing_draft | PARTIAL_PARITY | S: ui/dsc_page.py:219-262; utils/session_state.py:101-203; D: dash_app/pages/dsc.py:1207-1230, 1935-1960. Both implement the action family, but storage lifetime, snapshot keys, reset defaults, and archive behavior differ. |
| dsc | /dsc | Save, apply, and delete processing presets | Streamlit preset manager saves and loads analysis settings through session/core storage. | Dash preset callbacks call typed list/load/save/delete endpoints and hydrate stores. | /presets/{analysis_type}: dash_app/api_client.py:265-305; backend/app.py:1301-1393 | tests/test_dsc_dash_page.py::test_apply_dsc_preset_loads_normalization_from_processing; tests/test_dta_dash_page.py::test_api_client_save_analysis_preset_forwards_POST_with_payload | PARTIAL_PARITY | S: ui/components/preset_manager.py:35-163; D: dash_app/pages/dsc.py:1434-1609. API parity exists, but name validation, refresh timing, error text, and whether Streamlit and Dash persist identical payload keys need verification. |
| dsc | /dsc | Run analysis and render result summary | Streamlit runs core DSC actions, renders figures, Tg/peak metrics, and result tables. | Dash posts AnalysisRunRequest, loads result detail, builds summary/quality/figure sections, and refreshes workspace state. | analysis_run and workspace_result_detail: dash_app/api_client.py:108-187; backend/app.py:923-938, 1796-1845 | tests/test_dsc_dash_page.py::test_run_dsc_analysis_forwards_draft_overrides_and_refreshes; tests/test_dsc_dash_page.py::test_display_result_returns_new_surface_sections | PARTIAL_PARITY | S: ui/dsc_page.py:589-778; D: dash_app/pages/dsc.py:2165-2346. Shared core/result contracts are strong, but state keys, automatic save timing, result ordering, and browser rendering are not proven equal. |
| dsc | /dsc | Save result and register figure artifacts | Streamlit explicitly saves results to session state and stores report-ready figure bytes. | Dash registers result figures through result artifact callbacks and exposes snapshot/report-figure actions. | register_result_figure and fetch_result_figure_png: dash_app/api_client.py:219-263; backend/app.py:1173-1260 | tests/test_dsc_dash_page.py::test_capture_dsc_figure_delegates_to_shared_helper; tests/test_backend_exports.py::test_report_exports_include_saved_figure_payloads | PARTIAL_PARITY | S: ui/dsc_page.py:778-795; D: dash_app/pages/dsc.py:2462-2590. Streamlit save is an explicit session action while Dash artifact registration is backend-owned; equivalent persisted keys, download behavior, and figure warnings remain unverified. |
| dsc | /dsc | Literature comparison | Streamlit literature panel loads/saves comparison details and shows provider/evidence states. | Dash literature callbacks call the typed result comparison route and render status/claims. | literature_compare: dash_app/api_client.py:189-217; backend/app.py:1092-1172 | tests/test_literature_compare_panel.py; tests/test_literature_compare.py::test_thermal_compare_context_exposes_search_mode_subject_trust_and_evidence_scope | PARTIAL_PARITY | S: ui/dsc_page.py:798-816; ui/components/literature_compare_panel.py:1561-1634; D: dash_app/pages/dsc.py:2386-2441. Provider failures, evidence buckets, persistence timing, and visible panel transitions need side-by-side acceptance. |
| tga | /tga | Select dataset, template, and temperature unit | Streamlit selects dataset, workflow template, and unit mode before processing. | Dash loads eligible datasets, template, and unit-mode stores. | workspace_datasets and workspace_dataset_detail: dash_app/api_client.py:73-87; backend/app.py:868-922 | tests/test_tga_dash_page.py::test_tga_controls_to_draft_normalizes_window_and_prominence; tests/test_tga_dash_page.py::test_tga_page_module_imports | PARTIAL_PARITY | S: ui/tga_page.py:196-288; D: dash_app/pages/tga.py:1319-1366. Unit labels and workflow state exist on both sides, but defaults, available units, and lifecycle semantics are not proven equal. |
| tga | /tga | Apply smoothing and DTG overlay | Streamlit exposes smoothing controls, DTG toggle, and smoothing action with session undo snapshots. | Dash exposes smoothing controls, DTG/result sections, draft synchronization, and disabled-field callbacks. | analysis_run after draft update: dash_app/api_client.py:164-187; backend/app.py:1796-1845 | tests/test_tga_dash_page.py::test_tga_controls_to_draft_normalizes_window_and_prominence; tests/test_tga_explore.py::test_build_tga_raw_quality_panel_renders_grade | PARTIAL_PARITY | S: ui/tga_page.py:419-558; D: dash_app/pages/tga.py:452-510, 748-817, 1077-1161. Smoothing ranges, DTG defaults, unit conversions, disabled behavior, and history side effects require comparison. |
| tga | /tga | Detect and render decomposition steps | Streamlit exposes prominence, minimum mass loss, step smoothing, and step plot/table controls. | Dash has step-detection card, exploration helpers, and result callbacks. | analysis_run and analysis_state_curves: dash_app/api_client.py:115-187; backend/app.py:939-956, 1796-1845 | tests/test_tga_explore.py::test_compute_tga_raw_exploration_stats_synthetic; tests/test_tga_dash_page.py::test_build_step_cards_truncates_high_step_count | PARTIAL_PARITY | S: ui/tga_page.py:595-745; D: dash_app/pages/tga.py:510-548, 1350-1522. Step thresholds, units, truncation, and warnings are not proven to match. |
| tga | /tga | Undo, redo, and reset processing state | Streamlit keeps _undo_stack and _redo_stack in session state and reports history counts. | Dash stores draft and undo/redo stacks in page stores and updates button disabled state. | No persistence endpoint; browser stores in Dash page state | tests/test_tga_dash_page.py::test_tga_snapshots_equal_for_dirty_tracking; tests/test_tga_explore.py::test_perform_undo_redo_roundtrip | PARTIAL_PARITY | S: ui/tga_page.py:289-332; D: dash_app/pages/tga.py:355-366, 1050-1173. Action names overlap, but stack lifetime, reset defaults, unit-mode coupling, and archive behavior differ. |
| tga | /tga | Save, apply, and delete processing presets | Streamlit preset manager provides select/apply/delete/save controls. | Dash preset callbacks use list/load/save/delete API calls and hydrate stores. | /presets/{analysis_type}: dash_app/api_client.py:265-305; backend/app.py:1301-1393 | tests/test_tga_dash_page.py::test_tga_preset_processing_body_for_save_includes_method_context; tests/test_dta_dash_page.py::test_api_client_delete_analysis_preset_forwards_DELETE | PARTIAL_PARITY | S: ui/components/preset_manager.py:35-163; D: dash_app/pages/tga.py:817-1050. API paths overlap, but payload keys, unit-mode persistence, error feedback, and refresh semantics need verification. |
| tga | /tga | Run analysis and render result summary | Streamlit runs TGA/DTG processing and renders mass-loss/step result figures and tables. | Dash posts analysis, loads result detail, and renders summary, quality, and figure sections. | analysis_run and workspace_result_detail: dash_app/api_client.py:108-187; backend/app.py:923-938, 1796-1845 | tests/test_tga_dash_page.py::test_run_tga_analysis_forwards_processing_overrides; tests/test_backend_workflow.py::test_analysis_run_auto_registers_figure_for_tga_and_persists_into_exports_and_project | PARTIAL_PARITY | S: ui/tga_page.py:548-837; D: dash_app/pages/tga.py:1350-1522. Shared analysis coverage is strong, but automatic save timing, result state keys, warnings, and browser layout are not proven equivalent. |
| tga | /tga | Save result and register figure artifacts | Streamlit explicitly saves a stable result in session state and prepares report figures. | Dash registers result figure artifacts and exposes snapshot/report-figure controls. | register_result_figure and fetch_result_figure_png: dash_app/api_client.py:219-263; backend/app.py:1173-1260 | tests/test_tga_dash_page.py::test_capture_tga_figure_delegates_to_shared_helper; tests/test_backend_exports.py::test_report_exports_include_saved_figure_payloads | PARTIAL_PARITY | S: ui/tga_page.py:836-866; D: dash_app/pages/tga.py:1634-1765. Streamlit explicit session save and Dash backend artifact registration have different ownership; equivalent keys, download behavior, and missing-figure warnings are unverified. |
| tga | /tga | Literature comparison | Streamlit literature panel renders provider states and persists comparison details. | Dash literature callbacks call the typed result comparison route and render bounded claims. | literature_compare: dash_app/api_client.py:189-217; backend/app.py:1092-1172 | tests/test_tga_dash_page.py::test_compare_tga_literature_forwards_options_and_renders_status; tests/test_literature_compare.py::test_tga_compare_no_results_persists_traceability | PARTIAL_PARITY | S: ui/tga_page.py:866-879; ui/components/literature_compare_panel.py:1561-1634; D: dash_app/pages/tga.py:1554-1620. Provider failure messages, evidence scope, persistence timing, and panel transitions need side-by-side acceptance. |
| dta | /dta | Select dataset and workflow template | Streamlit selects a dataset, template, and session-backed processing state. | Dash loads eligible datasets and template controls into stores. | workspace_datasets and workspace_dataset_detail: dash_app/api_client.py:73-87; backend/app.py:868-922 | tests/test_dta_dash_page.py::test_layout_contains_key_div_ids; tests/test_dta_dash_page.py::test_default_processing_draft_includes_baseline_and_peak_sections | PARTIAL_PARITY | S: ui/dta_page.py:151-206; D: dash_app/pages/dta.py:1395-1454, 1646-1670. Both expose the workflow, but defaults, template options, session keys, and empty states are not proven equal. |
| dta | /dta | Apply smoothing, baseline, and peak processing | Streamlit applies smoothing, baseline, and peak controls with undo snapshots and derivative figures. | Dash has separate smoothing, baseline, and peak cards, draft callbacks, and analysis-run payloads. | analysis_run: dash_app/api_client.py:164-187; backend/app.py:1796-1845 | tests/test_dta_dash_page.py::test_dta_analysis_run_honors_smoothing_overrides; tests/test_dta_dash_page.py::test_dta_analysis_run_honors_baseline_and_peak_overrides | PARTIAL_PARITY | S: ui/dta_page.py:321-689; D: dash_app/pages/dta.py:736-1126, 2567-3044. Processing sections match broadly, but option domains, default values, disabled states, and undo side effects require comparison. |
| dta | /dta | Undo, redo, reset, and presets | Streamlit history uses session state and the shared preset manager. | Dash stores processing history and calls typed preset endpoints. | /presets/{analysis_type}: dash_app/api_client.py:265-305; backend/app.py:1301-1393 | tests/test_dta_dash_page.py::test_undo_redo_cycle_restores_previous_and_future_drafts; tests/test_dta_dash_page.py::test_api_client_save_analysis_preset_forwards_POST_with_payload | PARTIAL_PARITY | S: ui/dta_page.py:206-248; ui/components/preset_manager.py:35-163; D: dash_app/pages/dta.py:1148-1243, 1454-1639, 2613-2720. The action family exists on both sides, but storage lifetime, payload keys, refresh, and error messages are not proven equal. |
| dta | /dta | Run analysis and render result metrics/tables | Streamlit runs DTA processing and renders peak metrics, result tables, and figures. | Dash posts analysis, loads detail, and renders summary, quality, result figure, and peak cards. | analysis_run and workspace_result_detail: dash_app/api_client.py:108-187; backend/app.py:923-938, 1796-1845 | tests/test_dta_dash_page.py::test_dta_dash_page_import_and_run_via_server; tests/test_dta_dash_page.py::test_build_peak_cards_with_data | PARTIAL_PARITY | S: ui/dta_page.py:397-792; D: dash_app/pages/dta.py:1685-1860. Shared result structures are tested, but result state keys, automatic persistence, warning surfaces, and browser layout are not proven equivalent. |
| dta | /dta | Save result and register figure artifacts | Streamlit saves DTA results into session records and prepares figure bytes for reports. | Dash figure callbacks register PNG artifacts and refresh result details. | register_result_figure and fetch_result_figure_png: dash_app/api_client.py:219-263; backend/app.py:1173-1260 | tests/test_dta_dash_page.py::test_capture_dta_figure_posts_png_once_per_result; tests/test_backend_workflow.py::test_analysis_run_auto_registers_figure_for_dta_and_persists_into_exports_and_project | PARTIAL_PARITY | S: ui/dta_page.py:689-799; D: dash_app/pages/dta.py:3157-3330. Streamlit save and Dash artifact registration have different persistence owners; figure keys, download behavior, and failure warnings are unverified. |
| dta | /dta | Literature comparison | Streamlit literature panel renders provider status, evidence buckets, and persisted claims. | Dash literature callbacks call the same typed comparison endpoint and render claims/citations. | literature_compare: dash_app/api_client.py:189-217; backend/app.py:1092-1172 | tests/test_dta_dash_page.py::test_compare_dta_literature_renders_claims_and_citations; tests/test_literature_compare.py::test_dta_compare_prefers_entity_and_temperature_anchored_paper_over_modality_only | PARTIAL_PARITY | S: ui/dta_page.py:792-816; ui/components/literature_compare_panel.py:1561-1634; D: dash_app/pages/dta.py:3076-3140. Provider failure, evidence scope, persistence timing, and visible panel transitions need side-by-side acceptance. |
| ftir | /ftir | Select data and process spectral signal | Streamlit FTIR wrapper delegates to the shared spectral page with plot settings, smoothing, baseline, normalization, peaks, and matching controls. | Dash FTIR page exposes the same broad processing sections and runs typed analysis callbacks. | workspace_datasets, analysis_run, analysis_state_curves: dash_app/api_client.py:73-187; backend/app.py:868-956, 1796-1845 | tests/test_ftir_dash_page.py::test_default_processing_draft_has_all_sections; tests/test_ftir_dash_page.py::test_run_ftir_analysis_forwards_processing_overrides | PARTIAL_PARITY | S: ui/ftir_page.py:1-12; ui/spectral_page.py:200-610; D: dash_app/pages/ftir.py:508-762, 1113-1909. The counterpart is broad, but ranges, defaults, axis units, plot settings, and bad-data responses are not fully compared. |
| ftir | /ftir | FTIR peaks, library matching, and result figure | Streamlit renders peaks, optional library matching, normalized/raw traces, and Plotly results. | Dash renders peak cards/match table, library status, result figures, and result metadata. | analysis_run, workspace_result_detail, analysis_state_curves: dash_app/api_client.py:108-187; backend/app.py:923-956, 1796-1845 | tests/test_ftir_dash_page.py::test_build_match_table_renders_columns; tests/test_ftir_dash_page.py::test_display_result_returns_nine_outputs | PARTIAL_PARITY | S: ui/spectral_page.py:610-820; D: dash_app/pages/ftir.py:1878-2067, 2862-2920. Match status, trace selection, peak limits, result formatting, and browser figure behavior remain unproven. |
| ftir | /ftir | FTIR presets and literature comparison | Streamlit uses the shared preset manager and literature panel when the modality supports them. | Dash calls preset and literature endpoints and renders FTIR-prefixed callbacks. | /presets/{analysis_type} and literature compare: dash_app/api_client.py:189-305; backend/app.py:1092-1172, 1301-1393 | tests/test_ftir_dash_page.py::test_literature_compare_uses_ftir_prefix; tests/test_ftir_dash_page.py::test_preset_dirty_flag_renders_dirty_when_snapshot_differs | PARTIAL_PARITY | S: ui/spectral_page.py:439-472, 379-413; D: dash_app/pages/ftir.py:1178-1380, 2067-2160. API and control families overlap, but preset payloads, provider states, limits, and panel transitions need acceptance. |
| raman | /raman | Select data and process spectral signal | Streamlit Raman wrapper delegates to the shared spectral page with smoothing, baseline, normalization, peaks, matching, and plot controls. | Dash Raman page exposes the corresponding sections and typed analysis callbacks. | workspace_datasets, analysis_run, analysis_state_curves: dash_app/api_client.py:73-187; backend/app.py:868-956, 1796-1845 | tests/test_raman_dash_page.py::test_default_processing_draft_has_all_sections; tests/test_raman_dash_page.py::test_run_raman_analysis_forwards_processing_overrides | PARTIAL_PARITY | S: ui/raman_page.py:1-12; ui/spectral_page.py:200-610; D: dash_app/pages/raman.py:513-767, 1118-1914. Counterpart coverage is broad, but Raman-specific ranges, defaults, axis units, and error responses are not fully compared. |
| raman | /raman | Raman peaks, library matching, and result figure | Streamlit renders peaks, optional library matching, selected traces, and Plotly results. | Dash renders match cards/table, library status, result metadata, and figures. | analysis_run, workspace_result_detail, analysis_state_curves: dash_app/api_client.py:108-187; backend/app.py:923-956, 1796-1845 | tests/test_raman_dash_page.py::test_build_match_table_renders_columns; tests/test_raman_dash_page.py::test_display_result_returns_nine_outputs | PARTIAL_PARITY | S: ui/spectral_page.py:610-820; D: dash_app/pages/raman.py:1883-2072, 2867-2925. Match status, trace selection, peak limits, result formatting, and browser figure behavior remain unproven. |
| raman | /raman | Raman presets and literature comparison | Streamlit uses shared presets and literature compare for Raman results. | Dash calls typed preset and literature endpoints and renders Raman-prefixed callbacks. | /presets/{analysis_type} and literature compare: dash_app/api_client.py:189-305; backend/app.py:1092-1172, 1301-1393 | tests/test_raman_dash_page.py::test_literature_compare_uses_raman_prefix; tests/test_raman_dash_page.py::test_preset_dirty_flag_renders_dirty_when_snapshot_differs | PARTIAL_PARITY | S: ui/spectral_page.py:439-472, 379-413; D: dash_app/pages/raman.py:1183-1394, 2072-2160. API and control families overlap, but preset payloads, provider states, limits, and visible panel transitions need acceptance. |
| xrd | /xrd | Review axis and wavelength context | Streamlit confirms axis interpretation and wavelength before processing. | Dash has setup review, wavelength store, validation, and disabled run state callbacks. | workspace_dataset_detail: dash_app/api_client.py:80-87; backend/app.py:895-922 | tests/test_xrd_page.py; tests/test_xrd_dash_page.py::test_layout_contains_key_div_ids; tests/test_validation.py::test_validate_xrd_processing_warns_when_wavelength_context_is_missing | PARTIAL_PARITY | S: ui/xrd_page.py:845-883; D: dash_app/pages/xrd.py:875-945. Both gate input review, but warning copy, default wavelength, axis sorting, and confirmation persistence need comparison. |
| xrd | /xrd | Apply axis, smoothing, baseline, and peak controls | Streamlit exposes XRD axis range, smoothing, baseline, prominence, distance, width, and max-peak controls. | Dash exposes corresponding processing cards and draft synchronization. | analysis_run after draft update: dash_app/api_client.py:164-187; backend/app.py:1796-1845 | tests/test_xrd_page.py; tests/test_xrd_dash_page.py::test_xrd_default_corrected_view_demotes_raw_from_autorange | PARTIAL_PARITY | S: ui/xrd_page.py:1659-1759; D: dash_app/pages/xrd.py:1241-1498. Large control families overlap, but numeric ranges, defaults, units, disabled fields, and axis normalization are not proven equal. |
| xrd | /xrd | Plot settings and figure presentation controls | Streamlit exposes reset/autoscale, x/y ranges, line and marker precision, labels, matched/unmatched connectors, and log-y presentation controls. | Dash exposes overlapping plot-settings callbacks, result-plot controls, and figure presentation updates. | No distinct endpoint; settings are carried through the analysis draft and analysis_run: dash_app/api_client.py:164-187; backend/app.py:1796-1845 | tests/test_xrd_page.py; tests/test_xrd_dash_page.py::test_xrd_default_corrected_view_demotes_raw_from_autorange; tests/test_xrd_browser_rendering.py::test_xrd_result_plotly_graph_has_visible_browser_box | PARTIAL_PARITY | S: ui/xrd_page.py:1173-1367; D: dash_app/pages/xrd.py:501-579,1276-1492. The surfaces overlap, but exact defaults, control IDs, disabled behavior, autoscale/reset semantics, and connector/label/log-y persistence are not proven equivalent. |
| xrd | /xrd | Match candidates and render reference comparison | Streamlit configures tolerance, score, top-N, intensity weights, and renders candidate cards/tables and references. | Dash configures match controls, renders candidate results, and uses result/state endpoints. | analysis_run, workspace_result_detail, analysis_state_curves: dash_app/api_client.py:108-187; backend/app.py:923-956, 1796-1845 | tests/test_xrd_display.py::test_xrd_candidate_display_variants_apply_scientific_formatting_after_name_resolution; tests/test_xrd_dash_page.py::test_match_card_renders_candidate_and_score | PARTIAL_PARITY | S: ui/xrd_page.py:1762-1802, 2057-2072; D: dash_app/pages/xrd.py:459-493, 1241-1299, 2172-2323. Candidate naming, no-match semantics, scoring defaults, table truncation, and reference evidence need a dedicated comparison. |
| xrd | /xrd | Undo, redo, reset, and presets | Streamlit stores XRD processing history in session state and uses the shared preset manager. | Dash stores processing draft/history and calls typed preset endpoints. | /presets/{analysis_type}: dash_app/api_client.py:265-305; backend/app.py:1301-1393 | tests/test_xrd_page.py; tests/test_xrd_dash_page.py::test_layout_contains_mature_history_and_preset_stores | PARTIAL_PARITY | S: ui/xrd_page.py:1554-1633, 2085-2164; D: dash_app/pages/xrd.py:970-1209, 1222-1724. Both expose the action family, but state keys, snapshot lifetime, reset defaults, and payload refresh behavior are not proven equal. |
| xrd | /xrd | Render result tables and primary figure | Streamlit renders result tables, figures, snapshots, and report-figure selection in session records. | Dash loads result detail, renders tables/figures, and maintains result caches. | workspace_result_detail and fetch_result_figure_png: dash_app/api_client.py:108-120, 242-263; backend/app.py:923-956, 1242-1260 | tests/test_xrd_dash_page.py::test_build_xrd_result_figure_preserves_log_y_range_after_shared_theme; tests/test_xrd_browser_rendering.py::test_xrd_result_plotly_graph_has_visible_browser_box | PARTIAL_PARITY | S: ui/xrd_page.py:2085-2391; D: dash_app/pages/xrd.py:2172-2390. Both render result artifacts, but table truncation, figure sizing, cache keys, warnings, and browser layout are not confirmed equivalent. |
| xrd | /xrd | Literature comparison and figure artifacts | Streamlit literature panel and snapshot/report buttons update session result artifacts. | Dash literature and figure-artifact callbacks call typed workspace routes and register PNGs. | literature_compare, register_result_figure, fetch_result_figure_png: dash_app/api_client.py:189-263; backend/app.py:1092-1260 | tests/test_xrd_dash_page.py::test_compare_xrd_literature_callback_uses_xrd_literature_prefix; tests/test_xrd_dash_page.py::test_xrd_figure_artifact_callback_save_snapshot_registers | PARTIAL_PARITY | S: ui/xrd_page.py:2256-2421; D: dash_app/pages/xrd.py:2394-2639. Backend paths exist on Dash, but evidence buckets, report-figure replacement, snapshot keys, and failure messaging need side-by-side acceptance. |

## 5. Table C — shell, chrome, and cross-page behavior

| Shell capability | Streamlit implementation | Dash implementation | Classification | Evidence | Delta / risk |
| --- | --- | --- | --- | --- | --- |
| Navigation grouping | app.py renders primary, analyses, and management sections and hides native navigation. | dash_app.layout builds primary, analysis, and management sidebar groups from registered pages. | PARTIAL_PARITY | app.py:839-907; dash_app/layout.py:11-149; tests/test_ui_consistency.py::test_sidebar_navigation_uses_grouped_scientific_structure | Route names differ (import/report versus / /export), management omits Library and License, and preview pages are not in Dash. |
| Brand and license badge | Sidebar brand and License label are rendered from license state. | Sidebar brand/tagline is rendered; no equivalent license badge/activation panel was found. | PARTIAL_PARITY | app.py:839-855; dash_app/layout.py:117-149; ui/license_page.py:74-131 | License visibility and write-state messaging are user-impacting deltas. |
| Locale selection | ui_language defaults to tr; segmented control changes Streamlit session state. | ui-locale defaults to en; locale dropdown persists a Dash store and supports en/tr. | PARTIAL_PARITY | utils/session_state.py:10-36; app.py:859-866; dash_app/layout.py:70-114, 225-234; dash_app/i18n.py:13- | Default locale differs. Shared translation import also creates the blocked Streamlit dependency. |
| Theme selection | Light/dark segmented control is held in Streamlit session state. | Theme button and ui-theme store update html[data-theme]; Plotly tokens are in dash_app/theme.py. | PARTIAL_PARITY | app.py:868-875; utils/session_state.py:64-70; dash_app/layout.py:70-114, 188-222; dash_app/theme.py:5-95 | Persistence, initial values, CSS coverage, and figure-level defaults need browser verification. |
| Dataset count badge | Sidebar displays the current dataset count. | sidebar-dataset-badge is built from workspace state. | PARTIAL_PARITY | app.py:877-882; dash_app/layout.py:117-149, 261-298 | Counts depend on different state lifecycles and refresh timing. |
| Preview toggle and gating | Streamlit exposes a preview toggle and conditionally registers Kinetics/Deconvolution pages. | No preview toggle or counterpart pages were found. | NO_DASH_EQUIVALENT | app.py:929-1054; utils/runtime_flags.py:8-21; dash_app/layout.py:11-29 | No user-facing Dash counterpart exists for this toggle/gating control; backend/core flags do not upgrade it to parity. It requires a future product decision. |
| Recent-history sidebar | Uses Streamlit history/session helpers and page result state. | sidebar-history-panel renders recent workspace history from backend context. | PARTIAL_PARITY | app.py:1088-1091; ui/components/history_tracker.py; dash_app/layout.py:32-47, 261-298 | Event ordering, retention, clear behavior, and archive round trip differ in state ownership. |
| Page header / hero | Shared Streamlit render_page_header supplies title, caption, and badge. | Dash pages use page-specific hero/guidance components and shared translations. | PARTIAL_PARITY | ui/components/chrome.py:1-20; ui/components/workflow_guide.py:1-445; dash_app/components/page_guidance.py:1-; tests/test_ui_consistency.py:1- | Copy and structural intent are similar; pixel, responsive, and screen-reader equivalence is not established. |
| Workflow guides | Streamlit analysis pages call shared guide component for DSC, DTA, TGA, FTIR, Raman, and XRD. | Dash analysis pages use page guidance/help-hint components. | PARTIAL_PARITY | tests/test_ui_consistency.py::test_stable_analysis_pages_render_workflow_guides; dash_app/components/page_guidance.py:1- | Content keys overlap but rendering, placement, and dismissal behavior are not proven equal. |
| Alerts, errors, and theming CSS | Streamlit page functions emit notices and inject CSS. | Dash uses Bootstrap/assets CSS, theme tokens, callback status and alert components. | PARTIAL_PARITY | app.py:184-; dash_app/theme.py:45-95; dash_app/assets/style.css; tests/test_deployment_contract.py | Framework-native alert semantics and responsive styling differ; browser QA is required before any retirement. |
| Plot resizing and figure theme | Streamlit renders Plotly figures in page components. | Dash adds ms-figure-host, resize JavaScript, and light/dark Plotly theme application. | PARTIAL_PARITY | core/figure_render.py; dash_app/theme.py:45-95; dash_app/assets/result_figure_resize.js; tests/test_deployment_contract.py::test_dash_assets_keep_result_plotly_resize_contract | The technical seam is tested; visual equivalence of every modality figure is not. |

## 6. Table D — Streamlit UI modules and counterparts

The rows below cover every file under ui/components/ plus utils/i18n.py and utils/session_state.py. The direct-importer manifest immediately after the table is exhaustive for tracked Python source/tests at the inspected revision; it distinguishes direct imports from transitive Dash consumers and is reproduced from the static source scan.

| Module | Streamlit responsibility | Direct importers / consumers | Dash counterpart | Classification | Evidence and removal note |
| --- | --- | --- | --- | --- | --- |
| ui/components/__init__.py | Package marker; no Streamlit widgets or runtime behavior. | Imported as the ui.components package by component/page tests and modules. | No direct Dash counterpart is required. | DOCS/PACKAGING/TEST DEBT | ui/components/__init__.py:(empty file); Owner: removal/installer work package only if package discovery changes. Included for complete ui/components module coverage; no removal action is justified by this inventory. |
| ui/components/chrome.py | Streamlit page headers, badges, notices, and shell helpers. | Exact direct importers: ui/about_page.py, ui/compare_page.py, ui/dsc_page.py, ui/dta_page.py, ui/export_page.py, ui/home.py, ui/library_page.py, ui/license_page.py, ui/project_page.py, ui/spectral_page.py, ui/tga_page.py, ui/xrd_page.py. | dash_app/layout.py, dash_app/components/page_guidance.py, per-page hero helpers. | PARTIAL_PARITY | ui/components/chrome.py:1-20; dash_app/layout.py:1-298; source assertions in tests/test_ui_consistency.py:1- | Shared intent is not shared implementation. |
| ui/components/column_mapper.py | Streamlit file-to-column mapping controls and validation UI. | Exact direct importer: ui/home.py. | Dash home wizard mapping controls and /dataset/import. | PARTIAL_PARITY | ui/components/column_mapper.py:28-199; dash_app/pages/home.py:316-370, 808-1294. Keep mapping rules in core; compare UI option domains before any UI removal. |
| ui/components/data_preview.py | Streamlit raw-data preview table and metadata display. | Exact direct importer: ui/home.py. | Dash home preview/review cards. | PARTIAL_PARITY | ui/components/data_preview.py:9-92; dash_app/pages/home.py:808-1189. Exact row limits, labels, and invalid-data handling are unverified. |
| ui/components/history_tracker.py | Streamlit in-session analysis history and result navigation. | Exact direct importers: app.py, ui/compare_page.py, ui/deconvolution_page.py, ui/dsc_page.py, ui/dta_page.py, ui/home.py, ui/kinetics_page.py, ui/spectral_page.py, ui/tga_page.py, ui/xrd_page.py. | Dash workspace history sidebar and backend recent_history. | PARTIAL_PARITY | ui/components/history_tracker.py:1-100; dash_app/layout.py:32-47, 261-298. State semantics must be reconciled before deleting either helper. |
| ui/components/literature_compare_panel.py | Streamlit literature comparison panel, provider states, evidence buckets, and diagnostics. | Exact direct importers: tests/test_literature_compare_panel.py, ui/dsc_page.py, ui/dta_page.py, ui/spectral_page.py, ui/tga_page.py, ui/xrd_page.py. | Dash literature compare components/callbacks and /literature/compare. | PARTIAL_PARITY | ui/components/literature_compare_panel.py:1561-1634; dash_app/components/literature_compare_ui.py:1-; tests/test_literature_compare.py:1-; tests/test_dta_dash_page.py:1-. Provider failure and evidence presentation need end-to-end comparison. |
| ui/components/plot_builder.py | Streamlit-facing plot builders and analysis-state access; it has no direct st. widget calls but imports session state. | Exact direct importers: tests/test_plot_builder.py, tests/test_xrd_page.py, ui/compare_page.py, ui/deconvolution_page.py, ui/dsc_page.py, ui/dta_page.py, ui/home.py, ui/kinetics_page.py, ui/spectral_page.py, ui/tga_page.py, ui/xrd_page.py. | Dash Plotly figure/component builders are separate. | PARTIAL_PARITY | ui/components/plot_builder.py:1-616; utils/session_state.py:1-203; tests/test_plot_builder.py:1-. Kinetics, multirate, and deconvolution builders require an explicit core-or-loss decision. |
| ui/components/preset_manager.py | Streamlit preset select/save/delete UI and status messages. | Exact direct importers: ui/dsc_page.py, ui/dta_page.py, ui/spectral_page.py, ui/tga_page.py, ui/xrd_page.py. | Dash preset cards and /presets/{analysis_type} API. | PARTIAL_PARITY | ui/components/preset_manager.py:35-163; dash_app/components/analysis_boilerplate.py:1-; backend/app.py:1301-1394; tests/test_dta_dash_page.py:1-. API parity exists; option refresh/error UI differs until verified. |
| ui/components/quality_dashboard.py | Streamlit data-quality metrics/status cards. | Exact direct importers: ui/dsc_page.py, ui/dta_page.py, ui/tga_page.py. | Dash raw-quality and page-specific quality components. | PARTIAL_PARITY | ui/components/quality_dashboard.py:14-186; dash_app/components/raw_quality.py:1-; dash_app/pages/dta.py:1-. Metrics and thresholds need a source-level comparison. |
| ui/components/workflow_guide.py | Streamlit modality workflow guidance and explanatory text. | Exact direct importers: ui/dsc_page.py, ui/dta_page.py, ui/home.py, ui/spectral_page.py, ui/tga_page.py, ui/xrd_page.py. | dash_app/components/page_guidance.py and per-page help hints. | PARTIAL_PARITY | ui/components/workflow_guide.py:346-445; dash_app/components/page_guidance.py:1-; tests/test_ui_consistency.py:1-. Translation keys overlap, but the rendering contract is different. |
| utils/i18n.py | Shared translation catalog plus Streamlit session-backed get_language, t, and tx; also contains Dash translation keys. | Exact direct and package-form importers are listed in the manifest below; Dash consumers are direct even though the module is Streamlit-bearing. | dash_app/i18n.py thin wrapper over this module. | SHARED / NOT STREAMLIT-OWNED — streamlit-bearing shared module | utils/i18n.py:5, 3852-3904; blocked import probe in section 13. Decouple the import before changing ownership. |
| utils/session_state.py | Streamlit session defaults, project state, analysis undo/redo snapshots, and render revisions. | Exact direct importers are listed in the manifest below: app.py, selected ui modules, ui/components/plot_builder.py, ui/components/preset_manager.py, and tests/test_session_state.py. | Dash dcc.Store plus backend workspace/analysis-state APIs; no direct Dash import. | SHARED / NOT STREAMLIT-OWNED — streamlit-bearing shared module | utils/session_state.py:1-203; dash_app/layout.py:164-185; tests/test_session_state.py:1-. Pure undo/redo helpers may migrate; session-bound functions cannot be removed without a state plan. |

### 6.1 Exact direct-importer manifest

The following lists are the complete static direct-importer sets for the Table D modules. A listed file imports the target module or imports the target symbol from its package. Dynamic imports and transitive consumers are called out separately.

- ui/components/__init__.py: no direct importer; package marker only.
- ui/components/chrome.py: ui/about_page.py, ui/compare_page.py, ui/dsc_page.py, ui/dta_page.py, ui/export_page.py, ui/home.py, ui/library_page.py, ui/license_page.py, ui/project_page.py, ui/spectral_page.py, ui/tga_page.py, ui/xrd_page.py.
- ui/components/column_mapper.py: ui/home.py.
- ui/components/data_preview.py: ui/home.py.
- ui/components/history_tracker.py: app.py, ui/compare_page.py, ui/deconvolution_page.py, ui/dsc_page.py, ui/dta_page.py, ui/home.py, ui/kinetics_page.py, ui/spectral_page.py, ui/tga_page.py, ui/xrd_page.py.
- ui/components/literature_compare_panel.py: tests/test_literature_compare_panel.py, ui/dsc_page.py, ui/dta_page.py, ui/spectral_page.py, ui/tga_page.py, ui/xrd_page.py.
- ui/components/plot_builder.py: tests/test_plot_builder.py, tests/test_xrd_page.py, ui/compare_page.py, ui/deconvolution_page.py, ui/dsc_page.py, ui/dta_page.py, ui/home.py, ui/kinetics_page.py, ui/spectral_page.py, ui/tga_page.py, ui/xrd_page.py.
- ui/components/preset_manager.py: ui/dsc_page.py, ui/dta_page.py, ui/spectral_page.py, ui/tga_page.py, ui/xrd_page.py.
- ui/components/quality_dashboard.py: ui/dsc_page.py, ui/dta_page.py, ui/tga_page.py.
- ui/components/workflow_guide.py: ui/dsc_page.py, ui/dta_page.py, ui/home.py, ui/spectral_page.py, ui/tga_page.py, ui/xrd_page.py.
- utils/session_state.py: app.py, tests/test_session_state.py, ui/components/plot_builder.py, ui/components/preset_manager.py, ui/dsc_page.py, ui/dta_page.py, ui/home.py, ui/project_page.py, ui/tga_page.py.
- utils/i18n.py: app.py; dash_app/components/analysis_boilerplate.py, dash_app/components/analysis_page.py, dash_app/components/figure_artifacts.py, dash_app/components/literature_compare_ui.py, dash_app/components/page_guidance.py, dash_app/components/raw_quality.py, dash_app/components/spectral_explore.py, dash_app/components/spectral_plot_settings.py, dash_app/components/tga_explore.py, dash_app/components/xrd_result_plot.py; dash_app/i18n.py; dash_app/pages/about.py, dash_app/pages/compare.py, dash_app/pages/dsc.py, dash_app/pages/dta.py, dash_app/pages/export.py, dash_app/pages/ftir.py, dash_app/pages/home.py, dash_app/pages/project.py, dash_app/pages/raman.py, dash_app/pages/tga.py, dash_app/pages/xrd.py; tests/test_ftir_dash_page.py, tests/test_i18n.py (package-form import), tests/test_raman_dash_page.py, tests/test_xrd_dash_page.py; ui/about_page.py, ui/compare_page.py, ui/components/column_mapper.py, ui/components/data_preview.py, ui/components/preset_manager.py, ui/components/quality_dashboard.py, ui/components/workflow_guide.py, ui/deconvolution_page.py, ui/dsc_page.py, ui/dta_page.py, ui/export_page.py, ui/home.py, ui/library_page.py, ui/license_page.py, ui/project_page.py, ui/spectral_page.py, ui/tga_page.py, ui/xrd_page.py.

The manifest is limited to direct static importers. tests/test_dash_chrome_i18n.py is a transitive consumer through dash_app.i18n, and Dash page modules/components that import utils.i18n are direct consumers of the Streamlit-bearing module. No backend, core, tools, scripts, or desktop module directly imports ui, utils.i18n, or utils.session_state in the inspected source scan.

## 7. Table E — shared modules that are not safe to remove as Streamlit-only

This table isolates modules that look adjacent to the legacy surface but are consumed by backend, Dash, core, tools, packaging, or tests. The list is a removal-safety map, not a recommendation to preserve every UI wrapper forever.

| Module or group | Non-Streamlit consumers found | Streamlit relationship | Classification | Evidence / future decision |
| --- | --- | --- | --- | --- |
| utils/i18n.py | Exact direct consumers are listed in Table D section 6.1, including dash_app/i18n.py, all Dash pages/components that import the catalog, app.py, Streamlit UI, and tests/test_i18n.py. | Also imported by app.py and Streamlit UI; module imports Streamlit at import time. | SHARED / NOT STREAMLIT-OWNED — streamlit-bearing shared module | utils/i18n.py:5,3852-3904; import reachability scan and blocked import output in section 13. First blocking prerequisite is framework-neutral translation ownership. |
| utils/session_state.py | Exact direct consumers are listed in Table D section 6.1: app.py, five ui modules, ui/components/plot_builder.py, ui/components/preset_manager.py, and tests/test_session_state.py. | Module import and session functions are Streamlit-owned; pure snapshot/undo functions are framework-neutral. | SHARED / NOT STREAMLIT-OWNED — streamlit-bearing shared module | tests/test_session_state.py:1-; ui/components/plot_builder.py:1-616. Split pure state helpers only under a tested state migration. |
| core/data_io.py, core/validation.py, core/processing_schema.py | Backend import/workspace/API paths, Dash import/processing paths, project/export tests. | Streamlit pages call the same ingest and validation behavior. | SHARED / NOT STREAMLIT-OWNED | core/data_io.py:1-2158; core/validation.py:1-1240; core/processing_schema.py:1-426; backend/app.py:1736-1796; dash_app/pages/home.py:808-1294; tests/test_validation.py:1-. core/data_io.py is also a text-scan hit because of a historical 8501 token. |
| core/* processing modules (dsc_processor, dta_processor, tga_processor, spectral/XRD processing, baseline, peak analysis, preprocessing, modalities) | backend.app, dash_app, core tests, and report/export services. | Streamlit pages call these modules directly. | SHARED / NOT STREAMLIT-OWNED | core/dsc_processor.py:1-415; core/dta_processor.py:1-449; core/tga_processor.py:1-666; core/preprocessing.py:1-317; core/baseline.py:1-503; core/peak_analysis.py:1-558; core/modalities/registry.py:1-69; core/xrd_display.py:1-; core/spectral_demo_references.py:1-83; backend/app.py:1796-1845; tests/test_dsc_tga_parity.py:1-. Do not conflate removal of a UI with removal of scientific behavior. |
| core/plotting.py and core/figure_render.py | Dash figure/artifact components, backend result/figure routes, report/export code, tests. | Streamlit result pages render the same family of Plotly figures. | SHARED / NOT STREAMLIT-OWNED | core/plotting.py:1-475; core/figure_render.py:1-; dash_app/theme.py:45-95; backend/app.py:923-1242; tests/test_backend_exports.py:1-; visual artifact checks remain separate. |
| core/result_serialization.py, core/provenance.py, core/report_generator.py | Backend exports, project archive, Dash result/report paths, API tests. | Streamlit export/report pages consume the serialized result/artifact model. | SHARED / NOT STREAMLIT-OWNED | core/result_serialization.py:1-; core/provenance.py:1-; core/report_generator.py:1-; tests/test_backend_exports.py:1-; tests/test_backend_workflow.py:1-; tests/test_project_io.py:1-. Preserve archive/report compatibility independently of UI retirement. |
| core/project_io.py | Backend /project/load and /project/save, Dash API client, Streamlit project page, archive tests. | Streamlit owns one caller but not the archive format. | SHARED / NOT STREAMLIT-OWNED | core/project_io.py:29,171-; tests/test_project_io.py:1-. Archive round trip is a blocking acceptance item. |
| core/kinetics.py | tests/test_kinetics.py and Streamlit preview page; no Dash consumer found. | Scientific implementation is behind a Streamlit-only preview UI. | SHARED / NOT STREAMLIT-OWNED | core/kinetics.py:1-600; ui/kinetics_page.py:121-468; tests/test_kinetics.py:1-. Decide whether a future Dash surface, CLI/API, or explicit retirement owns the science. |
| core/peak_deconvolution.py | tests/test_peak_deconvolution.py and Streamlit preview page; no Dash consumer found. | Scientific implementation is behind a Streamlit-only preview UI. | SHARED / NOT STREAMLIT-OWNED | core/peak_deconvolution.py:1-310; ui/deconvolution_page.py:43-250; tests/test_peak_deconvolution.py:1-. UI removal cannot silently remove the tested core capability. |
| utils/diagnostics.py | backend.app, Streamlit UI, support/export paths, and diagnostics tests. | Streamlit pages show diagnostics and support information. | SHARED / NOT STREAMLIT-OWNED | utils/diagnostics.py:1-238; backend/app.py:1586-1600; tests/test_backend_workflow.py:1-. Keep support snapshot semantics stable. |
| utils/license_manager.py | Backend/library services, core/reference_library.py, core/preset_store.py, Dash export branding, pyproject.toml version attribute, tests. | Streamlit license page and sidebar badge are major callers. | SHARED / NOT STREAMLIT-OWNED | utils/license_manager.py:1-385; pyproject.toml:54-56; tests/test_license_manager.py:1-. License-page removal requires a replacement activation/write-gating surface. |
| utils/runtime_flags.py | app.py and preview-gating tests/consumers. | Controls Streamlit preview page registration. | SHARED / NOT STREAMLIT-OWNED | utils/runtime_flags.py:8-21; app.py:929-1054. Decide flag ownership before changing preview behavior. |
| core/reference_library.py, core/library_cloud_client.py, core/library_combined_bootstrap.py | Backend library routes, Dash/server bootstrap, report/provenance paths, tests. | Streamlit library page is one UI consumer. | SHARED / NOT STREAMLIT-OWNED | core/reference_library.py:1-1061; core/library_cloud_client.py:1-402; core/library_combined_bootstrap.py:1-135; backend/app.py:667-784; tests/test_reference_library.py:1-; tests/test_library_combined_bootstrap.py:1-. Backend service survival is independent of the Streamlit page. |
| sample_data/ and test_data/ fixtures | Dash sample-data helpers, backend/API tests, core tests, and Streamlit sample buttons. | Streamlit page labels and sample selectors reference them. | SHARED / NOT STREAMLIT-OWNED | dash_app/sample_data.py:1-58; exact 8501 text scan in section 13. Numeric 8501 hits in CSV rows are not framework references. |

## 8. Table F — dependency, deployment, lint, and packaging references

| Surface | Observed reference | Classification | Evidence | Future work / constraint |
| --- | --- | --- | --- | --- |
| requirements.txt | streamlit>=1.39.0 remains a runtime dependency beside Dash/FastAPI/Plotly and ingest/report dependencies. python-dotenv is shared by the Streamlit app and backend/server environment setup; Dash/FastAPI, scientific, and report dependencies are shared or deployment-owned rather than Streamlit-only. | DOCS/PACKAGING/TEST DEBT | requirements.txt:1-37; pyproject.toml:31, 54-56; app.py:25; dash_app/server.py:1- | Owner: removal/installer work package. Do not remove or re-pin it in PR-6. No install-footprint measurement was taken. A dependency removal must follow UI, installer, test, and import reachability decisions. |
| pyproject.toml | Runtime dependencies are dynamically sourced from requirements.txt; package discovery includes backend*, core*, dash_app*, ui*, and utils*. | DOCS/PACKAGING/TEST DEBT | pyproject.toml:23, 31-56 | Owner: removal/installer work package. Package ownership cannot be inferred from the current Dash deployment alone; ui* remains a packaged module. |
| Dockerfile and docker/start.sh | Container installs the shared requirements and starts only the combined Dash server on 8050. | DOCS/PACKAGING/TEST DEBT | Dockerfile:1-; docker/start.sh:1-6; deployment contract tests | Owner: removal/installer work package. This is a positive deployment contract, not Streamlit feature parity; no cleanup is required here by PR-6. |
| vercel.json | Container service points to the root Dockerfile. | DOCS/PACKAGING/TEST DEBT | vercel.json:1-13; tests/test_deployment_contract.py:1- | Owner: removal/installer work package. Keep the single deployment seam while future work changes application ownership, if approved. |
| ruff.toml | Per-file legacy exception for app.py (E402) and duplicate-locale exception for utils/i18n.py (F601); additional UI-specific frozen debt is present. | DOCS/PACKAGING/TEST DEBT | ruff.toml:16-20; ruff check . --output-format concise | Owner: removal/installer work package. Ruff exceptions are signals for a later ownership cleanup, not grounds for source deletion. |
| .github/workflows/ci.yml | Matrix runs Python 3.11/3.12, installs .[dev], runs pip check, full tests, and Ruff. No Streamlit-specific CI job was found. | DOCS/PACKAGING/TEST DEBT | .github/workflows/ci.yml:20-72 | Owner: removal/installer work package. CI coverage does not prove browser parity or Windows installer parity. |
| packaging/windows/ThermoAnalyzerLauncher.spec | Bundles Streamlit data/metadata and hidden imports; includes app.py, ui, utils, samples, hosted/mirror library trees, and guide paths. | DOCS/PACKAGING/TEST DEBT | packaging/windows/ThermoAnalyzerLauncher.spec:33-84 | Owner: removal/installer work package. Reconcile with the installer decision and tracked documentation set in a dedicated work package. |
| packaging/windows/ThermoAnalyzer_Beta.iss, packaging/windows/build_beta_installer.ps1, and packaging/windows/build_beta_installer.bat | The ISS file installs the PyInstaller output and end-user docs; the PowerShell script builds it; the batch file delegates to PowerShell. | DOCS/PACKAGING/TEST DEBT | packaging/windows/ThermoAnalyzer_Beta.iss:45-57; packaging/windows/build_beta_installer.ps1:1-105; packaging/windows/build_beta_installer.bat:1-5 | Owner: removal/installer work package. Preserve the chain until the Windows runtime decision is explicit. |
| packaging/windows/end_user_docs/HELP.html and packaging/windows/end_user_docs/README.txt | Tracked end-user help files tell users that the installer opens a local browser and distinguish stable from preview capabilities. | DOCS/PACKAGING/TEST DEBT | packaging/windows/end_user_docs/HELP.html:1-; packaging/windows/end_user_docs/README.txt:1-; packaging/windows/ThermoAnalyzer_Beta.iss:47-48 | Owner: PR-7 docs pass, coordinated with the removal/installer work package. The files are not Streamlit imports, but their launch and capability claims are product references. |
| package.json / package-lock.json | Desktop/automation metadata; no Streamlit runtime dependency. | DOCS/PACKAGING/TEST DEBT | package.json:1-22; package-lock.json:1-; exact text scan excludes package-lock.json | Owner: removal/installer work package. Not a Streamlit removal target. |

### Runtime package observation

python -m pip check in the inspected environment reports one pre-existing environment mismatch: mitmproxy 12.2.2 requires typing-extensions<=4.14,>=4.13.2 for Python <3.13, while 4.15.0 is installed. No package was changed for PR-6. The repository lint command passes.

## 9. Table G — test inventory and deletion risk

Counts below are pytest --collect-only counts at the inspected revision. A test marked direct may import Streamlit at module import time; a test marked transitive may import utils.i18n, a Streamlit page, or a Streamlit component inside the test body. A framework-neutral test must be retained or relocated before a UI deletion.

| Test file / group | Collected | Streamlit relationship | What it protects | Future removal note |
| --- | ---: | --- | --- | --- |
| tests/test_windows_launcher.py | 1 | Direct source/launcher probe; creates .streamlit config and asserts port/env behavior. | Legacy Windows launcher bootstrap and runtime config. | Rewrite against a replacement installer contract or explicitly archive with the launcher; do not delete as incidental cleanup. |
| tests/test_ui_consistency.py | 9 | Source-text assertions over Streamlit pages, app.py, utils/i18n.py, and shared chrome. | Headers, nav ordering, workflow guides, locale, license/about separation, and themed CSS. | Decide whether each assertion becomes Dash/browser acceptance, shared-core coverage, or a retired legacy contract. |
| tests/test_spectral_page.py | 1 | Direct ui.spectral_page import. | Streamlit spectral helper/page behavior. | Move framework-neutral helper coverage before deleting the Streamlit page. |
| tests/test_xrd_page.py | 25 | Direct ui.xrd_page and ui.components.plot_builder imports. | XRD display, input, plot, and state helper behavior. | Preserve core/XRD artifact tests; replace only UI-specific assertions after Dash acceptance. |
| tests/test_plot_builder.py | 8 | Transitive Streamlit session-state import through ui/components/plot_builder.py. | Plot-builder behavior and state interactions. | Split pure plot builders from session state before changing ownership. |
| tests/test_session_state.py | 4 | Direct utils.session_state import, which imports Streamlit. | Undo/redo snapshots, default state, and session behavior. | Retain pure snapshot tests; add a Dash/workspace state contract before removing session-bound code. |
| tests/test_i18n.py | 3 | Direct utils.i18n import, which imports Streamlit. | Bilingual t/tx and catalog lookup. | This is the first blocking decoupling seam because Dash uses the catalog. |
| tests/test_dash_chrome_i18n.py | 3 | Dash test transitive through dash_app.i18n → utils.i18n. | Locale normalization, Dash labels, theme/locale stores, and root layout. | Must continue to pass in an environment where Streamlit is absent if the legacy dependency is later removed. |
| tests/test_analysis_page_components.py | 41 | Dash component tests transitively import utils.i18n through dash_app.components.analysis_page. | Shared Dash analysis-page, status, metadata, and figure-artifact components. | Keep as Dash-side evidence; the blocked test-collection probe currently reaches utils/i18n.py:5 before these tests can collect without Streamlit. |
| tests/test_literature_compare_panel.py | 32 | Direct Streamlit literature panel import. | Provider status, evidence buckets, and comparison panel rendering helpers. | Preserve service/contract tests and replace UI rendering tests with Dash equivalents where behavior is intended to survive. |
| tests/test_export_report.py | 35 | Imports Streamlit export-page helpers. | CSV/XLSX preview and report helper behavior. | Keep framework-neutral serialization coverage; replace page-helper tests only after export UI acceptance. |
| tests/test_validation.py | 34 | Imports a validation helper from ui.home. | Input validation rules used by import flow. | Move validation to a framework-neutral module before removing the home page. |
| tests/test_ftir_dash_page.py | 47 | Dash page tests import utils.i18n inside test paths. | FTIR Dash callbacks, chrome, results, literature, presets, and state. | Keep as Dash-side parity evidence; remove Streamlit dependency from the translation seam first. |
| tests/test_raman_dash_page.py | 48 | Same transitive translation dependency as FTIR. | Raman Dash callbacks, chrome, results, literature, presets, and state. | Same migration constraint as FTIR. |
| tests/test_xrd_dash_page.py | 33 | Dash page tests import utils.i18n in selected tests. | XRD Dash layout, callbacks, figures, tables, and localized copy. | Keep; exact browser acceptance remains separate. |
| tests/test_dsc_dash_page.py | 37 | Dash page / API tests; no direct Streamlit page dependency. | DSC Dash controls, callback state, results, presets, and figures. | Strong counterpart evidence; augment with browser/default assertions before a legacy removal. |
| tests/test_tga_dash_page.py | 27 | Dash page / API tests; no direct Streamlit page dependency. | TGA Dash controls, workflow, history, results, and presets. | Same. |
| tests/test_dta_dash_page.py | 104 | Dash page tests; file also contains historical “Streamlit” terminology/source assertions. | DTA Dash controls, results, literature, presets, metadata, and chrome. | Retain Dash tests; audit historical names separately from runtime dependency. |
| tests/test_dsc_tga_parity.py | 6 | Framework-neutral/API parity tests. | Single/batch DSC/TGA result contract. | Keep independently of either UI. |
| tests/test_compare_dash_phase2.py | 5 | Dash/backend compare tests. | Curve selection, batch API, and combined app persistence. | Keep; add browser selection/download acceptance if the UI becomes canonical. |
| tests/test_export_dash_page.py | 3 | Dash export page tests. | Branding layout, pending logo feedback, and invalid payload behavior. | Keep and extend only if branding replaces the Streamlit license-page surface. |
| tests/test_backend_exports.py | 15 | Backend/core only. | CSV/XLSX/DOCX/PDF artifact generation, figure warnings, and result payloads. | Framework-neutral; not a Streamlit deletion candidate. |
| tests/test_backend_workflow.py | 13 | Backend/core workflow tests. | Import, run, save/load, compare, figures, and analysis artifacts. | Framework-neutral; preserve before UI changes. |
| tests/test_project_io.py | 3 | Core archive tests. | .scopezip manifest, round trip, and invalid archive errors. | Blocking archive contract; retain. |
| tests/test_backend_workspace.py | 3 | Backend workspace API tests. | Active dataset and comparison selection persistence/validation. | Blocking state contract; retain. |
| tests/test_license_manager.py | 8 | Framework-neutral license service tests. | Activation, trial, write gating, and secret rotation. | Retain even if the Streamlit license page changes. |
| tests/test_reference_library.py | 13 | Core/library service tests. | Reference lookup/catalog behavior. | Retain independently of the Streamlit library page. |
| tests/test_library_combined_bootstrap.py | 5 | Combined Dash server/library bootstrap tests. | Cloud URL/port environment behavior. | Retain; it documents the deployed Dash/library seam. |
| tests/test_literature_compare.py | 75 | Service/core tests. | Literature comparison payloads, providers, diagnostics, and evidence. | Retain independently of either UI. |
| tests/test_backend_api.py | 25 | Backend API tests; “streamlit artifact” is historical product terminology, not a Streamlit import. | Stable navigation/artifact API contracts. | Reword historical names only in a separate cleanup; do not treat them as dependency proof. |
| tests/test_deployment_contract.py | 10 | Source/deployment contract tests; explicitly guards against streamlit run app.py in the container. | Dash container, h11, Vercel, packaging, and asset contracts. | Retain; this is positive Dash evidence and a negative legacy-container guard. |
| tests/test_xrd_processing_draft.py | 9 | Historical/draft helper tests; docstring mentions parity with Streamlit. | XRD draft processing helper behavior. | Keep or reclassify with the XRD work package; no source deletion here. |
| tests/test_kinetics.py | 4 | Core-only tests for the Streamlit preview's scientific backend. | Kinetics algorithms. | Retain until the preview fate is decided. |
| tests/test_peak_deconvolution.py | 2 | Core-only tests for the Streamlit preview's scientific backend. | Deconvolution algorithms. | Retain until the preview fate is decided. |
| tests/test_xrd_display.py, tests/test_xrd_browser_rendering.py, tests/test_tga_explore.py | 4, 1, 7 | Core/Dash helper and rendering tests; no safe Streamlit-only classification. | Formula/display, browser figure, TGA exploration helper behavior. | Retain and use as migration evidence. |
| Plan-referenced missing files: tests/test_library_feed.py, tests/test_dta_page.py | 0 / absent | Not present in the tracked inspected tree. | No test evidence can be claimed for these paths. | Restore, replace, or remove the plan reference in a future test-inventory update; PR-6 does not invent tests. |

### Collection snapshots

- Nine plan-targeted files collected 86 tests.
- The nine plus the five additional direct/transitive UI files (test_export_report, test_validation, test_ftir_dash_page, test_raman_dash_page, test_xrd_dash_page) collected 283 tests.
- The existing named backend/core/Dash group, excluding the two absent plan-referenced files, collected 370 tests.
- Full repository baseline: 1221 passed, 10 skipped, 39 warnings in 500.79 seconds.

### Source-text assertion status

This is the explicit source-text column for the test rows above. **Yes:** tests/test_backend_api.py, tests/test_deployment_contract.py, tests/test_ui_consistency.py, and tests/test_windows_launcher.py read repository source or assert source/config text. **Mixed:** tests/test_dta_dash_page.py has one historical source read and historical Streamlit wording among otherwise Dash tests. **No:** every other test file/group listed in Table G, including tests/test_xrd_processing_draft.py; those tests exercise helpers, callbacks, APIs, artifacts, or core behavior rather than asserting Streamlit source text.

## 10. Table H — documentation and text references

This table records both actionable legacy references and neutral/historical references. A text match is not automatically a runtime dependency: the 8501 scan also matches numeric values in data fixtures.

| Reference | Location / observed text | Classification | Handling in PR-6 / evidence anchor |
| --- | --- | --- | --- |
| Streamlit app command and docstring | app.py:1-6 documents streamlit run app.py; app.py:11 imports Streamlit. | DOCS/PACKAGING/TEST DEBT | app.py:1-6,11; Owner: PR-7 docs pass. Recorded; no edit. |
| Streamlit page registration and preview gate | app.py:929-1054 contains the toggle, 15 st.Page( objects, and preview gating. | DOCS/PACKAGING/TEST DEBT | app.py:929-1054; Owner: removal/installer work package. Used as the route source of truth; no edit. |
| Windows launch model | packaging/windows/README.md:16 says the launcher starts Streamlit and opens the default browser. | DOCS/PACKAGING/TEST DEBT | packaging/windows/README.md:16; Owner: PR-7 docs pass, coordinated with removal/installer work package. Recorded; no edit. |
| Windows launcher source | packaging/windows/launcher.py:3, 18, 57-78, 90-116 describes/uses the Streamlit architecture and port/config behavior. | DOCS/PACKAGING/TEST DEBT | packaging/windows/launcher.py:3,18,57-78,90-116; Owner: removal/installer work package. Cross-referenced in Tables A and F; no edit. |
| Windows release preparation | packaging/windows/RELEASE_PREP_LOCAL.md:30 describes validating the browser shortcut; the surrounding release notes are tied to the legacy launcher. | DOCS/PACKAGING/TEST DEBT | packaging/windows/RELEASE_PREP_LOCAL.md:30; Owner: PR-7 docs pass, coordinated with removal/installer work package. Recorded for packaging review; no edit. |
| Windows PyInstaller spec | packaging/windows/ThermoAnalyzerLauncher.spec:46-65 collects Streamlit data/metadata and hidden imports; :33-44 bundles source and guide paths. | DOCS/PACKAGING/TEST DEBT | packaging/windows/ThermoAnalyzerLauncher.spec:33-65; Owner: removal/installer work package. Recorded; missing-path reconciliation is future work. |
| Windows build chain | packaging/windows/ThermoAnalyzer_Beta.iss, packaging/windows/build_beta_installer.ps1, and packaging/windows/build_beta_installer.bat form the tracked installer build chain. | DOCS/PACKAGING/TEST DEBT | packaging/windows/ThermoAnalyzer_Beta.iss:1-57; packaging/windows/build_beta_installer.ps1:1-105; packaging/windows/build_beta_installer.bat:1-5; Owner: removal/installer work package. The batch wrapper, PowerShell build, and Inno Setup file must be considered together. |
| Windows bundled end-user docs | packaging/windows/end_user_docs/HELP.html and packaging/windows/end_user_docs/README.txt describe browser launch, stable beta areas, and preview areas. | DOCS/PACKAGING/TEST DEBT | packaging/windows/end_user_docs/HELP.html:1-; packaging/windows/end_user_docs/README.txt:1-; Owner: PR-7 docs pass, coordinated with removal/installer work package. These are tracked product references even though they contain no Streamlit import. |
| Windows spec data roots | packaging/windows/ThermoAnalyzerLauncher.spec:39-40 references build/reference_library_hosted and build/reference_library_mirror_live; no tracked build paths were found. | DOCS/PACKAGING/TEST DEBT | packaging/windows/ThermoAnalyzerLauncher.spec:39-40; Owner: removal/installer work package. Record the absent/ignored build inputs; do not restore them in PR-6. |
| Ruff legacy exceptions | ruff.toml:16-20 marks the legacy Streamlit entrypoint and duplicate locale catalog. | DOCS/PACKAGING/TEST DEBT | ruff.toml:16-20; Owner: removal/installer work package. Recorded; no lint configuration change. |
| Shared session docstring | utils/session_state.py:1 identifies shared Streamlit session state. | SHARED / NOT STREAMLIT-OWNED | utils/session_state.py:1; Recorded with the pure-helper/state split in Tables D and E. |
| Dash translation wrapper | dash_app/i18n.py:1-15 is a thin wrapper over utils.i18n; text scan also finds Dash translation keys in related components/pages. | SHARED / NOT STREAMLIT-OWNED | dash_app/i18n.py:1-15; utils/i18n.py:5,3852-3904; Recorded as the import-decoupling blocker. |
| Dash page text references | dash_app/pages/dta.py, dash_app/pages/xrd.py, dash_app/components/spectral_explore.py, dash_app/components/tga_explore.py, and dash_app/components/xrd_processing_draft.py contain historical parity/draft/Streamlit wording. | DOCS/PACKAGING/TEST DEBT | dash_app/pages/dta.py:1-; dash_app/pages/xrd.py:1-; dash_app/components/spectral_explore.py:1-; dash_app/components/tga_explore.py:1-; dash_app/components/xrd_processing_draft.py:1-; Owner: PR-7 docs pass. Text is not treated as proof of a Streamlit runtime import; no rewording in PR-6. |
| Electron fallback/reference text | desktop/electron/renderer.js:483-488 says Streamlit remains untouched as a fallback/reference. desktop/electron/index.html is returned by the broad text scan through product/runtime wording. | DOCS/PACKAGING/TEST DEBT | desktop/electron/renderer.js:483-488; desktop/electron/index.html:1-; Owner: PR-7 docs pass, coordinated with removal/installer work package. Recorded; Electron is not counted as a Dash page. |
| Desktop backend bundle docs | desktop/backend_bundle/README.md and desktop/backend_bundle/build_backend.py describe the independent backend-only PyInstaller bundle. | DOCS/PACKAGING/TEST DEBT | desktop/backend_bundle/README.md:1-; desktop/backend_bundle/build_backend.py:1-; Owner: removal/installer work package. This bundle is not a Streamlit UI and remains a separate desktop distribution concern. |
| Requirements and deployment files | requirements.txt, Dockerfile, docker/start.sh, and vercel.json contain framework/port/runtime terms. | DOCS/PACKAGING/TEST DEBT | requirements.txt:1-37; Dockerfile:1-; docker/start.sh:1-6; vercel.json:1-13; Owner: removal/installer work package. Split in Table F; no dependency or deployment edit. |
| Backend/API terminology | tests/test_backend_api.py contains streamlit_artifact test names; tests/test_deployment_contract.py explicitly checks that the container does not run Streamlit. | DOCS/PACKAGING/TEST DEBT | tests/test_backend_api.py:1-; tests/test_deployment_contract.py:1-; Owner: removal/installer work package. Historical naming and positive Dash guard are distinguished; no test edit. |
| Dash DTA test wording | tests/test_dta_dash_page.py contains historical references to Streamlit in test descriptions. | DOCS/PACKAGING/TEST DEBT | tests/test_dta_dash_page.py:1-; Owner: PR-7 docs pass. Retain as provenance; no runtime implication. |
| UI source assertions | tests/test_ui_consistency.py asserts exact Streamlit source structure; tests/test_windows_launcher.py asserts Streamlit config/bootstrap. | DOCS/PACKAGING/TEST DEBT | tests/test_ui_consistency.py:1-; tests/test_windows_launcher.py:1-; Owner: removal/installer work package. Future removal must deliberately replace or retire these assertions. |
| XRD draft test wording | tests/test_xrd_processing_draft.py:1 says “parity with Streamlit”. | DOCS/PACKAGING/TEST DEBT | tests/test_xrd_processing_draft.py:1; Owner: PR-7 docs pass. Recorded; no edit. |
| Numeric fixture false positives | sample_data/dsc_multirate_kissinger.csv, sample_data/raman_cnt_figshare.csv, sample_data/xrd_2024_0304_zenodo.csv, sample_data/xrd_2024_1613_zenodo.csv, test_data/dsc_PET_amorphous_10Kmin.csv, test_data/dta_tnaa_2p5c_mendeley.csv, test_data/dta_tnaa_7p5c_mendeley.csv, test_data/raman_cnt_figshare_sparse.csv, test_data/xrd_2024_0303_zenodo.csv, test_data/xrd_2024_1784_zenodo.csv, and test_data/xrd_2024_2097_zenodo.csv match the broad scan because data rows contain 8501. | SHARED / NOT STREAMLIT-OWNED | sample_data/dsc_multirate_kissinger.csv:1-; sample_data/raman_cnt_figshare.csv:1-; sample_data/xrd_2024_0304_zenodo.csv:1-; sample_data/xrd_2024_1613_zenodo.csv:1-; test_data/dsc_PET_amorphous_10Kmin.csv:1-; test_data/dta_tnaa_2p5c_mendeley.csv:1-; test_data/dta_tnaa_7p5c_mendeley.csv:1-; test_data/raman_cnt_figshare_sparse.csv:1-; test_data/xrd_2024_0303_zenodo.csv:1-; test_data/xrd_2024_1784_zenodo.csv:1-; test_data/xrd_2024_2097_zenodo.csv:1-; broad scan output in section 13. These fixtures are used by tests/Dash/sample flows; no framework reference and no edit. |
| Tracked documentation absence | .streamlit/config.toml, PROFESOR_KURULUM_VE_KULLANIM_KILAVUZU.md, PROFESSOR_SETUP_AND_USAGE_GUIDE.md, PROFESSOR_BETA_GUIDE.md, and docs/scout-report.md return no tracked paths from git ls-files at the inspected revision. | DOCS/PACKAGING/TEST DEBT | `git ls-files .streamlit/config.toml PROFESOR_KURULUM_VE_KULLANIM_KILAVUZU.md PROFESSOR_SETUP_AND_USAGE_GUIDE.md PROFESSOR_BETA_GUIDE.md docs/scout-report.md` (no output); docs/scout-report.md:1-; Owner: removal/installer work package for config/guides; PR-7 docs pass for docs/scout-report.md. The worktree has untracked planning copies of some paths. They are not restored, deleted, or silently counted as committed product docs. |
| Roadmap reference | docs/roadmap.md is an existing untracked planning file with the Phase 0 PR-6 row and the legacy-stack inventory scope. | DOCS/PACKAGING/TEST DEBT | docs/roadmap.md:1-; Owner: PR-7 docs pass. It was preserved and not edited; its untracked status is recorded in the evidence appendix. |
| Current Dash-only docs | README.md and README.tr.md describe the combined Dash server; docs/early-tester-guide.md is neutral and does not authorize removal. | DOCS/PACKAGING/TEST DEBT | README.md:1-64; README.tr.md:1-64; docs/early-tester-guide.md:1-116; Owner: PR-7 docs pass. No change; these documents are evidence of the current deployed web path, not a parity sign-off. |

### Exact broad text-scan coverage

The following is the complete tracked-file result of:

    git grep -l -i -E 'streamlit|_stcore|\.streamlit|st\.set_page_config|st\.navigation|8501' -- . ':!package-lock.json'

Every result is assigned to a row in Tables A, D, E, F, G, or H. The CSV rows are explicitly classified as numeric false positives.

    app.py
    core/data_io.py
    dash_app/components/spectral_explore.py
    dash_app/components/tga_explore.py
    dash_app/components/xrd_processing_draft.py
    dash_app/i18n.py
    dash_app/pages/dta.py
    dash_app/pages/xrd.py
    desktop/electron/index.html
    desktop/electron/renderer.js
    packaging/windows/README.md
    packaging/windows/ThermoAnalyzerLauncher.spec
    packaging/windows/launcher.py
    requirements.txt
    ruff.toml
    sample_data/dsc_multirate_kissinger.csv
    sample_data/raman_cnt_figshare.csv
    sample_data/xrd_2024_0304_zenodo.csv
    sample_data/xrd_2024_1613_zenodo.csv
    test_data/dsc_PET_amorphous_10Kmin.csv
    test_data/dta_tnaa_2p5c_mendeley.csv
    test_data/dta_tnaa_7p5c_mendeley.csv
    test_data/raman_cnt_figshare_sparse.csv
    test_data/xrd_2024_0303_zenodo.csv
    test_data/xrd_2024_1784_zenodo.csv
    test_data/xrd_2024_2097_zenodo.csv
    tests/test_backend_api.py
    tests/test_deployment_contract.py
    tests/test_dta_dash_page.py
    tests/test_ui_consistency.py
    tests/test_windows_launcher.py
    tests/test_xrd_processing_draft.py
    ui/about_page.py
    ui/compare_page.py
    ui/components/chrome.py
    ui/components/column_mapper.py
    ui/components/data_preview.py
    ui/components/history_tracker.py
    ui/components/literature_compare_panel.py
    ui/components/preset_manager.py
    ui/components/quality_dashboard.py
    ui/components/workflow_guide.py
    ui/deconvolution_page.py
    ui/dsc_page.py
    ui/dta_page.py
    ui/export_page.py
    ui/home.py
    ui/kinetics_page.py
    ui/library_page.py
    ui/license_page.py
    ui/project_page.py
    ui/spectral_page.py
    ui/tga_page.py
    ui/xrd_page.py
    utils/i18n.py
    utils/session_state.py

## 11. Findings count and boundary

These are inventory counts, not a deletion checklist:

- Across the classified rows in Tables A-H: PARITY_CONFIRMED 0; PARTIAL_PARITY 75; NO_DASH_EQUIVALENT 6; SHARED / NOT STREAMLIT-OWNED 21 (including 4 streamlit-bearing shared-module rows); DOCS/PACKAGING/TEST DEBT 38. The zero confirmed rows is intentional: no user-facing row met every strict parity condition in the evidence collected here.
- 15 Streamlit st.Page( declarations: 13 stable, 2 preview-gated.
- 11 Dash page registrations.
- 4 Streamlit pages with no Dash page counterpart: Library, License, Kinetics preview, Deconvolution preview.
- 1 confirmed transitive Dash import blocker: utils/i18n.py imports Streamlit; dash_app.i18n, dash_app.layout, and Dash page imports fail in a Streamlit-blocked probe.
- 1 additional Streamlit-bound state module: utils/session_state.py.
- 0 tracked .streamlit config files.
- 5 requested guide/config paths absent from the tracked tree at the inspected revision.
- 2 plan-referenced test paths absent from the tracked tree.
- 1 Windows installer launch path still tied to Streamlit.

The inventory does not assert that Streamlit and Dash are visually identical. It records where source and tests are strong enough to establish shared behavior and where an explicit delta or runtime acceptance step remains.

## 12. Removal prerequisites recorded for future work

The following items are deliberately recorded as gates, not implemented changes. “Blocking” means a Streamlit removal or installer retarget would be unsafe without the item.

1. **Blocking — decouple utils/i18n.py from Streamlit.** Move or split the catalog and locale normalization so importing the Dash shell does not require Streamlit. Preserve Turkish/English keys and test both framework contexts.
2. **Blocking — decide the four no-counterpart pages.** Resolve Library, License/branding activation, Kinetics preview, and Deconvolution preview as replacement Dash surfaces, retained legacy surfaces, external/admin surfaces, or explicitly retired capabilities.
3. **Blocking — decide the Windows path.** Retire the Streamlit launcher or retarget the installer to Dash/FastAPI, then update shortcuts, ports, user data roots, config seeding, browser opening, and installer tests together.
4. **Blocking — relocate framework-neutral tests before deletion.** Move validation, plot builders, session snapshots, and any science helpers out of Streamlit-owned modules; decide which source-text assertions become Dash/browser contracts.
5. **Blocking — close user-impacting partial deltas.** At minimum compare the tr versus en defaults, license badge/write gating, preview toggle, export/report controls, branding, and analysis-specific options/defaults.
6. **Should-have — clean packaging in dependency order.** Only after runtime ownership is decided should requirements, package discovery, Ruff exceptions, PyInstaller hidden imports, and installer docs be changed.
7. **Should-have — perform the docs pass.** Reconcile legacy launch instructions, Windows release notes, guide links, and historical wording in a dedicated documentation change.
8. **Decision required — define state semantics.** Specify how st.session_state state maps to Dash stores/backend workspace, including active dataset, undo/redo, recent history, comparison selection, and archive round trip.
9. **Decision required — resolve unique plot builders.** Decide whether Kinetics, multirate, and deconvolution builders in ui/components/plot_builder.py move to core/Dash or are explicitly retired with their tests and scientific behavior.
10. **Should-have — require a roadmap approval gate.** A future removal work package should link this inventory, list every accepted delta, and obtain explicit approval before deleting or retargeting legacy files.

## 13. Evidence appendix

Unless a subsection says otherwise, command output below was collected against source revision 17ee1017003554768435999821f118e855387f78.

### 13.1 Baseline and versions

    git rev-parse HEAD
    17ee1017003554768435999821f118e855387f78

    git log -1 --oneline --decorate
    17ee101 (HEAD -> main) PR-5: Security trio — archive hardening, license-secret hygiene, bind warning + client token sync

    python --version
    Python 3.12.8

    python package versions
    dash 4.4.1
    dash-bootstrap-components 2.0.4
    fastapi 0.134.0
    kaleido 1.2.0
    plotly 6.5.2
    streamlit 1.54.0

### 13.2 Direct Streamlit imports

Command:

    git grep -n -E '^\s*(import streamlit|from streamlit)' -- '*.py'

Observed output:

    app.py:11:import streamlit as st
    packaging/windows/launcher.py:18:import streamlit.web.bootstrap as bootstrap
    ui/about_page.py:5:import streamlit as st
    ui/compare_page.py:9:import streamlit as st
    ui/components/chrome.py:5:import streamlit as st
    ui/components/column_mapper.py:3:import streamlit as st
    ui/components/data_preview.py:3:import streamlit as st
    ui/components/history_tracker.py:10:import streamlit as st
    ui/components/literature_compare_panel.py:12:import streamlit as st
    ui/components/preset_manager.py:5:import streamlit as st
    ui/components/quality_dashboard.py:9:import streamlit as st
    ui/components/workflow_guide.py:5:import streamlit as st
    ui/deconvolution_page.py:3:import streamlit as st
    ui/dsc_page.py:4:import streamlit as st
    ui/dta_page.py:11:import streamlit as st
    ui/export_page.py:8:import streamlit as st
    ui/home.py:6:import streamlit as st
    ui/kinetics_page.py:3:import streamlit as st
    ui/library_page.py:6:import streamlit as st
    ui/license_page.py:5:import streamlit as st
    ui/project_page.py:8:import streamlit as st
    ui/spectral_page.py:10:import streamlit as st
    ui/tga_page.py:11:import streamlit as st
    ui/xrd_page.py:11:import streamlit as st
    utils/i18n.py:5:import streamlit as st
    utils/session_state.py:7:import streamlit as st

### 13.3 Route maps

Streamlit route source from git grep -n -E 'st.Page( or url_path= in app.py:

    import        -> ui/home.py
    project       -> ui/project_page.py
    compare       -> ui/compare_page.py
    report        -> ui/export_page.py
    dsc           -> ui/dsc_page.py
    tga           -> ui/tga_page.py
    dta           -> ui/dta_page.py
    ftir          -> ui/ftir_page.py
    raman         -> ui/raman_page.py
    xrd           -> ui/xrd_page.py
    library       -> ui/library_page.py
    license       -> ui/license_page.py
    about         -> ui/about_page.py
    kinetics      -> ui/kinetics_page.py (preview gate)
    deconvolution -> ui/deconvolution_page.py (preview gate)

Dash registrations:

    /          -> dash_app/pages/home.py
    /project   -> dash_app/pages/project.py
    /export    -> dash_app/pages/export.py
    /compare   -> dash_app/pages/compare.py
    /dsc       -> dash_app/pages/dsc.py
    /tga       -> dash_app/pages/tga.py
    /dta       -> dash_app/pages/dta.py
    /ftir      -> dash_app/pages/ftir.py
    /raman     -> dash_app/pages/raman.py
    /xrd       -> dash_app/pages/xrd.py
    /about     -> dash_app/pages/about.py

### 13.4 Widget-density spot check

The plan's st. line-count probe is reproduced on Windows with the same file set and descending sort. The count is the number of source lines containing st., not the number of widget occurrences.

Command:

    $files=@('app.py') + @(rg --files ui -g '*.py' | ForEach-Object {$_ -replace '\\','/'})
    $rows=foreach($f in $files) {
      [pscustomobject]@{n=$f;c=@(Select-String -LiteralPath $f -Pattern 'st\.' 2>$null).Count}
    }
    $rows | Sort-Object @{Expression='c';Descending=$true},@{Expression='n';Descending=$false} |
      ForEach-Object { '{0,6}  {1}' -f $_.c,$_.n }

Observed output:

       147  ui/xrd_page.py
       113  ui/dsc_page.py
        98  ui/tga_page.py
        91  ui/dta_page.py
        90  ui/components/literature_compare_panel.py
        89  ui/export_page.py
        89  ui/project_page.py
        84  ui/kinetics_page.py
        83  ui/spectral_page.py
        67  ui/home.py
        63  ui/compare_page.py
        46  ui/library_page.py
        42  app.py
        41  ui/deconvolution_page.py
        40  ui/license_page.py
        23  ui/components/preset_manager.py
        21  ui/components/data_preview.py
        19  ui/components/column_mapper.py
        18  ui/about_page.py
        10  ui/components/history_tracker.py
         9  ui/components/workflow_guide.py
         2  ui/components/quality_dashboard.py
         1  ui/components/chrome.py
         0  ui/__init__.py
         0  ui/components/__init__.py
         0  ui/components/plot_builder.py
         0  ui/ftir_page.py
         0  ui/raman_page.py

The zero-count wrappers and plot_builder are still part of the file-set evidence; ui/ftir_page.py and ui/raman_page.py reach ui/spectral_page.py, which is the shared Streamlit implementation.

### 13.5 Streamlit-blocked import probes

The authoritative probe starts a fresh subprocess for every target module and sets sys.modules["streamlit"] = None inside that subprocess before importing it. The final combined-app call is also isolated. SHA: 17ee1017003554768435999821f118e855387f78.

Command:

    @'
    import re
    import subprocess
    import sys

    modules = [
        'utils.i18n', 'utils.session_state', 'dash_app.i18n', 'dash_app.layout',
        'dash_app.app', 'dash_app.server', 'backend.app', 'core.plotting', 'core.figure_render',
        'dash_app.pages.about', 'dash_app.pages.compare', 'dash_app.pages.dsc',
        'dash_app.pages.dta', 'dash_app.pages.export', 'dash_app.pages.ftir',
        'dash_app.pages.home', 'dash_app.pages.project', 'dash_app.pages.raman',
        'dash_app.pages.tga', 'dash_app.pages.xrd',
    ]
    child = """
    import importlib, sys, traceback
    sys.modules['streamlit'] = None
    try:
        importlib.import_module(sys.argv[1])
    except Exception as exc:
        print(type(exc).__name__ + ': ' + str(exc)[:120])
        traceback.print_exc()
        raise SystemExit(1)
    print('OK')
    """
    def first_streamlit_frame(stderr):
        frames = [line.strip() for line in stderr.splitlines()
                  if line.strip().startswith('File ') and 'MaterialScope' in line]
        for line in frames:
            if 'utils\\i18n.py' in line or 'utils/i18n.py' in line:
                return 'utils/i18n.py:5'
            if 'utils\\session_state.py' in line or 'utils/session_state.py' in line:
                return 'utils/session_state.py:7'
        return frames[-1] if frames else 'no repository frame'
    for module in modules:
        result = subprocess.run([sys.executable, '-c', child, module],
                                capture_output=True, text=True)
        if result.returncode == 0:
            print(f'OK       {module}')
        else:
            message = result.stdout.strip().splitlines()[0] if result.stdout.strip() else 'unknown error'
            print(f'BLOCKED  {module} -> {message} | first Streamlit-bearing frame: {first_streamlit_frame(result.stderr)}')
    combined = """
    import sys
    sys.modules['streamlit'] = None
    from dash_app.server import create_combined_app
    create_combined_app()
    """
    result = subprocess.run([sys.executable, '-c', combined],
                            capture_output=True, text=True)
    if result.returncode == 0:
        print('OK       combined_app')
    else:
        message = next((line.strip() for line in result.stderr.splitlines()
                        if line.strip().startswith('ModuleNotFoundError')
                        or line.strip().startswith('ImportError')), 'unknown error')
        print(f'BLOCKED  combined_app -> {message} | first Streamlit-bearing frame: {first_streamlit_frame(result.stderr)}')
    '@ | python -

Observed output:

    BLOCKED  utils.i18n -> ModuleNotFoundError: import of streamlit halted; None in sys.modules | first Streamlit-bearing frame: utils/i18n.py:5
    BLOCKED  utils.session_state -> ModuleNotFoundError: import of streamlit halted; None in sys.modules | first Streamlit-bearing frame: utils/session_state.py:7
    BLOCKED  dash_app.i18n -> ModuleNotFoundError: import of streamlit halted; None in sys.modules | first Streamlit-bearing frame: utils/i18n.py:5
    BLOCKED  dash_app.layout -> ModuleNotFoundError: import of streamlit halted; None in sys.modules | first Streamlit-bearing frame: utils/i18n.py:5
    OK       dash_app.app
    OK       dash_app.server
    OK       backend.app
    OK       core.plotting
    OK       core.figure_render
    BLOCKED  dash_app.pages.about -> ModuleNotFoundError: import of streamlit halted; None in sys.modules | first Streamlit-bearing frame: utils/i18n.py:5
    BLOCKED  dash_app.pages.compare -> ModuleNotFoundError: import of streamlit halted; None in sys.modules | first Streamlit-bearing frame: utils/i18n.py:5
    BLOCKED  dash_app.pages.dsc -> ModuleNotFoundError: import of streamlit halted; None in sys.modules | first Streamlit-bearing frame: utils/i18n.py:5
    BLOCKED  dash_app.pages.dta -> ModuleNotFoundError: import of streamlit halted; None in sys.modules | first Streamlit-bearing frame: utils/i18n.py:5
    BLOCKED  dash_app.pages.export -> ModuleNotFoundError: import of streamlit halted; None in sys.modules | first Streamlit-bearing frame: utils/i18n.py:5
    BLOCKED  dash_app.pages.ftir -> ModuleNotFoundError: import of streamlit halted; None in sys.modules | first Streamlit-bearing frame: utils/i18n.py:5
    BLOCKED  dash_app.pages.home -> ModuleNotFoundError: import of streamlit halted; None in sys.modules | first Streamlit-bearing frame: utils/i18n.py:5
    BLOCKED  dash_app.pages.project -> ModuleNotFoundError: import of streamlit halted; None in sys.modules | first Streamlit-bearing frame: utils/i18n.py:5
    BLOCKED  dash_app.pages.raman -> ModuleNotFoundError: import of streamlit halted; None in sys.modules | first Streamlit-bearing frame: utils/i18n.py:5
    BLOCKED  dash_app.pages.tga -> ModuleNotFoundError: import of streamlit halted; None in sys.modules | first Streamlit-bearing frame: utils/i18n.py:5
    BLOCKED  dash_app.pages.xrd -> ModuleNotFoundError: import of streamlit halted; None in sys.modules | first Streamlit-bearing frame: utils/i18n.py:5
    BLOCKED  combined_app -> ModuleNotFoundError: import of streamlit halted; None in sys.modules | first Streamlit-bearing frame: utils/i18n.py:5

The bare-import successes for dash_app.app and dash_app.server are deliberately not promoted to runtime independence: page/layout construction is lazy enough that the blocked layout and all eleven Dash page imports expose the transitive dependency. The full combined application is blocked at utils/i18n.py:5.

### 13.6 Shared-module reachability

All commands in this appendix were run against the inspected source revision 17ee1017003554768435999821f118e855387f78.

Command:

    git grep -n -E '^\s*(from|import)\s+(ui|utils\.session_state|utils\.i18n)\b' -- backend core dash_app tools scripts desktop generate_test_data.py

Observed output:

    dash_app/components/analysis_boilerplate.py:12:from utils.i18n import translate_ui
    dash_app/components/analysis_page.py:17:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/components/figure_artifacts.py:14:from utils.i18n import translate_ui
    dash_app/components/literature_compare_ui.py:11:from utils.i18n import translate_ui
    dash_app/components/page_guidance.py:10:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/components/raw_quality.py:10:from utils.i18n import translate_ui
    dash_app/components/spectral_explore.py:11:from utils.i18n import translate_ui
    dash_app/components/spectral_plot_settings.py:13:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/components/tga_explore.py:15:from utils.i18n import translate_ui
    dash_app/components/xrd_result_plot.py:11:from utils.i18n import translate_ui
    dash_app/i18n.py:11:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/pages/about.py:10:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/pages/compare.py:22:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/pages/dsc.py:88:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/pages/dta.py:86:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/pages/export.py:25:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/pages/ftir.py:115:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/pages/home.py:29:from utils.i18n import TRANSLATIONS, normalize_ui_locale, translate_ui
    dash_app/pages/project.py:20:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/pages/raman.py:115:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/pages/tga.py:93:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/pages/xrd.py:90:from utils.i18n import normalize_ui_locale, translate_ui

Command:

    git grep -n -E '^\s*(from|import)\s+utils\.' -- backend core dash_app

Observed output (all hits):

    backend/app.py:124:from utils.diagnostics import get_default_log_file, serialize_support_snapshot
    backend/app.py:125:from utils.license_manager import APP_VERSION, commercial_mode_enabled, load_license_state
    backend/library_cloud_service.py:33:from utils.license_manager import APP_VERSION, get_storage_dir, validate_encoded_license_key
    backend/library_feed.py:11:from utils.license_manager import APP_VERSION, validate_encoded_license_key
    core/library_cloud_client.py:12:from utils.license_manager import (
    core/preset_store.py:12:from utils.license_manager import get_storage_dir
    core/provenance.py:8:from utils.reference_data import evaluate_reference_check
    core/reference_library.py:24:from utils.license_manager import encode_license_key, get_storage_dir
    core/report_generator.py:27:from utils.reference_data import find_nearest_reference
    dash_app/components/analysis_boilerplate.py:12:from utils.i18n import translate_ui
    dash_app/components/analysis_page.py:17:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/components/figure_artifacts.py:14:from utils.i18n import translate_ui
    dash_app/components/literature_compare_ui.py:11:from utils.i18n import translate_ui
    dash_app/components/page_guidance.py:10:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/components/raw_quality.py:10:from utils.i18n import translate_ui
    dash_app/components/spectral_explore.py:11:from utils.i18n import translate_ui
    dash_app/components/spectral_plot_settings.py:13:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/components/tga_explore.py:15:from utils.i18n import translate_ui
    dash_app/components/tga_explore.py:16:from utils.reference_data import find_nearest_reference
    dash_app/components/xrd_result_plot.py:11:from utils.i18n import translate_ui
    dash_app/i18n.py:11:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/pages/about.py:10:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/pages/compare.py:22:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/pages/dsc.py:88:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/pages/dta.py:86:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/pages/export.py:25:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/pages/export.py:26:from utils.license_manager import APP_VERSION, commercial_mode_enabled, license_allows_write, load_license_state
    dash_app/pages/ftir.py:115:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/pages/home.py:29:from utils.i18n import TRANSLATIONS, normalize_ui_locale, translate_ui
    dash_app/pages/project.py:20:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/pages/raman.py:115:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/pages/tga.py:93:from utils.i18n import normalize_ui_locale, translate_ui
    dash_app/pages/xrd.py:90:from utils.i18n import normalize_ui_locale, translate_ui

Command:

    git grep -n -E '^\s*(from|import)\s+utils\.' -- app.py ui

Observed output (all hits):

    app.py:15:from utils.diagnostics import configure_diagnostics_logger
    app.py:16:from utils.i18n import SUPPORTED_LANGUAGES, t, tx
    app.py:17:from utils.license_manager import (
    app.py:22:from utils.runtime_flags import preview_modules_enabled
    app.py:23:from utils.session_state import ensure_session_state, get_ui_theme
    ui/about_page.py:8:from utils.i18n import t, tx
    ui/compare_page.py:18:from utils.diagnostics import make_error_id, record_diagnostic_event, record_exception
    ui/compare_page.py:19:from utils.i18n import t, tx
    ui/compare_page.py:20:from utils.license_manager import APP_VERSION
    ui/components/column_mapper.py:6:from utils.i18n import tx
    ui/components/data_preview.py:6:from utils.i18n import tx
    ui/components/literature_compare_panel.py:17:from utils.diagnostics import record_exception
    ui/components/plot_builder.py:11:from utils.session_state import get_ui_theme
    ui/components/preset_manager.py:17:from utils.i18n import tx
    ui/components/preset_manager.py:18:from utils.session_state import advance_analysis_render_revision
    ui/components/quality_dashboard.py:11:from utils.i18n import tx
    ui/components/workflow_guide.py:7:from utils.i18n import tx
    ui/deconvolution_page.py:17:from utils.i18n import tx
    ui/dsc_page.py:32:from utils.diagnostics import record_exception
    ui/dsc_page.py:33:from utils.i18n import t, tx
    ui/dsc_page.py:34:from utils.license_manager import APP_VERSION
    ui/dsc_page.py:35:from utils.reference_data import render_reference_comparison
    ui/dsc_page.py:36:from utils.session_state import (
    ui/dta_page.py:34:from utils.reference_data import render_reference_comparison
    ui/dta_page.py:35:from utils.i18n import t, tx
    ui/dta_page.py:36:from utils.session_state import (
    ui/export_page.py:20:from utils.diagnostics import record_exception, serialize_support_snapshot
    ui/export_page.py:21:from utils.i18n import t
    ui/export_page.py:22:from utils.license_manager import APP_VERSION, license_allows_write
    ui/home.py:16:from utils.diagnostics import record_exception
    ui/home.py:17:from utils.i18n import t, tx
    ui/home.py:18:from utils.session_state import ensure_session_state
    ui/kinetics_page.py:13:from utils.license_manager import APP_VERSION
    ui/library_page.py:11:from utils.i18n import tx
    ui/license_page.py:8:from utils.i18n import t
    ui/license_page.py:9:from utils.license_manager import (
    ui/project_page.py:13:from utils.diagnostics import record_exception
    ui/project_page.py:14:from utils.i18n import t
    ui/project_page.py:15:from utils.license_manager import license_allows_write
    ui/project_page.py:16:from utils.session_state import clear_project_state, replace_project_state
    ui/spectral_page.py:32:from utils.i18n import t, tx
    ui/spectral_page.py:33:from utils.license_manager import APP_VERSION
    ui/tga_page.py:41:from utils.diagnostics import record_exception
    ui/tga_page.py:42:from utils.i18n import t, tx
    ui/tga_page.py:43:from utils.license_manager import APP_VERSION
    ui/tga_page.py:44:from utils.reference_data import render_reference_comparison
    ui/tga_page.py:45:from utils.session_state import (
    ui/xrd_page.py:41:from utils.diagnostics import record_exception
    ui/xrd_page.py:42:from utils.i18n import t, tx
    ui/xrd_page.py:43:from utils.license_manager import APP_VERSION

Command:

    git grep -h -o -E '^\s*from core\.[a-z_]+' -- app.py ui | sort | uniq -c | sort -rn

Observed result:

    result_serialization 8; validation 7; processing_schema 6; batch_runner 4; provenance 3; modalities 3; preprocessing 3; peak_analysis 2; baseline 2; data_io 2; reference_library 2; project_io 2; tga_processor 1; report_generator 1; axis_labels 1; peak_deconvolution 1; literature_partitioning 1; library_cloud_client 1; kinetics 1; dta_processor 1; dsc_processor 1; chemical_formula_formatting 1; preset_store 1; xrd_display 1.

The exact direct importer lists for the UI components and the two Streamlit-bearing utils modules are in section 6.1. The non-Streamlit hits above are the evidence for the shared-module rows in Table E.

### 13.7 Blocked test collection

Command:

    python -c "import sys, subprocess; code = \"import sys; sys.modules['streamlit']=None; import pytest; sys.exit(pytest.main(['-q','--co','tests']))\"; r = subprocess.run([sys.executable,'-c',code], capture_output=True, text=True); print(r.stdout[-4000:]); print(r.stderr[-2000:])"

Observed result:

    returncode 2
    ERROR tests/test_analysis_page_components.py
    ERROR tests/test_dash_chrome_i18n.py
    ERROR tests/test_export_report.py
    ERROR tests/test_i18n.py
    ERROR tests/test_literature_compare_panel.py
    ERROR tests/test_plot_builder.py
    ERROR tests/test_session_state.py
    ERROR tests/test_spectral_page.py
    ERROR tests/test_tga_explore.py
    ERROR tests/test_validation.py
    ERROR tests/test_xrd_page.py
    1038 tests collected, 11 errors in 8.43s

First Streamlit-bearing collection frames:

    tests/test_analysis_page_components.py -> dash_app/components/analysis_page.py -> utils/i18n.py:5
    tests/test_dash_chrome_i18n.py -> dash_app/i18n.py -> utils/i18n.py:5
    tests/test_export_report.py -> ui/export_page.py:8
    tests/test_i18n.py -> utils/i18n.py:5
    tests/test_literature_compare_panel.py -> ui/components/literature_compare_panel.py:12
    tests/test_plot_builder.py -> ui/components/plot_builder.py -> utils/session_state.py:7
    tests/test_session_state.py -> utils/session_state.py:7
    tests/test_spectral_page.py -> ui/spectral_page.py:10
    tests/test_tga_explore.py -> dash_app/components/tga_explore.py -> utils/i18n.py:5
    tests/test_validation.py -> ui/home.py:6
    tests/test_xrd_page.py -> ui/components/plot_builder.py -> utils/session_state.py:7

### 13.8 Test collection and validation

    python -m pytest tests/test_windows_launcher.py tests/test_ui_consistency.py tests/test_spectral_page.py tests/test_xrd_page.py tests/test_plot_builder.py tests/test_session_state.py tests/test_i18n.py tests/test_dash_chrome_i18n.py tests/test_literature_compare_panel.py --collect-only -q
    86 tests collected in 3.39s

    python -m pytest tests/test_windows_launcher.py tests/test_ui_consistency.py tests/test_spectral_page.py tests/test_xrd_page.py tests/test_plot_builder.py tests/test_session_state.py tests/test_i18n.py tests/test_dash_chrome_i18n.py tests/test_literature_compare_panel.py -q
    86 passed in 7.23s

    python -m pytest tests/ -q --tb=short -rf
    1221 passed, 10 skipped, 39 warnings in 500.79s (0:08:20)

    ruff check . --output-format concise
    All checks passed!

    python -m pip check
    mitmproxy 12.2.2 has requirement typing-extensions<=4.14,>=4.13.2; python_version < "3.13", but you have typing-extensions 4.15.0.

The pip check mismatch is in the host environment and was not introduced or repaired by this documentation-only change.

### 13.9 Missing tracked paths and worktree boundary

    git ls-files .streamlit "PROFESOR_KURULUM_VE_KULLANIM_KILAVUZU.md" "PROFESSOR_SETUP_AND_USAGE_GUIDE.md" "PROFESSOR_BETA_GUIDE.md" "docs/scout-report.md"
    (no output)

The three untracked planning files were pre-existing user work. They were preserved and are not counted as tracked product files in the evidence above.

### 13.10 Packaging, deployment, desktop, and feature-extraction probes

SHA for the commands in this subsection: 17ee1017003554768435999821f118e855387f78.

Commands:

    git grep -n -i streamlit -- requirements.txt pyproject.toml Dockerfile docker/start.sh vercel.json ruff.toml .github/workflows package.json
    git grep -n -i -E 'streamlit|app\.py|8501|dash_app|backend' -- packaging/windows/launcher.py packaging/windows/*.spec packaging/windows/*.iss packaging/windows/*.ps1 packaging/windows/*.bat packaging/windows/*.md packaging/windows/end_user_docs/*
    git ls-files packaging/windows/end_user_docs
    git grep -n -i -E 'streamlit|8501|browser' -- packaging/windows/end_user_docs/*
    git grep -n -i -E 'streamlit|8501|dash_app|backend\.main|uvicorn' -- desktop/electron
    git grep -n -E 'tree_as_datas\(|collect_(data_files|submodules)\(' -- packaging/windows/ThermoAnalyzerLauncher.spec

Observed result (raw command output):

    requirements.txt:1:streamlit>=1.39.0
    ruff.toml:16:## --- Legacy Streamlit entrypoint (retirement tracked in roadmap) ---
    packaging/windows/README.md:16:- Launch model: local launcher that starts Streamlit and opens the default browser
    packaging/windows/ThermoAnalyzerLauncher.spec:34:datas += tree_as_datas("app.py")
    packaging/windows/ThermoAnalyzerLauncher.spec:46:datas += collect_data_files("streamlit")
    packaging/windows/ThermoAnalyzerLauncher.spec:50:datas += copy_metadata("streamlit")
    packaging/windows/ThermoAnalyzerLauncher.spec:62:hiddenimports += collect_submodules("streamlit")
    packaging/windows/build_beta_installer.ps1:105:        "_internal\\app.py"
    packaging/windows/launcher.py:3:This keeps the current Streamlit architecture intact:
    packaging/windows/launcher.py:18:import streamlit.web.bootstrap as bootstrap
    packaging/windows/launcher.py:23:PREFERRED_PORT = 8501
    packaging/windows/launcher.py:58:    """Create writable runtime directories and seed Streamlit config."""
    packaging/windows/launcher.py:61:    user_streamlit_dir = user_root / ".streamlit"
    packaging/windows/launcher.py:62:    user_streamlit_dir.mkdir(parents=True, exist_ok=True)
    packaging/windows/launcher.py:65:    _assert_writable_directory(user_streamlit_dir)
    packaging/windows/launcher.py:67:    bundled_config = resource_root / ".streamlit" / "config.toml"
    packaging/windows/launcher.py:68:    target_config = user_streamlit_dir / "config.toml"
    packaging/windows/launcher.py:74:    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    packaging/windows/launcher.py:78:    """Pick a local TCP port, preferring 8501 for familiarity."""
    packaging/windows/launcher.py:92:    app_script = resource_root / "app.py"
    packaging/windows/launcher.py:95:            f"{APP_NAME} could not locate app.py inside the packaged runtime.\n\n"
    packaging/windows/end_user_docs/HELP.html
    packaging/windows/end_user_docs/README.txt
    desktop/electron/backend_locator.js:26:      args: ["-m", "backend.main"],
    desktop/electron/index.html:1154:              <li>Streamlit fallback/reference implementation olarak dokunulmadan korunur.</li>
    desktop/electron/renderer.js:483:          "<li>Streamlit fallback/reference implementation olarak dokunulmadan korunur.</li>",
    desktop/electron/renderer.js:488:          "<li>Streamlit remains available as untouched fallback/reference implementation.</li>",
    desktop/electron/scripts/test-backend-locator.js:15:  assert.deepStrictEqual(launch.args, ["-m", "backend.main"]);
    packaging/windows/ThermoAnalyzerLauncher.spec:18:def tree_as_datas(relative_path: str):
    packaging/windows/ThermoAnalyzerLauncher.spec:34:datas += tree_as_datas("app.py")
    packaging/windows/ThermoAnalyzerLauncher.spec:35:datas += tree_as_datas("core")
    packaging/windows/ThermoAnalyzerLauncher.spec:36:datas += tree_as_datas("ui")
    packaging/windows/ThermoAnalyzerLauncher.spec:37:datas += tree_as_datas("utils")
    packaging/windows/ThermoAnalyzerLauncher.spec:38:datas += tree_as_datas("sample_data")
    packaging/windows/ThermoAnalyzerLauncher.spec:39:datas += tree_as_datas("build/reference_library_hosted")
    packaging/windows/ThermoAnalyzerLauncher.spec:40:datas += tree_as_datas("build/reference_library_mirror_live")
    packaging/windows/ThermoAnalyzerLauncher.spec:41:datas += tree_as_datas("README.md")
    packaging/windows/ThermoAnalyzerLauncher.spec:42:datas += tree_as_datas("PROFESOR_KURULUM_VE_KULLANIM_KILAVUZU.md")
    packaging/windows/ThermoAnalyzerLauncher.spec:43:datas += tree_as_datas("PROFESSOR_SETUP_AND_USAGE_GUIDE.md")
    packaging/windows/ThermoAnalyzerLauncher.spec:44:datas += tree_as_datas("PROFESSOR_BETA_GUIDE.md")
    packaging/windows/ThermoAnalyzerLauncher.spec:46:datas += collect_data_files("streamlit")
    packaging/windows/ThermoAnalyzerLauncher.spec:47:datas += collect_data_files("plotly")
    packaging/windows/ThermoAnalyzerLauncher.spec:48:datas += collect_data_files("kaleido")
    packaging/windows/ThermoAnalyzerLauncher.spec:49:datas += collect_data_files("reportlab")
    packaging/windows/ThermoAnalyzerLauncher.spec:62:hiddenimports += collect_submodules("streamlit")
    packaging/windows/ThermoAnalyzerLauncher.spec:63:hiddenimports += collect_submodules("plotly")
    packaging/windows/ThermoAnalyzerLauncher.spec:64:hiddenimports += collect_submodules("kaleido")
    packaging/windows/ThermoAnalyzerLauncher.spec:65:hiddenimports += collect_submodules("reportlab")

Interpretation:

    The raw output shows the tracked Streamlit runtime and Windows launcher remain in the dependency and installer surfaces. It also shows the Electron bundle has explicit fallback/reference wording, while the end-user-doc grep itself returns no literal Streamlit/8501/browser match.

The end_user_docs grep returns no literal Streamlit/8501/browser match in the tracked files, but their content is still a product reference: HELP.html and README.txt state that the local program opens in a browser and distinguish stable from preview capabilities. The two reference-library build directories and three professor-guide paths have no tracked source entries at this revision.

Feature-level extraction used the plan's source patterns with the concrete page map below. It reports widget counts, every Dash callback decorator line, and every Dash API-import site for all fifteen Streamlit page objects.

Command:

    $control = 'st\.(button|download_button|file_uploader|selectbox|multiselect|slider|number_input|text_input|text_area|toggle|checkbox|radio|tabs|expander|form|data_editor|dataframe|plotly_chart|segmented_control|page_link)\('
    $pairs = @(
      @{n='home';s=@('ui/home.py');d='dash_app/pages/home.py'},
      @{n='project';s=@('ui/project_page.py');d='dash_app/pages/project.py'},
      @{n='compare';s=@('ui/compare_page.py');d='dash_app/pages/compare.py'},
      @{n='export';s=@('ui/export_page.py');d='dash_app/pages/export.py'},
      @{n='dsc';s=@('ui/dsc_page.py');d='dash_app/pages/dsc.py'},
      @{n='tga';s=@('ui/tga_page.py');d='dash_app/pages/tga.py'},
      @{n='dta';s=@('ui/dta_page.py');d='dash_app/pages/dta.py'},
      @{n='ftir';s=@('ui/ftir_page.py','ui/spectral_page.py');d='dash_app/pages/ftir.py'},
      @{n='raman';s=@('ui/raman_page.py','ui/spectral_page.py');d='dash_app/pages/raman.py'},
      @{n='xrd';s=@('ui/xrd_page.py');d='dash_app/pages/xrd.py'},
      @{n='about';s=@('ui/about_page.py');d='dash_app/pages/about.py'},
      @{n='library';s=@('ui/library_page.py');d=$null},
      @{n='license';s=@('ui/license_page.py');d=$null},
      @{n='kinetics';s=@('ui/kinetics_page.py');d=$null},
      @{n='deconvolution';s=@('ui/deconvolution_page.py');d=$null}
    )
    foreach($p in $pairs) {
      Write-Output "[$($p.n)]"
      $hits=@(); foreach($f in $p.s) {$hits += @(rg -n -o $control $f 2>$null)}
      $counts=@{}; foreach($h in $hits) {if($h -match 'st\.([a-z_]+)\(') {$k=$matches[1]; if(!$counts.ContainsKey($k)) {$counts[$k]=0}; $counts[$k]++}}
      $sout=if($counts.Count) {($counts.GetEnumerator() | Sort-Object Name | ForEach-Object {"$($_.Name)=$($_.Value)"}) -join ', '} else {'none matched'}
      Write-Output "S widgets: $sout"
      if($p.d) {
        $cb=@(rg -n '^@callback' $p.d 2>$null)
        $ai=@(rg -n 'from dash_app\.api_client import|from dash_app import api_client' $p.d 2>$null)
        Write-Output ("D @callback lines: " + (($cb | ForEach-Object {($_ -split ':')[0]}) -join ', '))
        Write-Output ("D API import lines: " + (($ai | ForEach-Object {($_ -split ':')[0]}) -join ', '))
      } else {Write-Output 'D: no page/callback/API counterpart'}
    }

Observed output:

    [home]
    S widgets: button=4, expander=1, file_uploader=1, plotly_chart=1, selectbox=1, tabs=1
    D @callback lines: 533, 620, 634, 666, 709, 746, 786, 808, 926, 1102, 1184, 1342, 1403, 1467, 1483, 1507
    D API import lines: 1270, 1376, 1428, 1477, 1498, 1532
    [project]
    S widgets: button=8, dataframe=2, download_button=1, file_uploader=1, tabs=1
    D @callback lines: 165, 196, 217, 227, 248, 404, 496, 627, 649
    D API import lines: 268, 426, 547, 608
    [compare]
    S widgets: button=2, dataframe=3, multiselect=1, plotly_chart=1, segmented_control=2, selectbox=2, text_area=1
    D @callback lines: 137, 203, 241, 258, 279, 296, 326, 378
    D API import lines: 218, 269, 312, 350, 412
    [export]
    S widgets: button=5, checkbox=1, dataframe=3, download_button=4, expander=1, multiselect=1, selectbox=2, tabs=1
    D @callback lines: 294, 329, 376, 696, 706, 734, 751, 777, 790, 836, 860, 914, 982, 1031
    D API import lines: 401, 765, 807, 894, 943, 1010, 1062
    [dsc]
    S widgets: button=8, checkbox=4, dataframe=1, expander=1, number_input=8, plotly_chart=7, selectbox=5, slider=6, tabs=1
    D @callback lines: 1023, 1063, 1078, 1103, 1113, 1151, 1178, 1207, 1226, 1241, 1278, 1303, 1328, 1403, 1434, 1464, 1474, 1534, 1587, 1622, 1635, 1719, 1734, 1756, 1770, 1779, 1788, 1811, 1829, 1851, 1878, 1899, 1920, 2042, 2051, 2082, 2113, 2131, 2150, 2200, 2346, 2378, 2386, 2462, 2472, 2482, 2504, 2576
    D API import lines: 1126, 1341, 1415, 1441, 1491, 1550, 1600, 2179, 2235, 2412, 2450, 2493, 2534, 2949, 3027
    [tga]
    S widgets: button=6, checkbox=2, dataframe=1, expander=1, number_input=2, plotly_chart=4, selectbox=5, slider=6, tabs=1
    D @callback lines: 639, 689, 704, 748, 777, 817, 847, 858, 939, 1011, 1050, 1077, 1101, 1161, 1173, 1198, 1208, 1218, 1233, 1263, 1278, 1291, 1319, 1350, 1393, 1522, 1554, 1562, 1634, 1644, 1654, 1676, 1748
    D API import lines: 824, 879, 957, 1025, 1244, 1331, 1371, 1438, 1588, 1622, 1665, 1706, 2156, 2261
    [dta]
    S widgets: button=7, checkbox=4, dataframe=1, number_input=6, plotly_chart=6, selectbox=4, slider=6, tabs=1
    D @callback lines: 1295, 1333, 1353, 1378, 1388, 1426, 1454, 1485, 1496, 1554, 1603, 1639, 1670, 1725, 2567, 2613, 2637, 2652, 2674, 2720, 2806, 2866, 2912, 2934, 2948, 2972, 2994, 3018, 3044, 3076, 3084, 3157, 3167, 3177, 3199, 3288
    D API import lines: 1401, 1462, 1512, 1569, 1615, 1651, 1699, 1771, 2193, 2470, 3110, 3145, 3188, 3229, 3312
    [ftir]
    S widgets: button=1, checkbox=11, dataframe=3, expander=2, number_input=8, plotly_chart=3, selectbox=7, slider=4, tabs=1
    D @callback lines: 866, 904, 919, 944, 954, 989, 1042, 1113, 1149, 1178, 1208, 1219, 1295, 1366, 1405, 1418, 1475, 1494, 1522, 1549, 1571, 1590, 1620, 1635, 1647, 1661, 1729, 1780, 1846, 1863, 1909, 2067, 2099, 2107, 2179, 2189, 2199, 2221, 2298
    D API import lines: 966, 1125, 1185, 1239, 1312, 1380, 1883, 1958, 2133, 2167, 2210, 2251, 2515, 2863
    [raman]
    S widgets: button=1, checkbox=11, dataframe=3, expander=2, number_input=8, plotly_chart=3, selectbox=7, slider=4, tabs=1
    D @callback lines: 871, 909, 924, 949, 959, 994, 1047, 1118, 1154, 1183, 1213, 1224, 1300, 1371, 1410, 1423, 1480, 1499, 1527, 1554, 1576, 1595, 1625, 1640, 1652, 1666, 1734, 1785, 1851, 1868, 1914, 2072, 2104, 2112, 2184, 2194, 2204, 2226, 2303
    D API import lines: 971, 1130, 1190, 1244, 1317, 1385, 1888, 1963, 2138, 2172, 2215, 2256, 2520, 2868
    [xrd]
    S widgets: button=6, checkbox=11, dataframe=5, expander=3, number_input=13, plotly_chart=4, selectbox=7, slider=13, tabs=1
    D @callback lines: 716, 754, 769, 794, 804, 846, 875, 892, 945, 970, 999, 1028, 1039, 1104, 1156, 1189, 1202, 1222, 1241, 1379, 1387, 1397, 1498, 1652, 1712, 1724, 2172, 2323, 2394, 2420, 2425, 2473, 2484, 2494, 2518, 2631
    D API import lines: 817, 857, 905, 1006, 1059, 1121, 1170, 1743, 1788, 2116, 2203, 2345, 2445, 2505, 2558
    [about]
    S widgets: tabs=1
    D @callback lines: 270
    D API import lines:
    [library]
    S widgets: dataframe=4, tabs=1
    D: no page/callback/API counterpart
    [license]
    S widgets: button=2, file_uploader=1, form=2, tabs=1, text_area=2, text_input=4
    D: no page/callback/API counterpart
    [kinetics]
    S widgets: button=4, dataframe=2, multiselect=2, number_input=14, plotly_chart=3, radio=1, selectbox=2, tabs=1
    D: no page/callback/API counterpart
    [deconvolution]
    S widgets: button=2, checkbox=2, dataframe=1, expander=3, number_input=4, plotly_chart=3, selectbox=3, slider=1
    D: no page/callback/API counterpart

The resulting per-page controls, callbacks, backend endpoint families, tests, and concrete deltas are recorded in Table B. No browser-level parity claim is inferred from this static extraction.

## 14. PR-6 change boundary

Changed by this implementation:

- Added docs/streamlit-parity-inventory.md.

Not changed:

- app.py, ui/, packaging/windows/, Streamlit modules, dependencies, Docker/deployment files, tests, README files, and runtime flags.
- Existing untracked docs/index.html, docs/roadmap.md, and docs/scout-report.md.

No removal, warning, feature flag, dependency cleanup, installer retarget, or parity claim beyond the evidence in this document was made.
