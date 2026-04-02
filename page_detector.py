"""
page_detector.py — Text-based page classifier for STR/ARCH PDFs.
══════════════════════════════════════════════════════════════════
Reads the text layer of every PDF page and searches for known
drawing-type keywords.  Falls back to interactive user prompt for
any page whose type cannot be determined from text alone.

No AI, no API key, works fully offline.

Usage (CLI):
    py page_detector.py <str_pdf> <arch_pdf>
    py page_detector.py "path/Str.pdf" "path/Arch.pdf"
    py page_detector.py "path/Str.pdf" none        # STR only
    py page_detector.py none "path/Arch.pdf"       # ARCH only

Usage (as module):
    from page_detector import detect_pages
    cfg = detect_pages(str_pdf="...", arch_pdf="...")
    # cfg = {"pg_foundation": 7, "pg_tbeam": 8, "pg_gf_plan": 2, ...}
"""

import fitz, re, sys, json, os

# ══════════════════════════════════════════════════════════════════════════════
# KEYWORD SIGNATURES
# ══════════════════════════════════════════════════════════════════════════════
# Each value is a list of keyword phrases (case-insensitive).
# A page matches a type if ANY keyword is found in its text.
# More-specific keywords should appear first to avoid false positives.

_STR_KEYWORDS = {
    "foundation_layout": [
        "FOUNDATION LAYOUT",
        "FOOTING LAYOUT",
        "SCHEDULE OF FOOTINGS",
        "SCHEDULE OF FOOTING",
        "FOUNDATION PLAN",
    ],
    "tiebeam_layout": [
        "TIE BEAM LAYOUT",
        "TIE BEAMS LAYOUT",
        "TIEBEAM LAYOUT",
        "GROUND BEAM LAYOUT",
        "GROUND BEAMS LAYOUT",
        "SOG LAYOUT",
        "SCHEDULE OF TIE BEAMS",
        "TIE BEAM PLAN",
    ],
    "columns_ff": [
        "FIRST FLOOR COLUMN",
        "FF COLUMN LAYOUT",
        "1ST FLOOR COLUMN",
        "FIRST FLOOR COLUMN LAYOUT",
        "FF COLS",
    ],
    "columns_gf": [
        "GROUND FLOOR COLUMN",
        "GF COLUMN LAYOUT",
        "COLUMN LAYOUT",
        "COLUMNS LAYOUT",
        "SCHEDULE OF COLUMNS",
        "COLUMN LAYOUT AT GROUND FLOOR",
    ],
    "ff_slab": [
        "FIRST FLOOR SLAB LAYOUT",
        "FF SLAB LAYOUT",
        "1ST FLOOR SLAB",
        "FIRST SLAB LAYOUT",
        "FIRST FLOOR SLAB",
    ],
    "roof_slab": [
        "ROOF SLAB LAYOUT",
        "RF SLAB LAYOUT",
        "ROOF SLAB",
        "RF SLAB",
        "ROOF FLOOR SLAB",
    ],
}

_ARCH_KEYWORDS = {
    "dw_schedule": [
        "DOORS AND WINDOWS SCHEDULE",
        "DOOR AND WINDOW SCHEDULE",
        "D&W SCHEDULE",
        "SCHEDULE OF DOORS AND WINDOWS",
        "WINDOWS SCHEDULE",
        "ALUMINUM WINDOWS DETAILS",
        "ALUMINIUM WINDOWS DETAILS",
        "DOOR SCHEDULE",
    ],
    "section_heights": [
        "BUILDING SECTION",
        "CROSS SECTION",
        "SECTION A-A",
        "SECTION B-B",
        "SECTION A",
        "SECTION B",
        "FFL",
        "FINISHED FLOOR LEVEL",
        "FLOOR TO FLOOR",
    ],
    "ff_plan": [
        "FIRST FLOOR PLAN",
        "FF FLOOR PLAN",
        "1ST FLOOR PLAN",
        "FIRST FLOOR ARCHITECTURAL PLAN",
        "FIRST FLOOR LAYOUT",
    ],
    "gf_plan": [
        "GROUND FLOOR PLAN",
        "G.F. PLAN",
        "GF FLOOR PLAN",
        "GROUND FLOOR LAYOUT",
        "GROUND FLOOR ARCHITECTURAL PLAN",
    ],
    "elevation_2": [
        "ELEVATION 3",
        "ELEVATION 4",
        "ELEVATIONS 3",
        "ELEVATIONS 4",
        "SIDE ELEVATION",
        "E3",
        "E4",
    ],
    "elevation_1": [
        "ELEVATION 1",
        "ELEVATION 2",
        "ELEVATIONS 1",
        "ELEVATIONS 2",
        "FRONT ELEVATION",
        "REAR ELEVATION",
        "E1",
        "E2",
        "ELEVATION",
    ],
}


# ══════════════════════════════════════════════════════════════════════════════
# DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def _classify_page(text: str, keyword_map: dict) -> list:
    """
    Return list of drawing types matched in 'text'.
    text is the raw text of ONE PDF page.
    """
    text_upper = text.upper()
    matches = []
    for dtype, keywords in keyword_map.items():
        for kw in keywords:
            if kw in text_upper:
                matches.append(dtype)
                break
    return matches


def _detect_from_pdf(pdf_path: str, keyword_map: dict, pdf_label: str) -> dict:
    """
    Scan all pages in pdf_path, return {drawing_type: page_index}.
    When multiple pages match the same type, the first match wins.
    """
    if not os.path.exists(pdf_path):
        print(f"  ⚠ PDF not found: {pdf_path}")
        return {}

    doc = fitz.open(pdf_path)
    n = doc.page_count
    print(f"\nScanning {pdf_label}: {os.path.basename(pdf_path)}  ({n} pages)")

    detected = {}          # drawing_type → page_index
    page_texts = []
    for i in range(n):
        text = doc[i].get_text()
        page_texts.append(text)
        matched = _classify_page(text, keyword_map)
        for dtype in matched:
            if dtype not in detected:
                detected[dtype] = i
                print(f"  ✓  page {i:02d}  →  {dtype}")

    doc.close()
    return detected, page_texts, n


def _ask_page(drawing_label: str, pdf_label: str, n_pages: int) -> int | None:
    """Interactively ask the user for a 0-based page number."""
    raw = input(
        f"  Enter 0-based page number for '{drawing_label}' in {pdf_label}"
        f" (0–{n_pages-1}, or ENTER to skip): "
    ).strip()
    if raw == "":
        return None
    try:
        v = int(raw)
        if 0 <= v < n_pages:
            return v
        print(f"    ✗ Must be 0–{n_pages-1}")
    except ValueError:
        pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
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


def detect_pages(str_pdf: str = None, arch_pdf: str = None) -> tuple:
    """
    Detect page numbers in STR and/or ARCH PDFs using text-layer keywords.
    Falls back to interactive user prompt for any undetected type.

    Returns
    -------
    cfg : dict   flat config — {pg_foundation, pg_tbeam, pg_columns,
                 pg_gf_cols, pg_ff_cols, pg_ff_slab, pg_roof_slab,
                 pg_elevation, pg_gf_plan, pg_ff_plan,
                 pg_elev1, pg_elev2, pg_dw_sched}
    result : dict  raw detection detail
    """
    cfg = {k: None for k in _LABELS}
    result = {"str": {}, "arch": {}, "notes": "text-based detection"}

    str_n = 0
    arch_n = 0

    # ── STR detection ─────────────────────────────────────────────
    if str_pdf and str_pdf.lower() != "none" and os.path.exists(str_pdf):
        str_detected, str_texts, str_n = _detect_from_pdf(
            str_pdf, _STR_KEYWORDS, "STR"
        )
        result["str"] = {k: v for k, v in str_detected.items()}

        cfg["pg_foundation"] = str_detected.get("foundation_layout")
        cfg["pg_tbeam"]      = str_detected.get("tiebeam_layout")
        cfg["pg_columns"]    = str_detected.get("columns_gf")
        cfg["pg_gf_cols"]    = str_detected.get("columns_gf")
        cfg["pg_ff_cols"]    = str_detected.get("columns_ff",
                                                 str_detected.get("columns_gf"))
        cfg["pg_ff_slab"]    = str_detected.get("ff_slab")
        cfg["pg_roof_slab"]  = str_detected.get("roof_slab")

    elif str_pdf and str_pdf.lower() != "none":
        print(f"  ⚠ STR PDF not found: {str_pdf}")

    # ── ARCH detection ────────────────────────────────────────────
    if arch_pdf and arch_pdf.lower() != "none" and os.path.exists(arch_pdf):
        arch_detected, arch_texts, arch_n = _detect_from_pdf(
            arch_pdf, _ARCH_KEYWORDS, "ARCH"
        )
        result["arch"] = {k: v for k, v in arch_detected.items()}

        cfg["pg_elevation"] = arch_detected.get("section_heights")
        cfg["pg_gf_plan"]   = arch_detected.get("gf_plan")
        cfg["pg_ff_plan"]   = arch_detected.get("ff_plan")
        cfg["pg_elev1"]     = arch_detected.get("elevation_1")
        cfg["pg_elev2"]     = arch_detected.get("elevation_2",
                                                 arch_detected.get("elevation_1"))
        cfg["pg_dw_sched"]  = arch_detected.get("dw_schedule")

    elif arch_pdf and arch_pdf.lower() != "none":
        print(f"  ⚠ ARCH PDF not found: {arch_pdf}")

    # ── Interactive fallback for undetected types ─────────────────
    undetected = [(k, label) for k, label in _LABELS.items() if cfg.get(k) is None]
    if undetected:
        print(f"\n  {len(undetected)} drawing type(s) not auto-detected — please enter manually:")
        for cfg_key, label in undetected:
            is_str = "(STR)" in label
            pdf_label = "STR" if is_str else "ARCH"
            n_pages = str_n if is_str else arch_n
            if n_pages == 0:
                continue
            v = _ask_page(label, pdf_label, n_pages)
            if v is not None:
                cfg[cfg_key] = v

    return cfg, result


def print_cfg(cfg: dict):
    """Print a formatted detection summary."""
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
        print(f"\n  ⚠ {len(missing)} item(s) not detected")
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

    base = os.path.splitext(os.path.basename(str_pdf or arch_pdf))[0]
    out  = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{base}_pagemap.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"config": cfg, "raw": raw_result}, f, indent=2, ensure_ascii=False)
    print(f"\nSaved: {out}")

    print("\n── Config snippet (copy into run_batch.py) ──")
    for k, v in cfg.items():
        print(f'    "{k}": {v},')
