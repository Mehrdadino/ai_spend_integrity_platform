"""Generate cross-site comparison test PDFs with embedded ``BILL_SPEC_V1`` blocks.

PDFs use a minimal PDF 1.4 writer (Helvetica text layer) so ``pypdf`` can extract them
without OCR. The spec block drives ``generic-bill-v1`` when no LLM key is set.

Upload order for the **3-bill / 2-site** demo (see ``CROSS_SITE_UPLOAD_ORDER``):
  1. Site B — March baseline (peer)
  2. Site A — February baseline (prior for same-site MoM)
  3. Site A — March rare fee (anchor) — **upload last**

Cross-site peer rules need **≥3 other sites** in production. Optional PDFs 4–5 add
peer sites C and D for a full ``peer_fee_line_rare`` signal without lowering thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence


@dataclass(frozen=True)
class CrossSiteBillPdfSpec:
    """One generated PDF: human label + embedded machine spec."""

    filename: str
    site_name: str
    upload_order: int
    display_title: str
    company: str
    service_address: str
    account_type: str
    period_start: str
    period_end: str
    issue_date: str
    spend_domain: str
    spend_kind: str
    lines: tuple[tuple[str, float, str], ...]  # label, amount, extras (qty= / kind=)
    header_total: float | None = None


# (filename, order, site, scenario copy)
CROSS_SITE_UPLOAD_ORDER: tuple[CrossSiteBillPdfSpec, ...] = (
    CrossSiteBillPdfSpec(
        filename="01-upload-first-site-b-mar-normal.pdf",
        site_name="Cross-Site Site B",
        upload_order=1,
        display_title="March 2026 — Site B baseline",
        company="Pacific Electric Utilities",
        service_address="Cross-Site Site B — 1200 Harbor Ave",
        account_type="Utility account — electric service",
        period_start="2026-03-01",
        period_end="2026-03-31",
        issue_date="2026-04-05",
        spend_domain="utility",
        spend_kind="electricity",
        lines=(
            ("Basic service charge", 12.50, ""),
            ("Energy usage", 98.40, "qty=820 | unit=kwh"),
            ("Environmental levy", 4.10, ""),
            ("State tax", 6.32, ""),
        ),
    ),
    CrossSiteBillPdfSpec(
        filename="02-upload-second-site-a-feb-normal.pdf",
        site_name="Cross-Site Site A",
        upload_order=2,
        display_title="February 2026 — Site A baseline",
        company="Pacific Electric Utilities",
        service_address="Cross-Site Site A — 88 Market Street",
        account_type="Utility account — electric service",
        period_start="2026-02-01",
        period_end="2026-02-28",
        issue_date="2026-03-05",
        spend_domain="utility",
        spend_kind="electricity",
        lines=(
            ("Basic service charge", 12.50, ""),
            ("Energy usage", 98.40, "qty=820 | unit=kwh"),
            ("Environmental levy", 4.10, ""),
            ("State tax", 6.32, ""),
        ),
    ),
    CrossSiteBillPdfSpec(
        filename="03-upload-last-site-a-mar-rare-fee.pdf",
        site_name="Cross-Site Site A",
        upload_order=3,
        display_title="March 2026 — Site A rare grid surcharge",
        company="Pacific Electric Utilities",
        service_address="Cross-Site Site A — 88 Market Street",
        account_type="Utility account — electric service",
        period_start="2026-03-01",
        period_end="2026-03-31",
        issue_date="2026-04-05",
        spend_domain="utility",
        spend_kind="electricity",
        lines=(
            ("Basic service charge", 12.50, ""),
            ("Energy usage", 98.40, "qty=820 | unit=kwh"),
            ("Grid modernization surcharge", 15.00, "kind=fee"),
            ("Environmental levy", 4.10, ""),
            ("State tax", 7.15, ""),
        ),
    ),
)

# Optional fourth and fifth uploads at **new sites** so §3c peer gates pass (≥3 peer sites).
CROSS_SITE_OPTIONAL_PEER_PDFS: tuple[CrossSiteBillPdfSpec, ...] = (
    CrossSiteBillPdfSpec(
        filename="04-optional-site-c-mar-normal.pdf",
        site_name="Cross-Site Site C",
        upload_order=4,
        display_title="March 2026 — Site C baseline",
        company="Pacific Electric Utilities",
        service_address="Cross-Site Site C — 400 Industrial Blvd",
        account_type="Utility account — electric service",
        period_start="2026-03-01",
        period_end="2026-03-31",
        issue_date="2026-04-05",
        spend_domain="utility",
        spend_kind="electricity",
        lines=(
            ("Basic service charge", 12.50, ""),
            ("Energy usage", 98.40, "qty=820 | unit=kwh"),
            ("Environmental levy", 4.10, ""),
            ("State tax", 6.32, ""),
        ),
    ),
    CrossSiteBillPdfSpec(
        filename="05-optional-site-d-mar-normal.pdf",
        site_name="Cross-Site Site D",
        upload_order=5,
        display_title="March 2026 — Site D baseline",
        company="Pacific Electric Utilities",
        service_address="Cross-Site Site D — 55 Campus Drive",
        account_type="Utility account — electric service",
        period_start="2026-03-01",
        period_end="2026-03-31",
        issue_date="2026-04-05",
        spend_domain="utility",
        spend_kind="electricity",
        lines=(
            ("Basic service charge", 12.50, ""),
            ("Energy usage", 98.40, "qty=820 | unit=kwh"),
            ("Environmental levy", 4.10, ""),
            ("State tax", 6.32, ""),
        ),
    ),
)

ALL_CROSS_SITE_PDF_SPECS: tuple[CrossSiteBillPdfSpec, ...] = (
    CROSS_SITE_UPLOAD_ORDER + CROSS_SITE_OPTIONAL_PEER_PDFS
)


def _sum_lines(spec: CrossSiteBillPdfSpec) -> float:
    return round(sum(amt for _, amt, _ in spec.lines), 2)


def _ascii_safe(s: str) -> str:
    return s.encode("ascii", "replace").decode("ascii")


def _bill_spec_block(spec: CrossSiteBillPdfSpec) -> str:
    total = spec.header_total if spec.header_total is not None else _sum_lines(spec)
    rows = [
        "BILL_SPEC_V1",
        f"spend_domain: {spec.spend_domain}",
        f"spend_kind: {spec.spend_kind}",
        f"issuer_name: {spec.company}",
        f"period_start: {spec.period_start}",
        f"period_end: {spec.period_end}",
        "currency: USD",
    ]
    for label, amount, extras in spec.lines:
        extra = f" | {extras}" if extras else ""
        rows.append(f"line: {label} | {amount:.2f}{extra}")
    rows.append(f"header_total: {total:.2f}")
    rows.append("END_BILL_SPEC")
    return "\n".join(rows)


def _build_page_stream(spec: CrossSiteBillPdfSpec) -> str:
    """PDF content stream (ASCII) — mirrors frontend ``pdfGenerator`` layout."""
    total = spec.header_total if spec.header_total is not None else _sum_lines(spec)
    y = 740
    cmds: list[str] = ["BT"]

    def font(fid: int, size: float, r: float, g: float, b: float) -> None:
        cmds.append(f"/F{fid} {size} Tf {r} {g} {b} rg")

    def txt(x: float, yy: float, text: str) -> None:
        safe = _ascii_safe(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        cmds.append(f"1 0 0 1 {x} {yy} Tm ({safe}) Tj")

    font(1, 16, 0.1, 0.2, 0.5)
    txt(50, y, spec.company)
    y -= 22
    font(2, 9, 0.35, 0.35, 0.35)
    txt(50, y, "Reliable Power for Every Customer Since 1952")
    y -= 36
    font(1, 11, 0, 0, 0)
    txt(50, y, "STATEMENT OF ACCOUNT")
    y -= 28
    font(2, 9, 0, 0, 0)
    txt(50, y, f"Service address: {spec.service_address}")
    y -= 14
    txt(50, y, spec.account_type)
    y -= 14
    txt(50, y, f"Billing period: {spec.period_start} — {spec.period_end}")
    y -= 14
    txt(50, y, f"Issue date: {spec.issue_date}")
    y -= 24
    font(1, 10, 0, 0, 0)
    txt(50, y, "Description")
    txt(420, y, "Amount (USD)")
    y -= 18
    font(2, 9, 0, 0, 0)
    for label, amount, detail in spec.lines:
        txt(50, y, label)
        txt(420, y, f"${amount:,.2f}")
        y -= 14
        if detail and "qty=" in detail:
            txt(60, y, detail.replace("|", " ").strip())
            y -= 12
    y -= 8
    font(1, 11, 0, 0, 0)
    txt(50, y, "Total Amount Due")
    txt(420, y, f"${total:,.2f}")
    y -= 40
    font(2, 7.5, 0.6, 0.6, 0.6)
    spec_block = _bill_spec_block(spec)
    for line in spec_block.splitlines():
        txt(50, y, line)
        y -= 10
    cmds.append("ET")
    return "\n".join(cmds)


def build_test_bill_pdf_bytes(spec: CrossSiteBillPdfSpec) -> bytes:
    """Return a PDF 1.4 document with embedded text + ``BILL_SPEC_V1``."""
    stream = _build_page_stream(spec)
    stream_len = len(stream.encode("ascii"))
    bodies = [
        "",
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]\n"
        "   /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >>\n"
        "   /Contents 6 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        f"<< /Length {stream_len} >>\nstream\n{stream}\nendstream",
    ]
    pdf = "%PDF-1.4\n"
    offsets: list[int] = [0] * 7
    for i in range(1, 7):
        offsets[i] = len(pdf.encode("ascii"))
        pdf += f"{i} 0 obj\n{bodies[i]}\nendobj\n"
    xref_offset = len(pdf.encode("ascii"))
    pdf += "xref\n0 7\n0000000000 65535 f \n"
    for i in range(1, 7):
        pdf += f"{str(offsets[i]).zfill(10)} 00000 n \n"
    pdf += f"trailer\n<< /Size 7 /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
    return pdf.encode("ascii")


def write_cross_site_pdfs_to_dir(target_dir: str, *, include_optional: bool = True) -> list[str]:
    """Write PDF files to ``target_dir``; return paths written."""
    import os

    os.makedirs(target_dir, exist_ok=True)
    specs: Sequence[CrossSiteBillPdfSpec] = (
        ALL_CROSS_SITE_PDF_SPECS if include_optional else CROSS_SITE_UPLOAD_ORDER
    )
    paths: list[str] = []
    for spec in specs:
        path = os.path.join(target_dir, spec.filename)
        with open(path, "wb") as fh:
            fh.write(build_test_bill_pdf_bytes(spec))
        paths.append(path)
    return paths
