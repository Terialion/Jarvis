from __future__ import annotations
from pathlib import Path
from typing import Any, Dict

DESCRIPTION = "PDF 生成适配入口"
ICON = "📕"


def execute(text: str = "", output: str = "", user_input: str = "", **kwargs) -> Dict[str, Any]:
    try:
      from reportlab.pdfgen import canvas
    except Exception:
      return {"status": "error", "code": "missing_dependency", "message": "reportlab not installed"}

    out = (output or "d:/jarvis/workspace/auto_generated.pdf").strip()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(out)
    c.drawString(50, 800, "Generated PDF")
    c.drawString(50, 780, (text or user_input or "Hello from minimax-pdf adapter")[:120])
    c.save()
    return {"status": "success", "output": out, "notes": "pdf_generated"}
