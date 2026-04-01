"""
utils.py — Shared utilities for QTO-AI pipeline.
"""
import fitz, base64, json, re as _re


# ═══════════════════════════════════════════════════════════════════
# AUTO-SCALE — Detect page size → optimal rendering scale
# ═══════════════════════════════════════════════════════════════════
# Gemini performs best at ~3000–4000 px on the long edge.
# A4 (595×842 pt) needs scale=4.0 → 3368 px.
# A1 (1684×2384 pt) needs scale=1.5 → 3576 px.
# A0 (2384×3370 pt) needs scale=1.2 → 4044 px.

_TARGET_LONG_PX = 3500   # target pixels on longest edge


def auto_scale(page):
    """Return optimal scale factor for a PDF page to hit ~3500px long edge."""
    w, h = page.rect.width, page.rect.height
    long_edge = max(w, h)
    if long_edge < 1:
        return 2.0
    s = _TARGET_LONG_PX / long_edge
    # Clamp to [1.0, 5.0] — below 1.0 loses detail, above 5.0 wastes tokens
    return max(1.0, min(5.0, round(s, 2)))


def page_to_b64(doc, page_idx, scale=None):
    """Render a single PDF page to base64 PNG. Auto-scales if scale=None."""
    page = doc[page_idx]
    if scale is None:
        scale = auto_scale(page)
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
    png = pix.tobytes("png")
    kb  = len(png) // 1024
    return base64.b64encode(png).decode(), kb


def pdf_to_b64(pdf_path, scale=None):
    """Open a single-page PDF and render page 0 to base64 PNG. Auto-scales if scale=None."""
    doc = fitz.open(pdf_path)
    b64, kb = page_to_b64(doc, 0, scale)
    doc.close()
    return b64, kb


def repair_json(raw, name):
    """
    4-phase JSON repair for truncated Gemini responses.
    Phase 1: scan bracket/string state
    Phase 2: close unterminated string
    Phase 3: strip trailing comma + handle dangling colon
    Phase 4: close all open brackets
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  JSON truncated at char {e.pos} — attempting repair...")
        truncated = raw[:e.pos]

        # Phase 1: scan bracket/string state
        opens, in_str, esc = [], False, False
        for ch in truncated:
            if esc:              esc = False; continue
            if ch == '\\':       esc = True;  continue
            if ch == '"':        in_str = not in_str; continue
            if in_str:           continue
            if ch in ('{', '['): opens.append(']' if ch == '[' else '}')
            elif ch in ('}', ']') and opens: opens.pop()

        # Phase 2: close unterminated string
        if in_str:
            truncated += '"'

        # Phase 3: strip trailing comma/whitespace
        truncated = _re.sub(r'[,\s]+$', '', truncated)

        # Phase 3b: if dangling colon (key with no value), add empty string
        if _re.search(r':\s*$', truncated):
            truncated += '""'

        # Phase 4: close all open brackets
        repaired = truncated + ''.join(reversed(opens))

        try:
            r = json.loads(repaired)
            print("  JSON repair succeeded.")
            return r
        except Exception:
            print(f"  Repair FAILED — see {name}_raw.txt")
            raise


def extract_super_heights(name, here_dir):
    """
    Read {name}_super_result.json → return (gf_h, ff_h, roof_slab_m2, parapet_h).
    Falls back to defaults if values not found.
    """
    import os
    path = os.path.join(here_dir, f"{name}_super_result.json")
    if not os.path.exists(path):
        print(f"  ⚠ {name}_super_result.json not found")
        return 3.20, 3.20, 160.0, 1.20

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    fh   = data.get("floorHeights", {})
    gf_h      = fh.get("gf_floor_height_m")
    ff_h      = fh.get("ff_floor_height_m")
    parapet_h = fh.get("parapet_height_m")

    # Roof slab area from observedElements
    roof_area = None
    for el in data.get("observedElements", []):
        t  = str(el.get("type", "")).lower()
        fl = str(el.get("floor", "")).upper()
        if t == "slab" and fl in ("ROOF", "RF", "ROOF SLAB"):
            roof_area = el.get("area_m2")
            break

    # Fallback: back-calc from roof_slab qty / thickness
    if roof_area is None:
        for item in data.get("qtoItems", []):
            if item.get("id") == "roof_slab":
                vol = item.get("totalQty", 0)
                for el in data.get("observedElements", []):
                    if str(el.get("type", "")).lower() == "slab":
                        th = el.get("thickness_m", 0.20)
                        if th and th > 0:
                            roof_area = round(vol / th, 3)
                            break
                if roof_area:
                    break

    gf_h      = float(gf_h)      if gf_h      else 3.20
    ff_h      = float(ff_h)      if ff_h      else 3.20
    roof_area = float(roof_area)  if roof_area else 160.0
    parapet_h = float(parapet_h)  if parapet_h else 1.20

    print(f"  → GF h={gf_h}m | FF h={ff_h}m | Roof={roof_area}m² | Parapet={parapet_h}m")
    return gf_h, ff_h, roof_area, parapet_h


def load_qty_from_result(json_path):
    """Load QTO items from a result JSON. Returns dict: item_id → {qty, unit, bd}."""
    import os
    result = {}
    if not os.path.exists(json_path):
        return result
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("qtoItems") or data.get("items", [])
    for item in items:
        iid = str(item.get("id", "")).strip()
        result[iid] = {
            "qty":  item.get("totalQty") if item.get("totalQty") is not None else item.get("q", 0),
            "unit": item.get("unit") or item.get("u", ""),
            "bd":   item.get("breakdown") or item.get("bd", ""),
        }
    return result
