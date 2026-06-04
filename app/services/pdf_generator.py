from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas


@dataclass
class PDFGenerator:
    output_dir: str

    def __post_init__(self) -> None:
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    def _safe_filename(self, name: str) -> str:
        keep = []
        for ch in name:
            if ch.isalnum() or ch in ("-", "_"):
                keep.append(ch)
            elif ch.isspace():
                keep.append("_")
        return "".join(keep)[:120] or "document"

    def create_receipt(
        self,
        *,
        guest_name: str,
        booking_id: str,
        items: Sequence[tuple[str, float]],
        currency: str = "USD",
        notes: str | None = None,
    ) -> Path:
        total = sum(v for _, v in items)
        filename = self._safe_filename(f"receipt_{booking_id}_{guest_name}") + ".pdf"
        out_path = Path(self.output_dir) / filename

        canvas = Canvas(out_path.as_posix(), pagesize=LETTER)
        width, height = LETTER

        y = height - 1 * inch
        canvas.setFont("Helvetica-Bold", 18)
        canvas.drawString(1 * inch, y, "Monster Resort — Receipt")
        y -= 0.4 * inch

        canvas.setFont("Helvetica", 11)
        canvas.drawString(1 * inch, y, f"Guest: {guest_name}")
        y -= 0.25 * inch
        canvas.drawString(1 * inch, y, f"Booking ID: {booking_id}")
        y -= 0.25 * inch
        canvas.drawString(1 * inch, y, f"Issued: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        y -= 0.4 * inch

        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawString(1 * inch, y, "Line Items")
        y -= 0.25 * inch

        canvas.setFont("Helvetica", 11)
        for label, price in items:
            canvas.drawString(1.1 * inch, y, f"• {label}")
            canvas.drawRightString(width - 1 * inch, y, f"{currency} {price:,.2f}")  # noqa: E231
            y -= 0.22 * inch
            if y < 1.5 * inch:
                canvas.showPage()
                y = height - 1 * inch
                canvas.setFont("Helvetica", 11)

        y -= 0.15 * inch
        canvas.setFont("Helvetica-Bold", 12)
        canvas.drawRightString(width - 1 * inch, y, f"TOTAL: {currency} {total:,.2f}")  # noqa: E231
        y -= 0.4 * inch

        if notes:
            canvas.setFont("Helvetica-Bold", 11)
            canvas.drawString(1 * inch, y, "Notes")
            y -= 0.25 * inch
            canvas.setFont("Helvetica", 11)
            for line in notes.splitlines():
                canvas.drawString(1.1 * inch, y, line[:120])
                y -= 0.2 * inch

        canvas.showPage()
        canvas.save()
        return out_path
