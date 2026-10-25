from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import re
import unicodedata
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED
from zoneinfo import ZoneInfo

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from app.services.persistent_interview import student_report


NAVY = colors.HexColor("#163248")
TEAL = colors.HexColor("#007F82")
MUTED = colors.HexColor("#526775")
LIGHT = colors.HexColor("#EDF5F6")
LINE = colors.HexColor("#D7E4E8")


def pdf_report(interview) -> dict:
    """Projeção da conversa visível. Nunca exporta gabarito ou análise interna."""
    report = student_report(interview)
    report["scenario_title"] = interview.scenario_snapshot.get("title", "Monitorias acadêmicas")
    report["max_questions"] = interview.max_questions
    report["people"] = {
        key: {"name": value.get("name", "Personagem"), "role": value.get("role", "")}
        for key, value in interview.scenario_snapshot["stakeholders"].items()
    }
    return report


def report_filename(report: dict) -> str:
    name = unicodedata.normalize("NFKD", str(report["group_name"]))
    name = name.encode("ascii", "ignore").decode().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name).strip("_")[:80] or "grupo"
    # O ID completo evita sobrescrever PDFs de grupos com nomes parecidos.
    session = re.sub(r"[^a-zA-Z0-9-]", "", str(report["session_id"]))[:36]
    return f"entrevista_{name}_{session or 'sessao'}.pdf"


@lru_cache(maxsize=1)
def _register_fonts() -> frozenset[int]:
    # Fontes incluídas no próprio ReportLab: não dependem do Windows/Linux.
    root = Path(reportlab.__file__).resolve().parent / "fonts"
    pdfmetrics.registerFont(TTFont("InterviewSans", str(root / "Vera.ttf")))
    pdfmetrics.registerFont(TTFont("InterviewSans-Bold", str(root / "VeraBd.ttf")))
    pdfmetrics.registerFontFamily("InterviewSans", normal="InterviewSans", bold="InterviewSans-Bold")
    regular = pdfmetrics.getFont("InterviewSans").face.charWidths
    bold = pdfmetrics.getFont("InterviewSans-Bold").face.charWidths
    return frozenset(regular) & frozenset(bold)


def _plain(value) -> str:
    supported = _register_fonts()
    text = str(value).replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    text = text.translate(str.maketrans({"\u2010": "-", "\u2011": "-", "\u2013": "-", "\u2014": "-"}))
    return "".join(
        char if char == "\n" or ord(char) in supported else f"[U+{ord(char):04X}]"
        for char in text if char == "\n" or ord(char) >= 32
    )


def _html(value) -> str:
    # O texto da entrevista não pode virar marcação ReportLab nem carregar imagens/URLs.
    return escape(_plain(value)).replace("\n", "<br/>")


def display_time(value) -> str:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo("America/Fortaleza")).strftime("%d/%m/%Y às %H:%M")


def build_interview_pdf(report: dict, *, exported_at: datetime | None = None) -> bytes:
    """PDF feito a partir da transcrição salva, sem chamadas de IA."""
    _register_fonts()
    exported_at = exported_at or datetime.now(timezone.utc)
    history = report.get("conversation_history", [])
    people = report.get("people", {})
    grouped: OrderedDict[str, list[tuple[int, dict]]] = OrderedDict()
    for number, turn in enumerate(history, 1):
        grouped.setdefault(turn["stakeholder_id"], []).append((number, turn))

    base = dict(fontName="InterviewSans", textColor=NAVY, alignment=TA_LEFT,
                fontSize=10, leading=15, spaceAfter=7, splitLongWords=True)
    body = ParagraphStyle("InterviewBody", **base)
    muted = ParagraphStyle("InterviewMuted", parent=body, textColor=MUTED, fontSize=8.5, leading=12)
    title = ParagraphStyle("InterviewTitle", parent=body, fontName="InterviewSans-Bold",
                           fontSize=26, leading=32, spaceAfter=12)
    group_style = ParagraphStyle("InterviewGroup", parent=body, textColor=TEAL,
                                 fontSize=19, leading=25, spaceAfter=14)
    heading = ParagraphStyle("InterviewHeading", parent=body, fontName="InterviewSans-Bold",
                             fontSize=17, leading=23, spaceBefore=15, spaceAfter=7,
                             keepWithNext=True)
    label = ParagraphStyle("InterviewLabel", parent=body, fontName="InterviewSans-Bold",
                           textColor=TEAL, fontSize=9, leading=13, spaceBefore=10,
                           spaceAfter=4, keepWithNext=True)
    question_style = ParagraphStyle("InterviewQuestion", parent=body, fontName="InterviewSans-Bold",
                                    keepWithNext=True)
    table_style = ParagraphStyle("InterviewTable", parent=body, fontSize=9, leading=13, spaceAfter=0)
    table_head = ParagraphStyle("InterviewTableHead", parent=table_style, fontName="InterviewSans-Bold",
                                textColor=colors.white)
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm,
        topMargin=23*mm, bottomMargin=22*mm,
        title=_plain(f"Entrevista - {report['group_name']}"),
        author="Stakeholder Virtual", subject="Registro de entrevista de elicitação de requisitos",
    )
    width = A4[0] - 40*mm
    story = [
        Paragraph("REGISTRO DA ATIVIDADE", label),
        Paragraph("Entrevista do grupo", title),
        Paragraph(_html(report["group_name"]), group_style),
        Paragraph(_html(report.get("scenario_title", "Monitorias acadêmicas")), body),
        Spacer(1, 4*mm), HRFlowable(width="100%", thickness=1.3, color=TEAL), Spacer(1, 6*mm),
    ]
    status = "Finalizada" if report.get("completed") else "Em andamento"
    maximum = report.get("max_questions", report.get("questions_asked", 0) + report.get("questions_remaining", 0))
    meta = [
        ("Situação", status),
        ("Perguntas salvas", f"{len(history)} de {maximum}"),
        ("Perguntas restantes", str(report.get("questions_remaining", 0))),
        ("PDF gerado em", display_time(exported_at) + " (Fortaleza)"),
        ("Identificador da sessão", str(report["session_id"])),
    ]
    metadata = Table(
        [[Paragraph(_html(key), muted), Paragraph(_html(value), table_style)] for key, value in meta],
        colWidths=[51*mm, width-51*mm], hAlign="LEFT",
    )
    metadata.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 8), ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story += [metadata, Spacer(1, 5*mm), Paragraph("Participação na entrevista", heading)]
    rows = [[Paragraph("Stakeholder", table_head), Paragraph("Papel", table_head), Paragraph("Perguntas", table_head)]]
    identifiers = list(people) + [key for key in grouped if key not in people]
    for identifier in identifiers:
        person = people.get(identifier, {})
        turns = grouped.get(identifier, [])
        name = person.get("name") or (turns[0][1].get("stakeholder_name", identifier) if turns else identifier)
        rows.append([Paragraph(_html(name), table_style), Paragraph(_html(person.get("role", "")), table_style),
                     Paragraph(str(len(turns)), table_style)])
    if len(rows) > 1:
        summary = Table(rows, colWidths=[66*mm, width-96*mm, 30*mm], repeatRows=1, hAlign="LEFT")
        summary.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), NAVY), ("ROWBACKGROUNDS", (0,1), (-1,-1), [LIGHT, colors.white]),
            ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 10),
            ("RIGHTPADDING", (0,0), (-1,-1), 10), ("TOPPADDING", (0,0), (-1,-1), 9),
            ("BOTTOMPADDING", (0,0), (-1,-1), 9),
        ]))
        story.append(summary)
    story += [Spacer(1, 5*mm), Paragraph(
        "As conversas estão organizadas por stakeholder. A numeração das perguntas mantém a ordem "
        "original de envio do grupo. Este documento preserva as perguntas e respostas registradas "
        "pelo grupo até a geração do PDF.", muted)]
    if not history:
        story.append(Paragraph("O grupo ainda não possui perguntas e respostas salvas.", body))
    else:
        story.append(PageBreak())
    for section_number, (identifier, turns) in enumerate(grouped.items()):
        if section_number:
            story.append(PageBreak())
        person = people.get(identifier, {})
        name = person.get("name") or turns[0][1].get("stakeholder_name", identifier)
        story.append(Paragraph(_html(name), heading))
        story.append(Paragraph(_html(person.get("role", "")) + f" · {len(turns)} pergunta(s)", muted))
        for number, turn in turns:
            story.append(Paragraph(f"PERGUNTA {number:02d}", label))
            for part in str(turn["question"]).split("\n\n"):
                if part.strip(): story.append(Paragraph(_html(part), question_style))
            story.append(Paragraph("RESPOSTA", label))
            for part in str(turn["response"]).split("\n\n"):
                if part.strip(): story.append(Paragraph(_html(part), body))
            story += [Spacer(1, 2*mm), HRFlowable(width="100%", thickness=0.5, color=LINE)]

    def frame(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(MUTED)
        canvas.setFont("InterviewSans", 8)
        canvas.drawString(20*mm, A4[1]-14*mm, "STAKEHOLDER VIRTUAL  /  ENTREVISTA")
        canvas.setStrokeColor(LINE)
        canvas.line(20*mm, 17*mm, A4[0]-20*mm, 17*mm)
        text = _plain(report["group_name"])
        while pdfmetrics.stringWidth(text, "InterviewSans", 8) > width-28*mm:
            text = text[:-4].rstrip() + "..."
        canvas.drawString(20*mm, 11*mm, text)
        canvas.drawRightString(A4[0]-20*mm, 11*mm, f"Página {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=frame, onLaterPages=frame)
    return buffer.getvalue()


def build_interviews_zip(reports: list[dict], *, exported_at: datetime | None = None) -> bytes:
    if not reports or len(reports) > 100:
        raise ValueError("Selecione entre 1 e 100 grupos por download.")
    exported_at = exported_at or datetime.now(timezone.utc)
    result = BytesIO()
    with ZipFile(result, "w", compression=ZIP_DEFLATED) as archive:
        for report in reports:
            archive.writestr(report_filename(report), build_interview_pdf(report, exported_at=exported_at))
    return result.getvalue()
