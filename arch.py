import fitz, base64, json
import re as _re

from utils import page_to_b64, pdf_to_b64


# ═══════════════════════════════════════════════════════════════
# D&W TEXT PARSER — extracts doors/windows schedule from PDF text
# ═══════════════════════════════════════════════════════════════

def _parse_dw_from_text(text):
    """
    Parse Doors & Windows schedule from PDF text layer.
    Returns list of {id, cat, w, h, n, a} or None if parsing fails.
    """
    entries = []
    lines = text.split("\n")
    seen = set()

    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue

        # Match type IDs: D1, D2, W1, W2, SD1, GD1 etc.
        m = _re.match(r'^((?:S?G?[DW])\d+[A-Z]?)\b', s, _re.I)
        if not m:
            continue
        type_id = m.group(1).upper()
        if type_id in seen:
            continue
        seen.add(type_id)

        cat = "door" if "D" in type_id else "win"

        # Search this line and next 5 lines for dimensions
        search_block = " ".join(
            lines[j].strip() for j in range(i, min(i + 6, len(lines)))
        )

        # Pattern 1: WxH format — 90x210, 0.90x2.10, 900x2100
        dim_m = _re.search(
            r'(\d+\.?\d*)\s*[×xX]\s*(\d+\.?\d*)', search_block
        )
        if not dim_m:
            # Pattern 2: separate numbers on same/next lines
            nums = _re.findall(r'(?<!\d)(\d+\.?\d+)(?!\d)', search_block)
            nums = [float(n) for n in nums if 0.3 < float(n) < 300]
            if len(nums) >= 2:
                w, h = nums[0], nums[1]
            else:
                continue
        else:
            w, h = float(dim_m.group(1)), float(dim_m.group(2))

        # Convert to metres if in cm (>5) or mm (>500)
        if w > 500:
            w /= 1000
        elif w > 5:
            w /= 100
        if h > 500:
            h /= 1000
        elif h > 5:
            h /= 100

        # Sanity check
        if not (0.30 <= w <= 5.00 and 0.30 <= h <= 5.00):
            continue

        # Look for count
        count = 0
        cnt_m = _re.search(r'(?:qty|count|no\.?\s*|×\s*)(\d+)', search_block, _re.I)
        if cnt_m:
            count = int(cnt_m.group(1))

        entries.append({
            "id": type_id,
            "cat": cat,
            "w": round(w, 2),
            "h": round(h, 2),
            "n": count,
            "a": round(w * h, 3),
        })

    return entries if entries else None

_BASE_1577 = r"C:\Users\basel\Downloads\The System\FINAL DRAWINGS\New folder (3)"
_ARCH_3246 = r"C:\Users\basel\Downloads\The System\TINDER\DRAWINGS\PDF"

PROJECTS = [
    {
        "name":         "3246",
        "multi_pdf":    False,
        "arch_pdf":     f"{_ARCH_3246}\\3246 - ARCHITECT.pdf",
        "pg_gf_plan":   1,    # 0-based: Ground Floor Plan
        "pg_ff_plan":   2,    # 0-based: First Floor Plan
        "pg_elev1":     4,    # 0-based: Elevations A106 (Front+Right)
        "pg_elev2":     5,    # 0-based: Elevations A107 (Rear+Left)
        "pg_dw_sched":  9,    # 0-based: Windows & Doors Details
        "gf_height_m":  3.23,
        "ff_height_m":  4.20,
        "roof_slab_m2": 286.848,   # area m² from 3246_super_result observedElements
        "img_scale":    1.0,
    },
    {
        "name":        "1577",
        "multi_pdf":   True,
        "gf_plan":     f"{_BASE_1577}\\gf plan.pdf",
        "ff_plan":     f"{_BASE_1577}\\1st flr plan.pdf",
        "elevation1":  f"{_BASE_1577}\\ele.1.pdf",
        "elevation2":  f"{_BASE_1577}\\ele.2.pdf",
        "dw_sched":    f"{_BASE_1577}\\ARC-1577-MUN-01-Model.pdf",
        "gf_height_m":  3.20,
        "ff_height_m":  3.20,
        "roof_slab_m2": 160.0,     # area m² from 1577_super_result observedElements
        "img_scale":    0.75,   # smaller scale — 1577 drawings are A1/A0, need fewer tokens
    },
]


def run_project(cfg):
    name       = cfg["name"]
    gf_h       = cfg["gf_height_m"]
    ff_h       = cfg["ff_height_m"]
    roof_area  = cfg["roof_slab_m2"]
    parapet_h  = cfg.get("parapet_h", 1.20)
    combo      = round(roof_area * 1.2, 3)
    ext_h      = round(gf_h + ff_h + parapet_h, 3)
    scale      = cfg.get("img_scale", 1.5)

    print("\n" + "="*65)
    print(f"  PROJECT {name} — ARCHITECTURAL FINISHES")
    print("="*65)
    print(f"  GF h={gf_h}m | FF h={ff_h}m | Roof={roof_area}m² | Combo={combo}m² | ExtH={ext_h}m | Parapet={parapet_h}m | scale={scale}x")

    # ── Render images ──────────────────────────────────────────────
    parts = []
    if not cfg["multi_pdf"]:
        doc = fitz.open(cfg["arch_pdf"])
        for lbl, idx in [
            ("GF Floor Plan",            cfg["pg_gf_plan"]),
            ("FF Floor Plan",            cfg["pg_ff_plan"]),
            ("Elevations Front+Right",   cfg["pg_elev1"]),
            ("Elevations Rear+Left",     cfg["pg_elev2"]),
            ("Windows & Doors Schedule", cfg["pg_dw_sched"]),
        ]:
            b64, kb = page_to_b64(doc, idx, scale=None)
            parts.append({"inlineData": {"mimeType": "image/png", "data": b64}})
            print(f"  [{lbl}]: {kb} KB")
        doc.close()
    else:
        for lbl, path in [
            ("GF Floor Plan",             cfg["gf_plan"]),
            ("FF Floor Plan",             cfg["ff_plan"]),
            ("Elevations A-06",           cfg["elevation1"]),
            ("Elevations A-07",           cfg["elevation2"]),
            ("Municipality / D&W Elev",  cfg["dw_sched"]),
        ]:
            b64, kb = pdf_to_b64(path, scale=None)
            parts.append({"inlineData": {"mimeType": "image/png", "data": b64}})
            print(f"  [{lbl}]: {kb} KB")

    print(f"  Total images: {len(parts)}")

    # ══════════════════════════════════════════════════════════════════
    # LOAD STRUCTURAL ANCHORS (grid dims from sub result)
    # ══════════════════════════════════════════════════════════════════
    import os as _os
    _HERE = _os.path.dirname(_os.path.abspath(__file__))
    grid_L, grid_W = None, None
    sub_path = _os.path.join(_HERE, f"{name}_result.json")
    if _os.path.exists(sub_path):
        try:
            with open(sub_path, encoding="utf-8") as _f:
                _sub = json.load(_f)
            gd = _sub.get("gridDims", {})
            grid_L = gd.get("L_m")
            grid_W = gd.get("W_m")

            # Fallback: extract from slab_on_grade breakdown "L × W × 0.10"
            if not grid_L:
                for it in _sub.get("qtoItems", []):
                    if it.get("id") == "slab_on_grade":
                        bd = it.get("breakdown", "")
                        import re as _re2
                        m = _re2.search(r'(\d+\.?\d*)\s*[×x]\s*(\d+\.?\d*)\s*[×x]\s*0\.1', bd)
                        if m:
                            grid_L = float(m.group(1))
                            grid_W = float(m.group(2))
                            if grid_L < grid_W:
                                grid_L, grid_W = grid_W, grid_L
                        break

            if grid_L and grid_W:
                print(f"  📐 Structural anchors loaded: L={grid_L}m W={grid_W}m "
                      f"Area={round(grid_L*grid_W, 1)}m² Perim={round(2*(grid_L+grid_W), 1)}m")
        except Exception as e:
            print(f"  ⚠ Could not load sub result: {e}")

    # ══════════════════════════════════════════════════════════════════
    # TRY D&W TEXT EXTRACTION (100% accurate for text-based PDFs)
    # ══════════════════════════════════════════════════════════════════
    parsed_dw = None
    try:
        dw_text = ""
        if not cfg["multi_pdf"]:
            _doc = fitz.open(cfg["arch_pdf"])
            dw_text = _doc[cfg["pg_dw_sched"]].get_text()
            _doc.close()
        else:
            _doc = fitz.open(cfg["dw_sched"])
            dw_text = _doc[0].get_text()
            _doc.close()

        if dw_text.strip():
            parsed_dw = _parse_dw_from_text(dw_text)
            if parsed_dw:
                print(f"  ✓ D&W parsed from text layer: {len(parsed_dw)} entries")
                for e in parsed_dw:
                    print(f"     {e['id']}: {e['cat']} {e['w']}×{e['h']}m n={e['n']}")
    except Exception as e:
        print(f"  ⚠ D&W text extraction failed: {e}")

    # ══════════════════════════════════════════════════════════════════
    # VISION: Per-page focused calls (improved strategy)
    # ══════════════════════════════════════════════════════════════════
    from vision_reader import read_arch as _vision_read_arch
    from compute_arch import compute_arch_items
    from guards import run_all_checks

    observed, dw, warnings = _vision_read_arch(
        image_parts=parts, gf_h=gf_h, ff_h=ff_h, ext_h=ext_h,
        combo=combo, roof_area=roof_area, parapet_h=parapet_h,
        passes=3, name=name,
        grid_L=grid_L, grid_W=grid_W, parsed_dw=parsed_dw,
    )

    if warnings:
        print(f"  ⚠ Vision warnings: {warnings}")

    # ── Deterministic compute ─────────────────────────────────────
    items = compute_arch_items(observed, dw, gf_h, ff_h, roof_area, parapet_h)

    # Build result dict
    r = {"observed": observed, "dw": dw, "items": items, "warnings": warnings}

    # Sanity check
    items_check = {it["id"]: it["q"] for it in items}
    run_all_checks("arch", items_dict=items_check, observed=observed)

    # Save result
    with open(f"{name}_arch_result.json", "w", encoding="utf-8") as f:
        json.dump(r, f, indent=2, ensure_ascii=False)
    print(f"Saved {name}_arch_result.json")

    # ── Print table ────────────────────────────────────────────────
    items = r.get("items", r.get("qtoItems", []))
    print(f"\n{'='*65}")
    print(f"QTO — PROJECT {name} ARCHITECTURAL ({len(items)} items):")
    print(f"{'='*65}")
    for it in items:
        iid  = it.get("id", it.get("id", ""))
        qty  = it.get("q",  it.get("totalQty", 0))
        unit = it.get("u",  it.get("unit", ""))
        bd   = it.get("bd", it.get("breakdown", ""))
        print(f"  {iid:<22} => {qty:>10}  {unit}   {bd[:60]}")

    # D&W schedule
    dw = r.get("dw", r.get("doorsAndWindowsSchedule", []))
    if dw:
        print(f"\nD&W SCHEDULE ({len(dw)} types):")
        for s in dw:
            cat = s.get("cat", s.get("category", ""))
            iid = s.get("id", s.get("typeId", ""))
            w   = s.get("w",  s.get("width_m", 0))
            h   = s.get("h",  s.get("height_m", 0))
            n   = s.get("n",  s.get("count", 0))
            a   = s.get("a",  s.get("totalArea_m2", 0))
            print(f"  {cat:<6} {iid:<5} {w}x{h}m  x{n}  = {a} m²")

    warns = r.get("warn", r.get("warnings", []))
    if warns:
        print(f"\nWARNINGS:")
        for w in warns:
            print(f"  {w}")

    print("="*65)


# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    for cfg in PROJECTS:
        run_project(cfg)
