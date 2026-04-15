"""Central UI strings for Dash chrome (navigation, shared labels).

Extend ``MESSAGES`` with new keys; pages can import ``t`` when they need locale-aware copy.
"""

from __future__ import annotations

from typing import Final

DEFAULT_LOCALE: Final[str] = "en"
SUPPORTED_LOCALES: Final[tuple[str, ...]] = ("en", "tr")

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "app.tagline": "Multimodal materials characterization workbench",
        "nav.section_primary": "Primary",
        "nav.section_analysis": "Analysis",
        "nav.section_management": "Management",
        "nav.import": "Import",
        "nav.project": "Project",
        "nav.report": "Report",
        "nav.compare": "Compare",
        "nav.dsc": "DSC",
        "nav.tga": "TGA",
        "nav.dta": "DTA",
        "nav.ftir": "FTIR",
        "nav.raman": "RAMAN",
        "nav.xrd": "XRD",
        "nav.about": "About",
        "sidebar.history_title": "Recent History",
        "sidebar.history_empty": "No history yet.",
        "ui.theme_hint": "Color theme",
        "ui.theme_use_light": "Use light theme",
        "ui.theme_use_dark": "Use dark theme",
        "ui.theme_current_light": "Light",
        "ui.theme_current_dark": "Dark",
        "ui.language": "Language",
    },
    "tr": {
        "app.tagline": "Çok modlu malzeme karakterizasyon çalışma alanı",
        "nav.section_primary": "Ana",
        "nav.section_analysis": "Analiz",
        "nav.section_management": "Yönetim",
        "nav.import": "İçe aktar",
        "nav.project": "Proje",
        "nav.report": "Rapor",
        "nav.compare": "Karşılaştır",
        "nav.dsc": "DSC",
        "nav.tga": "TGA",
        "nav.dta": "DTA",
        "nav.ftir": "FTIR",
        "nav.raman": "RAMAN",
        "nav.xrd": "XRD",
        "nav.about": "Hakkında",
        "sidebar.history_title": "Son Geçmiş",
        "sidebar.history_empty": "Henüz geçmiş yok.",
        "ui.theme_hint": "Renk teması",
        "ui.theme_use_light": "Açık temayı kullan",
        "ui.theme_use_dark": "Koyu temayı kullan",
        "ui.theme_current_light": "Açık",
        "ui.theme_current_dark": "Koyu",
        "ui.language": "Dil",
    },
}


def normalize_locale(locale: str | None) -> str:
    if not locale:
        return DEFAULT_LOCALE
    loc = str(locale).lower().split("-", 1)[0]
    return loc if loc in SUPPORTED_LOCALES else DEFAULT_LOCALE


def t(locale: str | None, key: str) -> str:
    loc = normalize_locale(locale)
    return MESSAGES.get(loc, MESSAGES[DEFAULT_LOCALE]).get(
        key,
        MESSAGES[DEFAULT_LOCALE].get(key, key),
    )
