import fitz, base64, json
import re as _re

from utils import page_to_b64, pdf_to_b64

# ── PROJECT DEFINITIONS ────────────────────────────────────────────────────────
_BASE_1577 = r"C:\Users\basel\Downloads\The System\FINAL DRAWINGS\New folder (3)"
_ARCH_3246 = r"C:\Users\basel\Downloads\The System\TINDER\DRAWINGS\PDF"

PROJECTS = [
    {
        "name":          "3246",
        "multi_pdf":     False,
        # Single structural PDF — page indices (0-based)
        "struct_pdf":    f"{_ARCH_3246}\\3246 - STRUCTURE.pdf",
        "pg_gf_cols":    4,    # S-01 GF Column Layout
        "pg_ff_cols":    5,    # S-02 FF Column Layout
        "pg_ff_slab":    8,    # S-05 First Floor Slab Layout + Beam Schedule
        "pg_roof_slab":  9,    # S-06 Roof Slab Layout + Beam Schedule
        # Architect PDF — for elevation/section heights only
        "arch_pdf":      f"{_ARCH_3246}\\3246 - ARCHITECT.pdf",
        "pg_elevation":  4,    # Elevation page with floor levels + parapet
        # User inputs
        "parapet_type":  "block",   # "concrete" or "block"
    },
    {
        "name":        "1577",
        "multi_pdf":   True,
        # Each structural drawing is a separate PDF
        "gf_cols":     f"{_BASE_1577}\\1ST  COLS.pdf",   # S-02 GF Column Layout (double space)
        "ff_cols":     f"{_BASE_1577}\\1ST COLS.pdf",    # S-03 FF Column Layout
        "ff_slab":     f"{_BASE_1577}\\1ST SLAB.pdf",    # S-06 First Floor Slab + Beam Schedule
        "roof_slab":   f"{_BASE_1577}\\RF SLAB.pdf",     # S-07 Roof Slab + Beam Schedule
        # Section PDF — for floor heights + parapet levels only
        "section_pdf": f"{_BASE_1577}\\sectio.pdf",
        # User inputs
        "parapet_type": "block",   # "concrete" or "block"
    },
]

# ══════════════════════════════════════════════════════════════════
# PHASE 1 — TEXT PARSERS
# ══════════════════════════════════════════════════════════════════

def extract_all_text(doc):
    return {i: doc[i].get_text() for i in range(doc.page_count)}

def parse_column_schedule(text):
    """
    Parse SCHEDULE OF COLUMNS from text.
    Returns list of {mark, b_cm, d_cm, shape}
    """
    cols = []
    lines = text.split("\n")
    in_sched = False
    for i, line in enumerate(lines):
        if _re.search(r'SCHEDULE\s+OF\s+COLUMNS', line, _re.I):
            in_sched = True
            continue
        if not in_sched:
            continue
        # Stop at next section header
        if _re.search(r'SCHEDULE\s+OF\s+(FOOTINGS|BEAMS|TIE)', line, _re.I):
            break
        # Match column marks: C1, C2, C5/DC, etc.
        mark_m = _re.match(r'^\s*(C[\d]+(?:/DC)?)\s*$', line.strip(), _re.I)
        if mark_m:
            mark = mark_m.group(1).upper()
            # Look ahead for dimensions
            for j in range(i+1, min(i+8, len(lines))):
                dim_m = _re.search(r'(\d{2,3})\s*[xX×]\s*(\d{2,3})', lines[j])
                if dim_m:
                    b, d = int(dim_m.group(1)), int(dim_m.group(2))
                    shape = "circular" if "DC" in mark or "dc" in mark else "rect"
                    cols.append({"mark": mark, "b_cm": b, "d_cm": d, "shape": shape})
                    break
                circ_m = _re.search(r'[Øø∅]?\s*(\d{2,3})', lines[j])
                if circ_m and "DC" in mark:
                    d = int(circ_m.group(1))
                    cols.append({"mark": mark, "b_cm": d, "d_cm": d, "shape": "circular"})
                    break
    return cols

def parse_slab_thickness(text):
    """Extract slab thickness in metres from text."""
    m = _re.search(r'(?:MAIN\s+SLAB\s+THICKNESS|SLAB\s+THICKNESS)[^\d]*(\d{2,3})\s*(?:cm|mm)?', text, _re.I)
    if m:
        val = int(m.group(1))
        # If > 5, treat as cm; else metres
        return round(val / 100, 3) if val > 5 else val
    return None

def parse_levels_from_text(text):
    """
    Extract floor levels from elevation/section text.
    Returns dict with keys: gf_ffl, ff_ffl, roof_slab_top, parapet_top (all in metres)
    """
    levels = {}
    # Match patterns like +0.80, +3.60, +7.20 etc.
    matches = _re.findall(r'\+\s*(\d+\.\d+)', text)
    floats = sorted(set(round(float(x), 3) for x in matches))
    # Also try labelled patterns
    for pat, key in [
        (r'G\.?F\.?\s*F\.?F\.?L[^\d+]*\+?\s*([\d\.]+)', 'gf_ffl'),
        (r'GR(?:OUND)?\s*FL(?:OOR)?\s*F(?:INISH)?[^\d+]*\+?\s*([\d\.]+)', 'gf_ffl'),
        (r'FIRST\s*FLOOR\s*F\.?F\.?L[^\d+]*\+?\s*([\d\.]+)', 'ff_ffl'),
        (r'1ST\s*FL[^\d+]*\+?\s*([\d\.]+)', 'ff_ffl'),
        (r'TOP\s+OF\s+(?:GR(?:OUND)?\s+FL(?:OOR)?\s+)?SLAB[^\d+]*\+?\s*([\d\.]+)', 'gf_slab_top'),
        (r'TOP\s+OF\s+(?:F(?:IRST)?\s+FL(?:OOR)?\s+)?SLAB[^\d+]*\+?\s*([\d\.]+)', 'ff_slab_top'),
        (r'TOP\s+OF\s+(?:ROOF\s+)?SLAB[^\d+]*\+?\s*([\d\.]+)', 'roof_slab_top'),
        (r'TOP\s+OF\s+PARAPET[^\d+]*\+?\s*([\d\.]+)', 'parapet_top'),
        (r'PARAPET[^\d+]*\+?\s*([\d\.]+)', 'parapet_top'),
    ]:
        m = _re.search(pat, text, _re.I)
        if m:
            levels[key] = float(m.group(1))
    levels['_all_plus_levels'] = floats
    return levels

# ══════════════════════════════════════════════════════════════════
# PHASE 2 — IMAGE RENDERING
# ══════════════════════════════════════════════════════════════════

# page_to_b64 and pdf_to_b64 imported from utils.py

# ══════════════════════════════════════════════════════════════════
# PHASE 3 — MAIN PROJECT RUNNER
# ══════════════════════════════════════════════════════════════════

def run_project(cfg):
    name         = cfg["name"]
    multi_pdf    = cfg["multi_pdf"]
    parapet_type = cfg.get("parapet_type", "block")

    print("\n" + "="*65)
    print(f"  PROJECT {name} — SUPERSTRUCTURE")
    print("="*65)

    # ── Load documents & extract text ──────────────────────────────
    if not multi_pdf:
        struct_doc = fitz.open(cfg["struct_pdf"])
        arch_doc   = fitz.open(cfg["arch_pdf"])

        gf_cols_text  = struct_doc[cfg["pg_gf_cols"]].get_text()
        ff_cols_text  = struct_doc[cfg["pg_ff_cols"]].get_text()
        ff_slab_text  = struct_doc[cfg["pg_ff_slab"]].get_text()
        roof_slab_text= struct_doc[cfg["pg_roof_slab"]].get_text()
        elev_text     = arch_doc[cfg["pg_elevation"]].get_text()

        all_struct_text = "\n".join([gf_cols_text, ff_cols_text, ff_slab_text, roof_slab_text])
        levels_text     = elev_text

    else:
        gf_cols_doc   = fitz.open(cfg["gf_cols"])
        ff_cols_doc   = fitz.open(cfg["ff_cols"])
        ff_slab_doc   = fitz.open(cfg["ff_slab"])
        roof_slab_doc = fitz.open(cfg["roof_slab"])
        section_doc   = fitz.open(cfg["section_pdf"])

        gf_cols_text  = gf_cols_doc[0].get_text()
        ff_cols_text  = ff_cols_doc[0].get_text()
        ff_slab_text  = ff_slab_doc[0].get_text()
        roof_slab_text= roof_slab_doc[0].get_text()
        elev_text     = section_doc[0].get_text()

        all_struct_text = "\n".join([gf_cols_text, ff_cols_text, ff_slab_text, roof_slab_text])
        levels_text     = elev_text

    # ── Parse text ─────────────────────────────────────────────────
    col_schedule = parse_column_schedule(all_struct_text)
    slab_t_ff    = parse_slab_thickness(ff_slab_text)
    slab_t_roof  = parse_slab_thickness(roof_slab_text)
    levels       = parse_levels_from_text(levels_text)

    slab_t = slab_t_ff or slab_t_roof or 0.20   # fallback 20cm

    print(f"Columns parsed   : {[c['mark'] for c in col_schedule]}")
    print(f"Slab thickness   : {slab_t}m  (FF={slab_t_ff}, Roof={slab_t_roof})")
    print(f"Levels from text : {levels}")

    # ── Build parsed context string ────────────────────────────────
    if col_schedule:
        col_lines = "\n".join(
            f"  {c['mark']:8s} {c['b_cm']}x{c['d_cm']} cm  ({c['shape']})"
            for c in col_schedule
        )
        col_context = f"SCHEDULE OF COLUMNS (parsed from text — use these dims):\n{col_lines}"
    else:
        col_context = "SCHEDULE OF COLUMNS: Could not parse from text — read ALL column dims from the column layout images."

    slab_context = f"SLAB THICKNESS (parsed from text): {slab_t}m"

    level_lines = []
    for k, v in levels.items():
        if k != '_all_plus_levels':
            level_lines.append(f"  {k} = +{v}m")
    if levels.get('_all_plus_levels'):
        level_lines.append(f"  All +levels found: {levels['_all_plus_levels']}")
    level_context = "FLOOR LEVELS (parsed from elevation/section text):\n" + "\n".join(level_lines) if level_lines else "FLOOR LEVELS: Not found in text — read from elevation/section image."

    # ── Render images ──────────────────────────────────────────────
    parts_images = []

    if not multi_pdf:
        image_descs = [
            ("GF Column Layout + Column Schedule", cfg["pg_gf_cols"], struct_doc, None),
            ("FF Column Layout",                   cfg["pg_ff_cols"], struct_doc, None),
            ("First Floor Slab Layout + Beam Schedule", cfg["pg_ff_slab"],   struct_doc, None),
            ("Roof Slab Layout + Beam Schedule",   cfg["pg_roof_slab"], struct_doc, None),
            ("Elevation/Section — floor levels + parapet heights", cfg["pg_elevation"], arch_doc, None),
        ]
        for desc, pg_idx, doc, scale in image_descs:
            b64, kb = page_to_b64(doc, pg_idx, scale)
            parts_images.append({"inlineData": {"mimeType": "image/png", "data": b64}})
            print(f"  {desc}: {kb} KB")
    else:
        image_descs = [
            ("GF Column Layout + Column Schedule", gf_cols_doc,   0, None),
            ("FF Column Layout",                   ff_cols_doc,   0, None),
            ("First Floor Slab Layout + Beam Schedule", ff_slab_doc,  0, None),
            ("Roof Slab Layout + Beam Schedule",   roof_slab_doc, 0, None),
            ("Section — floor levels + parapet heights", section_doc,   0, None),
        ]
        for desc, doc, pg_idx, scale in image_descs:
            b64, kb = page_to_b64(doc, pg_idx, scale)
            parts_images.append({"inlineData": {"mimeType": "image/png", "data": b64}})
            print(f"  {desc}: {kb} KB")

    print(f"Total image parts: {len(parts_images)}")

    # ── Close PDF documents ────────────────────────────────────────
    if not multi_pdf:
        struct_doc.close()
        arch_doc.close()
    else:
        gf_cols_doc.close()
        ff_cols_doc.close()
        ff_slab_doc.close()
        roof_slab_doc.close()
        section_doc.close()

    # ── Build prompt ───────────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════════
    # VISION: READ-ONLY multi-pass (Gemini reads, does NOT calculate)
    # ══════════════════════════════════════════════════════════════════
    from manual_input import read_super as _vision_read_super
    from compute_super import recompute_super
    from guards import run_all_checks

    fh, obs, warnings = _vision_read_super(
        image_parts=parts_images,
        col_context=col_context,
        slab_context=slab_context,
        level_context=level_context,
        passes=3, name=name,
    )

    if warnings:
        print(f"  ⚠ Vision warnings: {warnings}")

    # Build result dict (compatible with old format)
    r = {
        "floorHeights": fh,
        "observedElements": obs,
        "warnings": warnings,
        "qtoItems": [],  # will be filled by recompute
    }

    # Save initial observed data
    with open(f"{name}_super_result.json", "w", encoding="utf-8") as f:
        json.dump(r, f, indent=2, ensure_ascii=False)
    print(f"Saved {name}_super_result.json (observed data)")
    # ── Deterministic recompute from observed data ──────────────────
    recomp_items, recomp_corrections = recompute_super(
        observed_elements = obs,
        floor_heights     = fh,
        parsed_cols       = col_schedule,
        slab_thickness    = slab_t,
        parapet_type      = parapet_type,
    )

    if recomp_corrections:
        print("\n── RECOMPUTE CORRECTIONS ─────────────────────────────────")
        for c in recomp_corrections:
            print(c)
        print("───────────────────────────────────────────────────────────\n")

    # Store recomputed items
    r["qtoItems"] = recomp_items

    # Sanity check
    items_dict = {it.get("id",""): it.get("totalQty",0) for it in recomp_items}
    run_all_checks("super", items_dict=items_dict,
                   observed=obs, floor_heights=fh)

    # Re-save with recomputed values
    with open(f"{name}_super_result.json", "w", encoding="utf-8") as f:
        json.dump(r, f, indent=2, ensure_ascii=False)

    # ── Print floor heights ────────────────────────────────────────
    fh = r.get("floorHeights", {})
    print(f"\nFLOOR HEIGHTS:")
    print(f"  GF floor height : {fh.get('gf_floor_height_m', '?')} m")
    print(f"  FF floor height : {fh.get('ff_floor_height_m', '?')} m")
    print(f"  Parapet height  : {fh.get('parapet_height_m', '?')} m")
    print(f"  Source          : {fh.get('source', '?')}")

    # ── Print QTO table ────────────────────────────────────────────
    items = r.get("qtoItems", [])
    qs    = r.get("questions", [])

    print(f"\n{'='*65}")
    print(f"QTO ITEMS — PROJECT {name} SUPERSTRUCTURE ({len(items)}):")
    print(f"{'='*65}")
    for item in items:
        status = "[OK]" if item.get("canCalculate") else "[--]"
        qty    = item.get("totalQty", 0)
        unit   = item.get("unit", "")
        desc   = item.get("description", "")
        bd     = item.get("breakdown", "")
        print(f"  {status} {item['id']:<22} — {desc:<40} => {qty} {unit}")
        if bd:
            # Print breakdown indented, max 120 chars per line
            for seg in [bd[i:i+110] for i in range(0, len(bd), 110)]:
                print(f"         {seg}")

    if qs:
        print(f"\nQUESTIONS NEEDED ({len(qs)}):")
        for q in qs:
            print(f"  [{q.get('id','')}] {q.get('text','')} (suggested: {q.get('suggested','')})")

    summary = r.get("summary", "")
    if summary:
        print(f"\nSUMMARY:\n  {summary}")

    warnings = r.get("warnings", [])
    if warnings:
        print(f"\nWARNINGS:")
        for w in warnings:
            print(f"  {w}")

    print("="*65)


# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    for cfg in PROJECTS:
        run_project(cfg)
