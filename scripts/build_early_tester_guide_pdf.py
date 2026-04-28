from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "early-tester-guide.pdf"
FORM_URL = (
    "https://docs.google.com/forms/d/e/"
    "1FAIpQLSc02aKo4FFWcmXqgznLtCK0P-sNIygD9PXybNiODP1A4UENxw/viewform"
)

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN_X = 18 * mm
MARGIN_TOP = 18 * mm
MARGIN_BOTTOM = 16 * mm

INK = colors.HexColor("#111111")
MUTED = colors.HexColor("#555555")
LINE = colors.HexColor("#D0D0D0")
PANEL = colors.HexColor("#F7F7F7")


def styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title",
            parent=base["Title"],
            fontName="Times-Bold",
            fontSize=24,
            leading=29,
            textColor=INK,
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=11.5,
            leading=16,
            textColor=INK,
            alignment=TA_CENTER,
            spaceAfter=18,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="Times-Roman",
            fontSize=9.3,
            leading=13.4,
            textColor=INK,
            spaceAfter=6,
        ),
        "body_small": ParagraphStyle(
            "BodySmall",
            parent=base["BodyText"],
            fontName="Times-Roman",
            fontSize=8.8,
            leading=12.2,
            textColor=INK,
            spaceAfter=5,
        ),
        "muted": ParagraphStyle(
            "Muted",
            parent=base["BodyText"],
            fontName="Times-Roman",
            fontSize=8.6,
            leading=12,
            textColor=MUTED,
        ),
        "section": ParagraphStyle(
            "Section",
            parent=base["Heading1"],
            fontName="Times-Bold",
            fontSize=13.5,
            leading=17,
            textColor=INK,
            spaceBefore=8,
            spaceAfter=7,
        ),
        "subsection": ParagraphStyle(
            "Subsection",
            parent=base["Heading2"],
            fontName="Times-Bold",
            fontSize=10.3,
            leading=13,
            textColor=INK,
            spaceBefore=2,
            spaceAfter=4,
        ),
        "callout": ParagraphStyle(
            "Callout",
            parent=base["BodyText"],
            fontName="Times-Roman",
            fontSize=9,
            leading=12.8,
            textColor=INK,
        ),
        "footer": ParagraphStyle(
            "Footer",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=7.5,
            textColor=MUTED,
        ),
        "link": ParagraphStyle(
            "Link",
            parent=base["BodyText"],
            fontName="Times-Roman",
            fontSize=8.7,
            leading=12,
            textColor=INK,
            wordWrap="CJK",
        ),
    }


def bullet_list(items: list[str], style: ParagraphStyle) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(item, style), leftIndent=10) for item in items],
        bulletType="bullet",
        start="circle",
        leftIndent=14,
        bulletFontName="Times-Roman",
        bulletFontSize=5,
        bulletColor=INK,
    )


def numbered_list(items: list[str], style: ParagraphStyle) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(item, style), leftIndent=13) for item in items],
        bulletType="1",
        leftIndent=16,
        bulletFontName="Times-Bold",
        bulletFontSize=8.5,
        bulletColor=INK,
    )


def section_card(title: str, items: list[str], s: dict[str, ParagraphStyle]) -> list:
    return [
        Paragraph(title, s["subsection"]),
        bullet_list(items, s["body_small"]),
    ]


def draw_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.4)
    canvas.line(MARGIN_X, 12 * mm, PAGE_WIDTH - MARGIN_X, 12 * mm)
    canvas.setFont("Times-Roman", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN_X, 7.5 * mm, "MaterialScope - Early Tester Guide")
    canvas.drawRightString(
        PAGE_WIDTH - MARGIN_X,
        7.5 * mm,
        f"Page {doc.page}",
    )
    canvas.restoreState()


def cover(s: dict[str, ParagraphStyle]) -> list:
    flow = [Spacer(1, 24 * mm)]
    flow.extend(
        [
            Paragraph("MaterialScope — Early Tester Guide", s["title"]),
            Paragraph("Early feedback round for materials characterization workflows", s["subtitle"]),
            Spacer(1, 6 * mm),
            Table(
                [
                    [
                        Paragraph(
                            "MaterialScope is an early-stage software platform designed to make "
                            "materials characterization workflows more organized, reproducible, "
                            "and practical.",
                            s["callout"],
                        )
                    ]
                ],
                colWidths=[PAGE_WIDTH - 2 * MARGIN_X - 12 * mm],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), PANEL),
                        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                        ("LEFTPADDING", (0, 0), (-1, -1), 12),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                        ("TOPPADDING", (0, 0), (-1, -1), 10),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                    ]
                ),
            ),
            Spacer(1, 15 * mm),
            Table(
                [[Paragraph("XRD", s["subsection"]), Paragraph("FTIR", s["subsection"]), Paragraph("Raman", s["subsection"])],
                 [Paragraph("DSC", s["subsection"]), Paragraph("TGA", s["subsection"]), Paragraph("DTA", s["subsection"])]],
                colWidths=[42 * mm, 42 * mm, 42 * mm],
                rowHeights=[14 * mm, 14 * mm],
                style=TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ]
                ),
                hAlign="CENTER",
            ),
            Spacer(1, 18 * mm),
            PageBreak(),
        ]
    )
    return flow


def build_story() -> list:
    s = styles()
    story = cover(s)

    story.extend(
        [
            Paragraph("What is MaterialScope?", s["section"]),
            Paragraph(
                "MaterialScope supports workflows around XRD, FTIR, Raman, DSC, TGA, and DTA. "
                "The goal is to reduce fragmentation between vendor software, spreadsheets, plotting "
                "tools, database or library tools, and separate reporting documents.",
                s["body"],
            ),
            Paragraph(
                "It is intended to help users keep data, processing decisions, visualizations, "
                "comparisons, and report outputs closer together in one workflow.",
                s["body"],
            ),
            Paragraph("What problem is it trying to solve?", s["section"]),
            Paragraph("Characterization workflows often require users to:", s["body"]),
            bullet_list(
                [
                    "Import data in different formats",
                    "Clean or reorganize data manually",
                    "Plot results in separate tools",
                    "Compare multiple samples manually",
                    "Export figures for reports, presentations, or papers",
                    "Keep track of different project files",
                    "Move between vendor software, Excel, Origin, Python, and reporting tools",
                ],
                s["body"],
            ),
            Paragraph(
                "MaterialScope aims to bring these steps into a cleaner and more reproducible workflow. "
                "This testing round is focused on whether that direction is practical for real "
                "characterization work.",
                s["body"],
            ),
            Spacer(1, 4 * mm),
            Paragraph("What should testers focus on?", s["section"]),
        ]
    )

    cards = [
        [section_card("General usability", [
            "Is the interface understandable?",
            "Is the workflow clear?",
            "Do you understand what each section is for?",
            "Does anything feel confusing or unnecessary?",
        ], s),
         section_card("Scientific usefulness", [
            "Would this help with real characterization work?",
            "Are the plots useful?",
            "Are important analysis steps missing?",
            "Does the workflow match how researchers or lab users actually work?",
        ], s)],
        [section_card("Data workflow", [
            "Is importing or working with data clear?",
            "Is sample comparison useful?",
            "Are export options practical?",
            "Would this help reduce manual work?",
        ], s),
         section_card("Visual quality", [
            "Are the plots clean enough for reports, presentations, or publications?",
            "Do the figures feel scientific and professional?",
            "What would make them better?",
        ], s)],
    ]
    story.append(
        Table(
            cards,
            colWidths=[(PAGE_WIDTH - 2 * MARGIN_X - 8 * mm) / 2] * 2,
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), PANEL),
                    ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.white),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            ),
        )
    )
    story.append(PageBreak())

    story.extend(
        [
            Paragraph("Suggested 10-minute testing flow", s["section"]),
            numbered_list(
                [
                    "Open MaterialScope.",
                    "Explore the main interface.",
                    "Try one characterization workflow, preferably XRD, FTIR, Raman, DSC, TGA, or DTA.",
                    "Import or inspect sample data if available.",
                    "Check the plot and visualization quality.",
                    "Try sample comparison if available.",
                    "Check export or report-related options.",
                    "Note anything confusing, missing, broken, or scientifically weak.",
                    "Fill out the feedback form.",
                ],
                s["body"],
            ),
            Paragraph("What kind of feedback is most useful?", s["section"]),
            Paragraph(
                "Honest critical feedback is preferred over general praise. Specific comments are the "
                "most helpful because they point directly to workflow, scientific, or usability issues "
                "that can be improved.",
                s["body"],
            ),
            bullet_list(
                [
                    '"This workflow is confusing because..."',
                    '"This feature would not be useful in a real lab because..."',
                    '"For XRD, FTIR, or TGA analysis, this step is missing..."',
                    '"The plot should include..."',
                    '"I would expect this export option..."',
                    '"This would be more useful if..."',
                ],
                s["body"],
            ),
            Paragraph("Known limitations", s["section"]),
            Paragraph(
                "MaterialScope is still early-stage. Some features may be incomplete, experimental, "
                "or not fully polished. The goal of this testing round is not to evaluate a finished "
                "commercial product, but to understand whether the workflow direction is useful for "
                "real users.",
                s["body"],
            ),
            Paragraph(
                "Please focus on workflow logic, scientific usefulness, missing features, confusing "
                "parts, usability problems, plot and report quality, and real-world applicability.",
                s["body"],
            ),
            Spacer(1, 2 * mm),
            Table(
                [[Paragraph("<b>Feedback form</b>", s["subsection"])],
                 [Paragraph(FORM_URL, s["link"])],
                 [Paragraph("Estimated time: 10-15 minutes.", s["body_small"])]],
                colWidths=[PAGE_WIDTH - 2 * MARGIN_X],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), PANEL),
                        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                        ("LEFTPADDING", (0, 0), (-1, -1), 10),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                        ("TOPPADDING", (0, 0), (-1, -1), 7),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ]
                ),
            ),
            Spacer(1, 5 * mm),
            Paragraph("Follow-up", s["section"]),
            Paragraph(
                "If you are open to a short follow-up conversation, please leave your name, email, "
                "or LinkedIn profile in the form.",
                s["body"],
            ),
            Paragraph(
                "Your feedback will directly help shape the next development steps of MaterialScope.",
                s["body"],
            ),
        ]
    )
    return story


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        rightMargin=MARGIN_X,
        leftMargin=MARGIN_X,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
        title="MaterialScope - Early Tester Guide",
        author="MaterialScope",
        subject="Early feedback round for materials characterization workflows",
    )
    doc.build(build_story(), onFirstPage=draw_footer, onLaterPages=draw_footer)
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
