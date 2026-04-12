"""Project workspace overview page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.project_io import PROJECT_EXTENSION, load_project_archive, save_project_archive
from core.result_serialization import split_valid_results
from ui.components.chrome import render_page_header
from utils.diagnostics import record_exception
from utils.i18n import t
from utils.license_manager import license_allows_write
from utils.session_state import clear_project_state, replace_project_state


def render():
    render_page_header(t("project.title"), t("project.caption"), badge=t("project.hero_badge"))
    lang = st.session_state.get("ui_language", "tr")

    datasets = st.session_state.get("datasets", {})
    valid_results, issues = split_valid_results(st.session_state.get("results", {}))
    figures = st.session_state.get("figures", {}) or {}
    workspace = st.session_state.get("comparison_workspace", {}) or {}

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Veri Seti" if lang == "tr" else "Datasets", str(len(datasets)))
    m2.metric("Kayıtlı Sonuç" if lang == "tr" else "Saved Results", str(len(valid_results)))
    m3.metric("Görsel" if lang == "tr" else "Figures", str(len(figures)))
    m4.metric("Geçmiş Adımı" if lang == "tr" else "History Steps", str(len(st.session_state.get("analysis_history", []))))

    overview_tab, actions_tab = st.tabs(
        [
            "Çalışma Alanı Özeti" if lang == "tr" else "Workspace Summary",
            "Proje İşlemleri" if lang == "tr" else "Project Actions",
        ]
    )

    with overview_tab:
        if datasets:
            st.subheader("Yüklenen Koşular" if lang == "tr" else "Loaded Runs")
            dataset_rows = []
            for key, dataset in datasets.items():
                dataset_rows.append(
                    {
                        ("Anahtar" if lang == "tr" else "Key"): key,
                        ("Tip" if lang == "tr" else "Type"): dataset.data_type,
                        "Vendor": dataset.metadata.get("vendor", "Generic"),
                        ("Numune" if lang == "tr" else "Sample"): dataset.metadata.get("sample_name") or ("Adsız" if lang == "tr" else "Unnamed"),
                        ("Isıtma Hızı" if lang == "tr" else "Heating Rate"): dataset.metadata.get("heating_rate") or "—",
                        ("Nokta" if lang == "tr" else "Points"): len(dataset.data),
                    }
                )
            st.dataframe(pd.DataFrame(dataset_rows), width="stretch", hide_index=True)

        if valid_results:
            st.subheader("Kayıtlı Sonuç Kayıtları" if lang == "tr" else "Saved Result Records")
            result_rows = []
            for record in valid_results.values():
                result_rows.append(
                    {
                        "ID": record["id"],
                        ("Tip" if lang == "tr" else "Type"): record["analysis_type"],
                        ("Durum" if lang == "tr" else "Status"): record["status"],
                        ("Veri Seti" if lang == "tr" else "Dataset"): record.get("dataset_key") or "—",
                        ("Satır" if lang == "tr" else "Rows"): len(record.get("rows", [])),
                    }
                )
            st.dataframe(pd.DataFrame(result_rows), width="stretch", hide_index=True)

        if workspace.get("selected_datasets"):
            st.subheader("Karşılaştırma Alanı" if lang == "tr" else "Comparison Workspace")
            st.write(f"**{'Tip' if lang == 'tr' else 'Type'}:** {workspace.get('analysis_type', 'N/A')}")
            st.write(f"**{'Seçili koşular' if lang == 'tr' else 'Selected runs'}:** {', '.join(workspace['selected_datasets'])}")
            if workspace.get("figure_key"):
                st.write(f"**{'Kaydedilen görsel' if lang == 'tr' else 'Saved figure'}:** {workspace['figure_key']}")
            if workspace.get("notes"):
                st.write(f"**{'Notlar' if lang == 'tr' else 'Notes'}**")
                st.write(workspace["notes"])

        if issues:
            st.warning("Bazı sonuç kayıtları eksik; export sırasında atlanacak." if lang == "tr" else "Some result records are incomplete and will be skipped from exports.")
            for issue in issues:
                st.caption(f"- {issue}")

    with actions_tab:
        st.info(t("project.sidebar_hint"))
        action_col1, action_col2 = st.columns(2)

        with action_col1:
            if st.button(t("sidebar.project.new"), key="project_new_page"):
                clear_project_state()
                st.rerun()

            has_project_data = bool(datasets or valid_results)
            can_write = license_allows_write(st.session_state.get("license_state"))
            if st.button(
                t("sidebar.project.prepare"),
                key="project_prepare_page",
                disabled=not has_project_data or not can_write,
                help="Build the archive first, then download it explicitly.",
            ):
                try:
                    st.session_state["project_archive_bytes"] = save_project_archive(st.session_state)
                    st.session_state["project_archive_ready"] = True
                    st.success("Proje arşivi hazırlandı." if lang == "tr" else "Project archive prepared.")
                except Exception as exc:
                    error_id = record_exception(
                        st.session_state,
                        area="project_load",
                        action="project_prepare",
                        message="Preparing project archive failed.",
                        context={"dataset_count": len(datasets)},
                        exception=exc,
                    )
                    st.error(f"Project archive preparation failed: {exc} (Error ID: {error_id})")

            if st.session_state.get("project_archive_ready") and st.session_state.get("project_archive_bytes"):
                st.download_button(
                    t("sidebar.project.download"),
                    data=st.session_state["project_archive_bytes"],
                    file_name=f"materialscope_project{PROJECT_EXTENSION}",
                    mime="application/zip",
                    key="project_save_page",
                    on_click="ignore",
                )
            elif not has_project_data:
                st.caption("Önce veri veya sonuç oluştur." if lang == "tr" else "Create datasets or results first.")

        with action_col2:
            uploaded_project = st.file_uploader(
                t("sidebar.project.load"),
                type=[PROJECT_EXTENSION.lstrip(".")],
                key="project_loader_page",
                help="Load a previously saved MaterialScope project archive.",
            )
            if uploaded_project is not None and st.button(t("sidebar.project.load_selected"), key="project_load_btn_page"):
                try:
                    project_state = load_project_archive(uploaded_project)
                    replace_project_state(project_state)
                    st.success("Project loaded." if lang != "tr" else "Proje yüklendi.")
                    st.rerun()
                except Exception as exc:
                    error_id = record_exception(
                        st.session_state,
                        area="project_load",
                        action="project_load",
                        message="Loading project archive failed.",
                        context={"file_name": getattr(uploaded_project, "name", "")},
                        exception=exc,
                    )
                    st.error(f"Project load failed: {exc} (Error ID: {error_id})")

