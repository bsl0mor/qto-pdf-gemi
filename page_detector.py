"""
page_detector.py — Auto-detect drawing page numbers in STR/ARCH PDFs using Gemini.

Renders every page as a small thumbnail, sends them all in ONE Gemini call,
and returns a complete config dict ready to pass into run_batch.py.

Usage (CLI):
    py page_detector.py <str_pdf> <arch_pdf>
    py page_detector.py "B:\\...\\Str.pdf" "B:\\...\\Arch.pdf"
    py page_detector.py "B:\\...\\Str.pdf" none        # STR only
    py page_detector.py none "B:\\...\\Arch.pdf"       # ARCH only

Usage (as module):
    from page_detector import detect_pages
    cfg = detect_pages(str_pdf=r"...", arch_pdf=r"...")
    # cfg = {"pg_foundation": 7, "pg_tbeam": 8, "pg_gf_plan": 2, ...}
"""

import fitz, base64, json, urllib.request, os, sys

API_KEY     = "AIzaSyAEf3myy42MZRDChyd2kRRrXDusTFG0rEY"
MODEL       = "gemini-2.5-flash"
URL         = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
THUMB_SCALE = 0.35   # ~35% — small enough to be cheap, large enough to read titles


# ══════════════════════════════════════════════════════════════════════════════
# RENDERING
# ══════════════════════════════════════════════════════════════════════════════

def _render_pdf(pdf_path: str, scale: float = THUMB_SCALE) -> list:
    """Render all pages of a PDF → list of {index, width, height, b64}."""
    doc = fitz.open(pdf_path)
    pages = []
    total_kb = 0
    for i in range(len(doc)):
        pix = doc[i].get_pixmap(
            matrix=fitz.Matrix(scale, scale),
            colorspace=fitz.csRGB
        )
        b64 = base64.b64encode(pix.tobytes("jpeg", jpg_quality=75)).decode()
        kb  = len(b64) // 1024
        total_kb += kb
        pages.append({"index": i, "width": pix.width, "height": pix.height, "b64": b64})
        print(f"    pg{i:02d}: {pix.width}x{pix.height}px  {kb}KB")
    doc.close()
    print(f"  Total: {len(pages)} pages, {total_kb}KB")
    return pages


# ══════════════════════════════════════════════════════════════════════════════
# GEMINI CALL
# ══════════════════════════════════════════════════════════════════════════════

PROMPT = """You are a structural/architectural drawing classifier for UAE villa construction projects.

I am showing you thumbnail images of all pages from one or two PDFs (labelled STR or ARCH).
Each image is labelled with [STR PAGE N] or [ARCH PAGE N] (0-based index).

YOUR TASK: identify the 0-based page index for each drawing type listed below.

──────────────────────────────────────────────────────────────
STRUCTURAL drawing types (look in STR pages):
  foundation_layout  → Plan showing footing positions + Schedule of Footings table
  tiebeam_layout     → Plan showing tie beams / ground beams layout
  columns_gf         → Ground floor column layout plan (+ column schedule if present)
  columns_ff         → First floor column layout plan
                       If the column drawing covers ALL FLOORS / GF TO ROOF, set columns_ff = columns_gf
  ff_slab            → First floor (FF) slab layout / beam plan
  roof_slab          → Roof floor slab layout / beam plan

ARCHITECTURAL drawing types (look in ARCH pages):
  gf_plan            → Ground floor architectural floor plan (rooms, walls, dimensions)
  ff_plan            → First floor architectural floor plan
  section_heights    → Section or elevation clearly showing floor heights / FFL levels
                       (e.g. GF = +0.60m, FF = +4.30m, Roof = +8.00m)
  elevation_1        → First facade elevation sheet (front / rear, labelled E1 or E2)
  elevation_2        → Second facade elevation sheet (sides, labelled E3/E4 or different from above)
                       If all elevations are on one page, set elevation_2 = elevation_1
  dw_schedule        → Doors and Windows schedule table (D1, D2... / W1, W2... with dimensions)
──────────────────────────────────────────────────────────────

RULES:
  - Page indices are 0-based
  - If two types share the same page, use the same index for both
  - If a type is NOT found, use null
  - Do NOT guess — only assign a page you are confident about

Return ONLY this JSON (no markdown fences, no comments):
{
  "str": {
    "foundation_layout": <int or null>,
    "tiebeam_layout":    <int or null>,
    "columns_gf":        <int or null>,
    "columns_ff":        <int or null>,
    "ff_slab":           <int or null>,
    "roof_slab":         <int or null>
  },
  "arch": {
    "gf_plan":           <int or null>,
    "ff_plan":           <int or null>,
    "section_heights":   <int or null>,
    "elevation_1":       <int or null>,
    "elevation_2":       <int or null>,
    "dw_schedule":       <int or null>
  },
  "notes": "<brief observations e.g. pages not found, combined pages, etc.>"
}"""


def detect_pages(str_pdf: str = None, arch_pdf: str = None) -> dict:
    """
    Auto-detect page numbers in STR and/or ARCH PDFs using Gemini.

    Returns a flat config dict:
        {pg_foundation, pg_tbeam, pg_columns, pg_gf_cols, pg_ff_cols,
         pg_ff_slab, pg_roof_slab, pg_elevation, pg_gf_plan, pg_ff_plan,
         pg_elev1, pg_elev2, pg_dw_sched}
    """
    parts = []

    # ── STR PDF ──────────────────────────────────────────────────────────────
    if str_pdf and str_pdf.lower() != "none" and os.path.exists(str_pdf):
        print(f"\nRendering STR: {os.path.basename(str_pdf)}")
        str_pages = _render_pdf(str_pdf)
        parts.append({"text": f"\n=== STRUCTURAL PDF: {os.path.basename(str_pdf)} "
                               f"({len(str_pages)} pages) ===\n"})
        for pg in str_pages:
            parts.append({"text": f"[STR PAGE {pg['index']} | {pg['width']}x{pg['height']}px]"})
            parts.append({"inlineData": {"mimeType": "image/jpeg", "data": pg["b64"]}})
    elif str_pdf and str_pdf.lower() != "none":
        print(f"  ⚠ STR PDF not found: {str_pdf}")

    # ── ARCH PDF ─────────────────────────────────────────────────────────────
    if arch_pdf and arch_pdf.lower() != "none" and os.path.exists(arch_pdf):
        print(f"\nRendering ARCH: {os.path.basename(arch_pdf)}")
        arch_pages = _render_pdf(arch_pdf)
        parts.append({"text": f"\n=== ARCHITECTURAL PDF: {os.path.basename(arch_pdf)} "
                               f"({len(arch_pages)} pages) ===\n"})
        for pg in arch_pages:
            parts.append({"text": f"[ARCH PAGE {pg['index']} | {pg['width']}x{pg['height']}px]"})
            parts.append({"inlineData": {"mimeType": "image/jpeg", "data": pg["b64"]}})
    elif arch_pdf and arch_pdf.lower() != "none":
        print(f"  ⚠ ARCH PDF not found: {arch_pdf}")

    if not parts:
        raise ValueError("No valid PDFs provided.")

    # ── Call Gemini ───────────────────────────────────────────────────────────
    body = json.dumps({
        "contents": [{"role": "user", "parts": [
            {"text": PROMPT},
            *parts
        ]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingBudget": 3000}
        }
    }).encode()

    print("\nCalling Gemini for page detection...")
    req = urllib.request.Request(
        URL, data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())

    raw = data["candidates"][0]["content"]["parts"][0]["text"]

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        import re
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            result = json.loads(m.group(0))
        else:
            print(f"⚠ Could not parse Gemini response:\n{raw}")
            raise

    # ── Map to pipeline config keys ───────────────────────────────────────────
    s = result.get("str",  {}) or {}
    a = result.get("arch", {}) or {}

    cfg = {
        "pg_foundation": s.get("foundation_layout"),
        "pg_tbeam":      s.get("tiebeam_layout"),
        "pg_columns":    s.get("columns_gf"),
        "pg_gf_cols":    s.get("columns_gf"),
        "pg_ff_cols":    s.get("columns_ff"),
        "pg_ff_slab":    s.get("ff_slab"),
        "pg_roof_slab":  s.get("roof_slab"),
        "pg_elevation":  a.get("section_heights"),
        "pg_gf_plan":    a.get("gf_plan"),
        "pg_ff_plan":    a.get("ff_plan"),
        "pg_elev1":      a.get("elevation_1"),
        "pg_elev2":      a.get("elevation_2"),
        "pg_dw_sched":   a.get("dw_schedule"),
    }

    notes = result.get("notes", "")
    if notes:
        print(f"\nGemini notes: {notes}")

    return cfg, result


# ══════════════════════════════════════════════════════════════════════════════
# DISPLAY
# ══════════════════════════════════════════════════════════════════════════════

_LABELS = {
    "pg_foundation": "Foundation Layout     (STR)",
    "pg_tbeam":      "Tie Beam Layout       (STR)",
    "pg_columns":    "Columns GF            (STR)",
    "pg_ff_cols":    "Columns FF            (STR)",
    "pg_ff_slab":    "FF Slab Layout        (STR)",
    "pg_roof_slab":  "Roof Slab Layout      (STR)",
    "pg_elevation":  "Section / Heights     (ARCH)",
    "pg_gf_plan":    "GF Floor Plan         (ARCH)",
    "pg_ff_plan":    "FF Floor Plan         (ARCH)",
    "pg_elev1":      "Elevation 1           (ARCH)",
    "pg_elev2":      "Elevation 2           (ARCH)",
    "pg_dw_sched":   "Doors & Windows Sched (ARCH)",
}

def print_cfg(cfg: dict):
    print("\n" + "=" * 55)
    print("  DETECTED PAGE MAP")
    print("=" * 55)
    missing = []
    for k, label in _LABELS.items():
        v = cfg.get(k)
        if v is None:
            missing.append(label)
            print(f"  ✗  {label}  →  NOT FOUND")
        else:
            print(f"  ✓  {label}  →  page {v}")
    if missing:
        print(f"\n  ⚠ {len(missing)} item(s) not detected — set manually in config")
    else:
        print("\n  ✓ All drawings detected successfully!")
    print("=" * 55)


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    str_pdf  = sys.argv[1] if len(sys.argv) > 1 else None
    arch_pdf = sys.argv[2] if len(sys.argv) > 2 else None

    cfg, raw_result = detect_pages(str_pdf, arch_pdf)
    print_cfg(cfg)

    # Save pagemap JSON next to this script
    base = os.path.splitext(os.path.basename(str_pdf or arch_pdf))[0]
    out  = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{base}_pagemap.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"config": cfg, "raw": raw_result}, f, indent=2, ensure_ascii=False)
    print(f"\nSaved: {out}")

    # Print as Python dict snippet for copy-paste into run_batch.py
    print("\n── Config snippet (copy into run_batch.py) ──")
    for k, v in cfg.items():
        print(f'    "{k}": {v},')
