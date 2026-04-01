"""
vision_reader.py — READ-ONLY Vision Module for QTO-AI
═══════════════════════════════════════════════════════
Gemini reads drawings and returns RAW observed data ONLY.
NO calculations — just measurements, counts, lengths, areas.

Multi-pass with majority consensus for reliability.
Guards validate and trigger focused re-reads.
"""

import json, urllib.request, time
from config import API_KEY, MODEL, URL, URL_PRO
from utils import repair_json


# ═══════════════════════════════════════════════════════════════
# CORE: Call Gemini with read-only prompt
# ═══════════════════════════════════════════════════════════════

def _call_gemini(prompt_text, image_parts, label="vision", use_pro=False):
    """Send prompt + images to Gemini. Returns parsed JSON or None.
    use_pro=True → gemini-2.5-pro (better spatial reasoning, slower)."""
    api_url = URL_PRO if use_pro else URL
    timeout = 600 if use_pro else 300
    thinking = 16000 if use_pro else 8000

    body = json.dumps({
        "contents": [{"role": "user", "parts": [
            {"text": prompt_text},
            *image_parts
        ]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 65536,
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingBudget": thinking}
        }
    }).encode()

    req = urllib.request.Request(api_url, data=body,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        # Handle thinking models: find last non-thought text part
        parts = data["candidates"][0]["content"]["parts"]
        raw = None
        for p in reversed(parts):
            if "text" in p and not p.get("thought"):
                raw = p["text"]
                break
        if raw is None:
            raw = parts[-1].get("text", parts[0].get("text", "{}"))
        # Save raw for debugging
        try:
            with open(f"{label}_raw.txt", "w", encoding="utf-8") as f:
                f.write(raw)
        except:
            pass
        return repair_json(raw, label)
    except Exception as e:
        print(f"  ✗ Gemini call failed ({label}): {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# MULTI-PASS CONSENSUS
# ═══════════════════════════════════════════════════════════════

def _median(values):
    """Return median of numeric list."""
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0
    if n % 2 == 1:
        return s[n // 2]
    return round((s[n // 2 - 1] + s[n // 2]) / 2, 3)


def _high_variance(values, threshold=0.5):
    """Check if values have high coefficient of variation (>threshold)."""
    if len(values) < 2:
        return False
    mean = sum(values) / len(values)
    if mean == 0:
        return max(values) > 0  # any non-zero when mean=0 is high variance
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    cv = (variance ** 0.5) / abs(mean)
    return cv > threshold


def _build_targeted_count_prompt(mark, dims, all_marks_with_dims):
    """
    Build a targeted prompt asking Gemini to count ONE footing type only.
    Includes all other types as context to avoid confusion.
    """
    L = dims.get("L", "?")
    W = dims.get("W", "?")
    H = dims.get("H", "?")
    others = "\n".join(
        f"  - {m}: {d.get('L')}×{d.get('W')}m (DO NOT count these)"
        for m, d in all_marks_with_dims.items() if m != mark
    )
    return f"""Look at this Foundation Layout drawing carefully.

COUNT ONLY: Footing type '{mark}' (size {L}×{W}×{H} m)

Other footing types in this drawing (do NOT count these):
{others}

How to count '{mark}':
1. Look for labels/marks reading '{mark}' anywhere on the plan
2. Also look for footings sized approximately {L}×{W}m without a clear label (may be unlabeled)
3. Scan the ENTIRE plan: top-left → top-right → bottom-left → bottom-right
4. Count every single instance

Return ONLY this JSON (no other text):
{{"mark":"{mark}","count":0,"locations":"describe where you found each one, e.g. grid A-1, B-3, C-5","confidence":"high/medium/low"}}"""


def _build_targeted_tb_prompt(mark, b, d, all_tb_marks):
    """
    Build a targeted prompt asking Gemini to measure ONE TB type total run length.
    """
    others = ", ".join(m for m in all_tb_marks if m != mark)
    return f"""Look at this Tie Beam Layout drawing carefully.

MEASURE TOTAL RUN LENGTH OF: Tie Beam type '{mark}' (cross-section {b}×{d}m)

Other tie beam types in this drawing (ignore these): {others}

How to measure '{mark}':
1. Find every segment labeled '{mark}' on the plan
2. Read the dimension written on each segment (in metres)
3. If no dimension is written, measure using the grid spacing shown
4. Add up ALL segment lengths to get the total

Important: Report the SUM of ALL '{mark}' segments across the entire plan.
A typical villa tie beam total is 10–200m per type.

Return ONLY this JSON (no other text):
{{"mark":"{mark}","totalLength_m":0,"segments":"list each segment length found, e.g. A1-A6=12.5m, B1-B3=6.0m","confidence":"high/medium/low"}}"""


def _match_size_to_schedule(size_str, schedule):
    """
    Match a footing size string (e.g., '280x340', '130x170') to schedule.
    Returns the correct mark or None if no match.
    Schedule format: [{'mark':'F1', 'L_cm':130, 'W_cm':170, ...}, ...]
    """
    if not size_str or not schedule:
        return None
    # Parse size string: "280x340", "280×340", "280 x 340", etc.
    import re
    nums = re.findall(r'\d+', str(size_str))
    if len(nums) < 2:
        return None
    a, b = int(nums[0]), int(nums[1])
    # Try both orientations
    dims = sorted([a, b])
    best_mark = None
    best_dist = 999
    for s in schedule:
        sched_dims = sorted([s.get("L_cm", 0), s.get("W_cm", 0)])
        dist = abs(dims[0] - sched_dims[0]) + abs(dims[1] - sched_dims[1])
        if dist < best_dist:
            best_dist = dist
            best_mark = s.get("mark", "")
    # Only accept if within 20cm tolerance total
    if best_dist <= 20:
        return best_mark
    return None


def _consensus_sub(results, parsed_footings=None):
    """
    Given N pass results for sub, return consensus observed data.
    Uses gridMap (if available) for footing counts — more reliable than direct counting.
    Uses tbSegments (if available) for TB lengths — more reliable than total estimates.
    Falls back to observedElements if gridMap/tbSegments not present.
    """
    # ── Stage 1: Extract footing counts from gridMap (preferred) and observedElements (fallback)
    ftg_counts_from_grid = {}   # mark → [count_pass1, count_pass2, ...]
    ftg_counts_from_obs  = {}
    tb_lengths_from_segs = {}   # mark → [total_pass1, total_pass2, ...]
    tb_lengths_from_obs  = {}
    col_counts = {}

    for r in results:
        # --- Footing counts from gridMap (with size-based correction) ---
        grid_map = r.get("gridMap", [])
        if grid_map and isinstance(grid_map, list) and len(grid_map) > 0:
            grid_count = {}   # mark → count for THIS pass
            for entry in grid_map:
                ftg = str(entry.get("footing", "")).upper().strip()
                size_cm = entry.get("size_cm", "")
                # Try size-based matching first (more reliable than label)
                if size_cm and parsed_footings:
                    matched = _match_size_to_schedule(size_cm, parsed_footings)
                    if matched:
                        ftg = matched.upper()
                if ftg and ftg != "NONE" and ftg != "":
                    grid_count[ftg] = grid_count.get(ftg, 0) + 1
            for mark, cnt in grid_count.items():
                ftg_counts_from_grid.setdefault(mark, []).append(cnt)

        # --- TB lengths from tbSegments ---
        tb_segs = r.get("tbSegments", [])
        if tb_segs and isinstance(tb_segs, list) and len(tb_segs) > 0:
            seg_lengths = {}   # mark → total for THIS pass
            for seg in tb_segs:
                mark = str(seg.get("type", "")).upper().strip()
                length = float(seg.get("length_m", 0) or 0)
                if mark and length > 0:
                    seg_lengths[mark] = seg_lengths.get(mark, 0) + length
            for mark, total in seg_lengths.items():
                tb_lengths_from_segs.setdefault(mark, []).append(round(total, 2))

        # --- Fallback: from observedElements ---
        obs = r.get("observedElements", [])
        for el in obs:
            etype = str(el.get("type", "")).lower()
            mark = str(el.get("mark", "")).upper()
            if etype in ("footing", "isolated_footing", "foundation"):
                ftg_counts_from_obs.setdefault(mark, []).append(el.get("count", 0) or 0)
            elif etype in ("tiebeam", "tie_beam", "tb", "tie beam"):
                dims = el.get("dims", {})
                length = dims.get("L") or dims.get("totalLength_m") or el.get("totalLength_m") or 0
                tb_lengths_from_obs.setdefault(mark, []).append(float(length))
            elif etype in ("column", "neck_column"):
                col_counts.setdefault(mark, []).append(el.get("count", 0) or 0)

    # ── Stage 2: Choose best source for footings
    # Prefer gridMap counts (they come from systematic grid-intersection scanning)
    ftg_counts = ftg_counts_from_grid if ftg_counts_from_grid else ftg_counts_from_obs
    use_grid = bool(ftg_counts_from_grid)

    # ── Stage 3: Choose best source for TBs
    tb_lengths = tb_lengths_from_segs if tb_lengths_from_segs else tb_lengths_from_obs
    use_segs = bool(tb_lengths_from_segs)

    # ── Stage 4: Build consensus observedElements ──
    consensus_obs = []

    for mark, counts in ftg_counts.items():
        med = _median(counts)
        # Find dims from first result
        dims = {}
        for r in results:
            for el in r.get("observedElements", []):
                if str(el.get("mark","")).upper() == mark and \
                   str(el.get("type","")).lower() in ("footing","isolated_footing","foundation"):
                    dims = el.get("dims", {})
                    break
            if dims:
                break
        src = "gridMap" if use_grid else "observedElements"
        consensus_obs.append({
            "type": "Footing", "mark": mark, "count": int(round(med)),
            "dims": dims,
            "notes": f"consensus of {len(counts)} passes ({src}): {counts} → {med}"
        })

    for mark, lengths in tb_lengths.items():
        med = _median(lengths)
        dims = {}
        for r in results:
            for el in r.get("observedElements", []):
                if str(el.get("mark","")).upper() == mark and \
                   str(el.get("type","")).lower() in ("tiebeam","tie_beam","tb","tie beam"):
                    dims = el.get("dims", {})
                    break
            if dims:
                break
        dims_out = dict(dims) if dims else {}
        dims_out["L"] = round(med, 1)
        src = "tbSegments" if use_segs else "observedElements"
        consensus_obs.append({
            "type": "Tie Beam", "mark": mark,
            "dims": dims_out,
            "notes": f"consensus of {len(lengths)} passes ({src}): {lengths} → {med}"
        })

    for mark, counts in col_counts.items():
        med = _median(counts)
        dims = {}
        for r in results:
            for el in r.get("observedElements", []):
                if str(el.get("mark","")).upper() == mark and \
                   str(el.get("type","")).lower() in ("column","neck_column"):
                    dims = el.get("dims", {})
                    break
            if dims:
                break
        consensus_obs.append({
            "type": "Column", "mark": mark, "count": int(round(med)),
            "dims": dims, "notes": f"consensus of {len(counts)} passes: {counts} → {med}"
        })

    return consensus_obs


def _consensus_super(results):
    """
    Given N pass results for super, return consensus.
    Median for: column counts, slab areas, beam lengths, floor heights, parapet.
    """
    # Floor heights
    gf_heights = []
    ff_heights = []
    parapet_heights = []

    # Observed
    col_by_floor_mark = {}  # (floor, mark) → [count, count, ...]
    slab_by_floor = {}      # floor → [area, area, ...]
    beam_by_floor = {}      # floor → [total_length, ...]
    rf_perimeters = []

    for r in results:
        fh = r.get("floorHeights", {})
        if fh.get("gf_floor_height_m"):
            gf_heights.append(float(fh["gf_floor_height_m"]))
        if fh.get("ff_floor_height_m"):
            ff_heights.append(float(fh["ff_floor_height_m"]))
        if fh.get("parapet_height_m"):
            parapet_heights.append(float(fh["parapet_height_m"]))

        for el in r.get("observedElements", []):
            etype = str(el.get("type","")).lower()
            floor = str(el.get("floor","")).upper()
            mark = str(el.get("mark","")).upper()

            if etype == "column":
                key = (floor, mark)
                col_by_floor_mark.setdefault(key, []).append(el.get("count",0) or 0)
            elif etype == "slab":
                slab_by_floor.setdefault(floor, []).append(el.get("area_m2",0) or 0)
            elif etype == "beam":
                beam_by_floor.setdefault(floor, []).append(el.get("totalLength_m",0) or 0)
            elif etype == "parapet":
                rf_perimeters.append(el.get("RF_perimeter_m",0) or 0)

    # Build consensus
    consensus_fh = {
        "gf_floor_height_m": round(_median(gf_heights), 2) if gf_heights else 3.20,
        "ff_floor_height_m": round(_median(ff_heights), 2) if ff_heights else 3.20,
        "parapet_height_m":  round(_median(parapet_heights), 2) if parapet_heights else 1.20,
        "source": f"consensus of {len(results)} passes"
    }

    consensus_obs = []
    for (floor, mark), counts in col_by_floor_mark.items():
        consensus_obs.append({
            "type": "column", "mark": mark, "floor": floor,
            "count": int(round(_median(counts))),
            "notes": f"consensus: {counts} → {_median(counts)}"
        })
    for floor, areas in slab_by_floor.items():
        consensus_obs.append({
            "type": "slab", "floor": floor,
            "area_m2": round(_median(areas), 2),
            "notes": f"consensus: {areas} → {_median(areas)}"
        })
    for floor, lengths in beam_by_floor.items():
        consensus_obs.append({
            "type": "beam", "floor": floor,
            "totalLength_m": round(_median(lengths), 1),
            "notes": f"consensus: {lengths} → {_median(lengths)}"
        })
    if rf_perimeters:
        consensus_obs.append({
            "type": "parapet",
            "RF_perimeter_m": round(_median(rf_perimeters), 1),
            "notes": f"consensus: {rf_perimeters} → {_median(rf_perimeters)}"
        })

    return consensus_fh, consensus_obs


def _consensus_arch(results):
    """
    Given N pass results for arch, return consensus observed + dw.
    For each observed type×floor: median of numeric fields.
    For D&W: median counts.
    """
    # Group observed by (type, floor)
    obs_groups = {}  # (t, f) → [dict, dict, ...]
    dw_groups = {}   # id → [dict, dict, ...]

    for r in results:
        for o in r.get("observed", []):
            key = (o.get("t",""), o.get("f",""))
            obs_groups.setdefault(key, []).append(o)
        for d in r.get("dw", []):
            did = d.get("id","")
            dw_groups.setdefault(did, []).append(d)

    # Consensus observed
    consensus_obs = []
    for (t, f), entries in obs_groups.items():
        merged = {"t": t, "f": f}
        # Get all numeric keys
        num_keys = set()
        for e in entries:
            for k, v in e.items():
                if k not in ("t","f","rooms") and isinstance(v, (int, float)):
                    num_keys.add(k)
        for k in num_keys:
            vals = [e.get(k, 0) for e in entries if isinstance(e.get(k, 0), (int, float))]
            merged[k] = round(_median(vals), 2)
        # rooms: take the longest string (most complete)
        rooms_list = [e.get("rooms","") for e in entries if e.get("rooms")]
        if rooms_list:
            merged["rooms"] = max(rooms_list, key=len)
        consensus_obs.append(merged)

    # Consensus D&W
    consensus_dw = []
    for did, entries in dw_groups.items():
        merged = {"id": did}
        merged["cat"] = entries[0].get("cat", "")
        for k in ("w","h","n","a"):
            vals = [e.get(k, 0) for e in entries if isinstance(e.get(k, 0), (int, float))]
            if vals:
                merged[k] = round(_median(vals), 3)
        consensus_dw.append(merged)

    return consensus_obs, consensus_dw


# ═══════════════════════════════════════════════════════════════
# PHASE-SPECIFIC READ-ONLY PROMPTS
# ═══════════════════════════════════════════════════════════════

def _sub_read_prompt(parsed_context, excav_depth, gf_level, cfg):
    """Build read-only prompt for substructure using grid-intersection + size-matching."""
    return f"""You are reading structural engineering drawings for a UAE villa.
Your ONLY job: READ and REPORT what you see. Do NOT calculate any quantities.

IMAGES (in order):
1. Foundation Layout — shows footing locations with type labels and SIZE annotations
2. Column Layout + Schedule — column types and their sections
3. Tie Beam Layout — TB segments with type labels and dimensions

PARSED DATA (100% accurate from PDF text layer):
{parsed_context}

══════════════════════════════════════════════════════════
TASK A: FOOTINGS — GRID-INTERSECTION + SIZE VERIFICATION
══════════════════════════════════════════════════════════

Use this EXACT procedure:

Step 1 — Read the GRID:
  • Column grid labels LEFT to RIGHT (e.g., A, B, C, D, E)
  • Row grid labels TOP to BOTTOM (e.g., 1, 2, 3, 4, 5, 6)

Step 2 — Visit EVERY grid intersection, row by row:
  At each intersection where a footing exists:
  a) Read the TYPE LABEL written on/near the footing (F1, F2, CF1, etc.)
  b) Read the SIZE ANNOTATION on the footing (e.g., 280, 340, or 260×320)
     - These are written as individual numbers on the short and long sides
     - Size is in CENTIMETRES

Step 3 — SIZE VERIFICATION (critical for accuracy):
  Match each footing's SIZE to the SCHEDULE OF FOOTINGS above.
  If the label says F1 but the size reads ~280×340, it is actually F5.
  The SIZE always wins over a misread label.
  Schedule reference:
    F1=130×170, F2=200×260, F3=240×280, F4=260×320, F5=280×340
    CF1=280×400, CF2=300×400 (combined footings are larger)

Step 4 — Count per VERIFIED type from your grid map.
  Total footings in a typical UAE villa: 25-40.

══════════════════════════════════════════════════════════
TASK B: TIE BEAMS — SEGMENT-BY-SEGMENT method
══════════════════════════════════════════════════════════

Do NOT estimate total lengths. Read EACH segment individually.

For each TB segment visible on the Tie Beam Layout:
  • TYPE label (TB1, TB2, TB3, etc.)
  • FROM → TO grid points (e.g., A-1 → E-1 along row 1)
  • LENGTH dimension written on or near the segment (metres)
  • If no dim written, use the grid bay spacing

List ALL segments, then sum by type.
A typical villa has 100-300m total TB length (all types combined).

IMPORTANT: The Tie Beam Layout may show a SCHEDULE of TB types beyond
the parsed data (e.g., TB4, TB5). Include those extra types WITH their
b×d dims from the image schedule.

══════════════════════════════════════════════════════════
TASK C: COLUMNS — From Schedule of Columns image
══════════════════════════════════════════════════════════
Read each column mark with b × d dimensions (cm).
For entries with '?' in parsed data, read from the schedule image.

══════════════════════════════════════════════════════════
TASK D: GRID DIMENSIONS
══════════════════════════════════════════════════════════
Overall L (sum of bay spacings in long direction) and W (short direction).

══════════════════════════════════════════════════════════
TASK E: LEVELS
══════════════════════════════════════════════════════════
GF slab level from any visible note/section.

CRITICAL: Do NOT calculate any QTO items. Just report observations.

Return ONLY valid JSON:
{{
  "gridMap": [
    {{"grid":"A-1","footing":"F1","size_cm":"130x170"}},
    {{"grid":"B-1","footing":"F3","size_cm":"240x280"}}
  ],
  "tbSegments": [
    {{"type":"TB1","from":"A-1","to":"E-1","length_m":19.22,"notes":"row 1"}},
    {{"type":"TB2","from":"A-1","to":"A-3","length_m":7.0,"notes":"col A"}}
  ],
  "observedElements": [
    {{"type":"Footing","mark":"F1","count":0,"dims":{{"L":0,"W":0,"H":0,"unit":"m"}},"locations":"grid list","notes":""}},
    {{"type":"Tie Beam","mark":"TB1","dims":{{"L":0,"b":0,"d":0,"unit":"m"}},"notes":"total from segments"}},
    {{"type":"Column","mark":"C1","dims":{{"b":0,"d":0,"unit":"m"}},"notes":"from schedule"}}
  ],
  "gridDims": {{"L_m":0,"W_m":0}},
  "levels": {{"gf_slab":""}},
  "warnings": []
}}"""""


def _super_read_prompt(col_context, slab_context, level_context):
    """Build read-only prompt for superstructure."""
    return f"""You are reading structural engineering drawings for a UAE villa.
Your ONLY job: READ and REPORT what you see. Do NOT calculate any quantities.

IMAGES (in order):
1. GF Column Layout + Column Schedule
2. FF Column Layout
3. First Floor Slab Layout + Beam Schedule
4. Roof Slab Layout + Beam Schedule
5. Elevation/Section — floor levels and parapet height

PARSED DATA (100% accurate from PDF text layer — use to verify):
{col_context}
{slab_context}
{level_context}

YOUR TASK — READ ONLY:

A) COLUMNS per Floor:
   - GF: Count each column mark (C1, C2, etc.) across the ENTIRE GF plan
   - FF: Count each column mark across the ENTIRE FF plan
   - Report: mark, count, b×d dimensions (verify against parsed schedule)

B) SLABS:
   - FF Slab: Net area in m² (from grid dimensions L × W on the slab plan)
   - Roof Slab: Net area in m² (from grid dimensions)
   - Slab thickness (if readable, else use parsed value)

C) BEAMS per Floor:
   - FF Beams: For each beam type, read total length. Sum ALL types for total.
   - Roof Beams: Same as FF beams.
   - Report beam cross-section b × d if visible in schedule.
   - IMPORTANT: total beam length is the SUM of individual beam spans, NOT count × span.
     A typical villa has 50-200m total beam length per floor, NEVER more than 400m.

D) FLOOR HEIGHTS (from Elevation/Section):
   - GF floor height = distance from GF FFL to underside of FF slab (m)
   - FF floor height = distance from FF FFL to underside of Roof slab (m)
   - Parapet height = top of Roof slab to top of parapet (m)

E) PARAPET:
   - Roof perimeter in metres (from roof slab plan edge dimensions)

CRITICAL: Do NOT calculate concrete volumes, block areas, or ANY QTO item.
Just report the RAW measurements.

Return ONLY valid JSON:
{{
  "floorHeights": {{
    "gf_floor_height_m": 0,
    "ff_floor_height_m": 0,
    "parapet_height_m": 0,
    "source": "read from elevation/section"
  }},
  "observedElements": [
    {{"type":"column","mark":"C1","floor":"GF","count":0,"dims":{{"b_cm":0,"d_cm":0}},"notes":""}},
    {{"type":"column","mark":"C1","floor":"FF","count":0,"dims":{{"b_cm":0,"d_cm":0}},"notes":""}},
    {{"type":"slab","floor":"FF","area_m2":0,"thickness_m":0,"notes":""}},
    {{"type":"slab","floor":"Roof","area_m2":0,"thickness_m":0,"notes":""}},
    {{"type":"beam","floor":"FF","totalLength_m":0,"beamSchedule":[{{"mark":"","b_m":0,"d_m":0,"totalLength_m":0}}],"notes":""}},
    {{"type":"beam","floor":"Roof","totalLength_m":0,"beamSchedule":[{{"mark":"","b_m":0,"d_m":0,"totalLength_m":0}}],"notes":""}},
    {{"type":"parapet","RF_perimeter_m":0,"notes":""}}
  ],
  "warnings": []
}}"""


# ═══════════════════════════════════════════════════════════════
# IMPROVED ARCH: Focused per-page prompts + structural anchors
# ═══════════════════════════════════════════════════════════════

def _dw_schedule_prompt():
    """Focused prompt for D&W schedule reading ONLY (1 image)."""
    return """You are reading a Doors & Windows Schedule table from a UAE villa architectural drawing.

Read EVERY entry in the schedule. For each entry report:
- id: Type identifier (D1, D2, D3, W1, W2, SD1, etc.)
- cat: "door" or "win"
- w: Width in metres (convert from cm if needed: 90cm = 0.90m)
- h: Height in metres (convert from cm if needed: 210cm = 2.10m)
- n: Count/quantity (0 if not shown in schedule — we'll count from plans)
- a: Unit area = w × h (m²)

RULES:
- Include EVERY type — do NOT skip any row
- Typical villa: 5-15 door types, 3-8 window types
- Door widths: 0.70-2.00m, heights: 2.10-2.40m
- Window widths: 0.40-3.00m, heights: 0.40-2.40m
- Sliding doors, folding doors, garage doors → cat="door"
- If schedule shows BOTH a detail drawing AND a table, read from the TABLE

Return ONLY valid JSON:
{
  "dw": [
    {"id":"D1","cat":"door","w":1.00,"h":2.10,"n":1,"a":2.10},
    {"id":"W1","cat":"win","w":1.50,"h":1.50,"n":4,"a":2.25}
  ]
}"""


def _arch_floor_prompt(floor, floor_h, total_area, ext_perim, dw_summary):
    """Focused prompt for reading ONE floor plan (1 image + structural anchors)."""
    floor_full = "Ground Floor" if floor == "GF" else "First Floor"

    area_anchor = (
        f"\n  KNOWN total floor area = {total_area} m² (from structural grid — use as cross-check)"
        if total_area else ""
    )
    perim_anchor = (
        f"\n  KNOWN external perimeter ≈ {ext_perim} m (from structural grid 2×(L+W) — verify against plan)"
        if ext_perim else ""
    )

    return f"""You are reading the {floor_full} Architectural Floor Plan of a UAE villa.
You have ONE image showing the {floor_full} layout with room names, dimensions, and wall lines.

STRUCTURAL ANCHORS (verified from engineering drawings):{area_anchor}{perim_anchor}
  Floor height = {floor_h} m

D&W SCHEDULE (already read):
{dw_summary}

═══════════════════════════════════════════════════════
TASK: Measure and report these items FROM THIS FLOOR PLAN:
═══════════════════════════════════════════════════════

1. EXTERNAL WALL PERIMETER (m):
   - Trace the OUTER wall centerline around the entire building footprint
   - Sum ALL external wall segment lengths
   - Include any setbacks, extensions, or projections

2. WET ROOMS — list EVERY wet room on this floor:
   Kitchen, ALL Bathrooms, Toilets/WC, Laundry, Pantry, Maid's room bathroom
   For EACH wet room:
   - Name (as labeled on plan)
   - L (length in metres — from dimension lines)
   - W (width in metres — from dimension lines)
   - area = L × W
   - perim = 2 × (L + W)
   Then sum: total wet area, total wet perimeter

3. DRY ROOMS — list EVERY dry room:
   Living, Majlis, Dining, ALL Bedrooms, Master Bedroom, Corridors, Stairs, Store, Entrance
   For EACH dry room:
   - Name, L, W, area, perim
   {"Then dry_total_area should ≈ " + str(round(total_area, 1)) + " - wet_total_area" if total_area else "Sum all dry areas"}

4. INTERIOR WALLS:
   - 20cm block walls: total LENGTH (m) — structural walls + wet area boundaries
     (thick walls, usually drawn with double lines or hatched)
   - 10cm block walls: total LENGTH (m) — thin partition walls between rooms
     (single line or thinner than 20cm walls)
   - Measure each wall SEGMENT length, then sum per type

5. OPENINGS on THIS floor:
   Count each D&W type visible on THIS floor plan:
   - Windows: list each type + count on this floor → sum total window area (m²)
   - External doors: doors in external walls → total area (m²)
   - Internal doors: doors between rooms → total area (m²)
   - Door width sum: add up the WIDTH of every door on this floor (m)

6. BALCONY:
   - Total balcony area (m²) — outdoor covered areas attached to building
   - 0 if no balconies on this floor

CRITICAL VALIDATION:
  wet_total_area + dry_total_area MUST ≈ total floor area {"(" + str(round(total_area, 1)) + " m²)" if total_area else ""}
  If they don't add up, recheck your room measurements.

Return ONLY valid JSON:
{{
  "floor": "{floor}",
  "ext_perim": 0,
  "wet_rooms": [
    {{"name":"Kitchen","L":0,"W":0,"area":0,"perim":0}},
    {{"name":"Bath1","L":0,"W":0,"area":0,"perim":0}}
  ],
  "wet_total_area": 0,
  "wet_total_perim": 0,
  "dry_rooms": [
    {{"name":"Living","L":0,"W":0,"area":0,"perim":0}},
    {{"name":"Bedroom1","L":0,"W":0,"area":0,"perim":0}}
  ],
  "dry_total_area": 0,
  "dry_total_perim": 0,
  "walls_20cm_len": 0,
  "walls_10cm_len": 0,
  "win_area": 0,
  "win_details": [{{"type":"W1","count_this_floor":0,"unit_area":0}}],
  "door_area_ext": 0,
  "door_area_int": 0,
  "door_width_sum": 0,
  "balcony_area": 0,
  "total_area_check": 0,
  "notes": ""
}}"""


def _consensus_floor(results):
    """Median consensus across multiple passes for a single floor."""
    if not results:
        return {}
    if len(results) == 1:
        return results[0]

    consensus = {"floor": results[0].get("floor", "")}
    numeric_keys = [
        "ext_perim", "wet_total_area", "wet_total_perim",
        "dry_total_area", "dry_total_perim",
        "walls_20cm_len", "walls_10cm_len",
        "win_area", "door_area_ext", "door_area_int",
        "door_width_sum", "balcony_area",
    ]
    for key in numeric_keys:
        vals = [float(r.get(key, 0) or 0)
                for r in results
                if isinstance(r.get(key, 0), (int, float))]
        consensus[key] = round(_median(vals), 2) if vals else 0

    # Wet rooms: keep longest list (most rooms found)
    wr_lists = [r.get("wet_rooms", []) for r in results if r.get("wet_rooms")]
    if wr_lists:
        consensus["wet_rooms"] = max(
            wr_lists,
            key=lambda lst: sum(rm.get("area", 0) for rm in lst)
        )
    else:
        consensus["wet_rooms"] = []

    # Dry rooms: same approach
    dr_lists = [r.get("dry_rooms", []) for r in results if r.get("dry_rooms")]
    if dr_lists:
        consensus["dry_rooms"] = max(
            dr_lists,
            key=lambda lst: sum(rm.get("area", 0) for rm in lst)
        )
    else:
        consensus["dry_rooms"] = []

    return consensus


def _arch_read_prompt(gf_h, ff_h, ext_h, combo, roof_area, parapet_h):
    """Build read-only prompt for architectural (legacy — kept for backward compat)."""
    return f"""You are reading architectural drawings for a UAE villa.
Your ONLY job: READ and REPORT measurements. Do NOT calculate QTO items.

IMAGES (in order):
1. Ground Floor Plan
2. First Floor Plan
3. Elevations Front+Right
4. Elevations Rear+Left
5. Windows & Doors Schedule

FIXED VALUES (do NOT re-read):
  GF floor height = {gf_h} m
  FF floor height = {ff_h} m
  Parapet height  = {parapet_h} m
  ExtH = {ext_h} m
  Roof area = {roof_area} m²

YOUR TASK — READ ONLY:

For EACH floor (GF and FF), measure and report:

A) EXTERNAL WALLS:
   - Total external perimeter (m) — measure from plan outer wall centerlines

B) WET AREAS (kitchens + ALL bathrooms + toilets + laundry + pantry):
   - List each wet room by name
   - Measure each room: L × W → area
   - Sum total wet area (m²)
   - Sum total wet perimeter (m) — sum of each room's perimeter

C) DRY AREAS:
   - Total floor area (m²) — overall villa footprint for that floor
   - Dry area = total - wet area (m²)
   - Dry perimeter (m) — perimeter of all dry rooms (sum room perimeters)

D) INTERIOR WALLS:
   - 20cm block walls: total length (m) — sum all 20cm wall segments
   - 10cm block walls: total length (m) — sum all 10cm wall segments (partitions)

E) OPENINGS:
   - Windows: total area (m²) — from schedule or count from plan
   - Doors: total width sum (m), total area (m²)
   - Separate external doors area vs internal doors area

F) BALCONIES:
   - Total balcony area per floor (m²)

G) DOORS & WINDOWS SCHEDULE (from schedule image):
   - Each type: ID (D1,D2,W1,W2...), category (door/win), width, height, count, unit area
   - COUNT every single door and window — do not skip any type

CRITICAL: Do NOT calculate block_20, plaster, skirting, paint, or ANY QTO item.
Just report the RAW measurements.

Return ONLY valid JSON:
{{
  "observed": [
    {{"t":"ext_walls","f":"GF","perim":0}},
    {{"t":"wet","f":"GF","area":0,"perim":0,"rooms":"Kitchen(LxW=...),Bath1(LxW=...),..."}},
    {{"t":"dry","f":"GF","total":0,"dry":0,"perim":0}},
    {{"t":"balcony","f":"GF","area":0}},
    {{"t":"walls20","f":"GF","len":0}},
    {{"t":"walls10","f":"GF","len":0}},
    {{"t":"openings","f":"GF","win_area":0,"door_w":0,"door_area":0,"door_area_ext":0,"door_area_int":0}},
    {{"t":"ext_walls","f":"FF","perim":0}},
    {{"t":"wet","f":"FF","area":0,"perim":0,"rooms":"MasterBath(LxW=...),Bath2(LxW=...),..."}},
    {{"t":"dry","f":"FF","total":0,"dry":0,"perim":0}},
    {{"t":"balcony","f":"FF","area":0}},
    {{"t":"walls20","f":"FF","len":0}},
    {{"t":"walls10","f":"FF","len":0}},
    {{"t":"openings","f":"FF","win_area":0,"door_w":0,"door_area":0,"door_area_ext":0,"door_area_int":0}}
  ],
  "dw": [
    {{"id":"D1","cat":"door","w":0,"h":0,"n":0,"a":0}},
    {{"id":"W1","cat":"win","w":0,"h":0,"n":0,"a":0}}
  ],
  "warnings": []
}}"""


# ═══════════════════════════════════════════════════════════════
# PUBLIC API: Multi-pass read with consensus + guard retry
# ═══════════════════════════════════════════════════════════════

def read_sub(image_parts, parsed_context, excav_depth, gf_level, cfg,
             passes=3, name="project", parsed_footings=None):
    """
    Multi-pass vision read for substructure.
    Step 1: 3 general passes → consensus.
    Step 2: For any footing/TB with high variance → targeted single-type prompt.
    parsed_footings: list of dicts from parse_footing_schedule for size-matching.
    """
    prompt = _sub_read_prompt(parsed_context, excav_depth, gf_level, cfg)
    results = []
    for i in range(passes):
        print(f"  🔍 Sub vision pass {i+1}/{passes}...")
        r = _call_gemini(prompt, image_parts, f"{name}_sub_pass{i+1}")
        if r:
            results.append(r)
        if i < passes - 1:
            time.sleep(2)

    if not results:
        print("  ✗ All sub vision passes failed!")
        return [], {}, []

    if len(results) == 1:
        r = results[0]
        return r.get("observedElements",[]), r.get("gridDims",{}), r.get("warnings",[])

    consensus_obs = _consensus_sub(results, parsed_footings=parsed_footings)

    # ── Step 2: Targeted re-read for high-variance items ────────────
    import ast

    # Collect dims for all footing marks (for context in targeted prompts)
    all_ftg_dims = {}   # mark → dims dict
    for el in consensus_obs:
        if el.get("type") == "Footing":
            all_ftg_dims[el["mark"]] = el.get("dims", {})

    # Collect dims for all TB marks
    all_tb_marks = [el["mark"] for el in consensus_obs if "Beam" in el.get("type","")]

    targeted_updates = {}  # mark → new_count or new_length

    for el in consensus_obs:
        notes = el.get("notes", "")
        if "passes:" not in notes:
            continue
        try:
            vals_str = notes.split("passes: ")[1].split(" →")[0]
            vals = ast.literal_eval(vals_str)
        except:
            continue

        if not _high_variance(vals):
            continue

        mark = el.get("mark", "")
        etype = el.get("type", "")

        if etype == "Footing":
            print(f"  🎯 Targeted count for {mark} (variance in {vals})...")
            # foundation layout is the FIRST image in image_parts
            ft_prompt = _build_targeted_count_prompt(mark, el.get("dims",{}), all_ftg_dims)
            # Use only foundation layout image (first 2 parts: text label + image)
            foundation_parts = image_parts[:2]
            r = _call_gemini(ft_prompt, foundation_parts, f"{name}_targeted_{mark}")
            if r and "count" in r:
                new_count = int(round(float(r["count"])))
                conf = r.get("confidence","?")
                locs = r.get("locations","")
                print(f"    → {mark}: targeted={new_count} (conf={conf}) loc={locs[:60]}")
                targeted_updates[mark] = ("count", new_count)
            time.sleep(1)

        elif "Beam" in etype:
            dims = el.get("dims", {})
            b = dims.get("b", 0.20)
            d_val = dims.get("d", 0.50)
            print(f"  🎯 Targeted length for {mark} (variance in {vals})...")
            # TB layout is the LAST structural image (last 2 parts)
            tb_parts = image_parts[-2:]
            tb_prompt = _build_targeted_tb_prompt(mark, b, d_val, all_tb_marks)
            r = _call_gemini(tb_prompt, tb_parts, f"{name}_targeted_{mark}")
            if r and "totalLength_m" in r:
                new_len = float(r["totalLength_m"])
                conf = r.get("confidence","?")
                segs = r.get("segments","")
                print(f"    → {mark}: targeted={new_len}m (conf={conf}) segs={segs[:60]}")
                targeted_updates[mark] = ("length", new_len)
            time.sleep(1)

    # Apply targeted updates to consensus
    if targeted_updates:
        for el in consensus_obs:
            mark = el.get("mark","")
            if mark in targeted_updates:
                kind, val = targeted_updates[mark]
                old_notes = el.get("notes","")
                if kind == "count":
                    old = el.get("count", 0)
                    el["count"] = val
                    el["notes"] = old_notes + f" | targeted={val} (was {old})"
                elif kind == "length":
                    old = el.get("dims",{}).get("L", 0)
                    el.setdefault("dims",{})["L"] = val
                    el["notes"] = old_notes + f" | targeted={val}m (was {old}m)"
        print(f"  ✓ Applied {len(targeted_updates)} targeted corrections")

    # Grid dims: take from first successful result
    grid = results[0].get("gridDims", {})
    warns = []
    for r in results:
        warns.extend(r.get("warnings",[]))
    warns = list(dict.fromkeys(warns))

    print(f"  ✓ Sub consensus from {len(results)} passes: {len(consensus_obs)} observed elements")
    return consensus_obs, grid, warns


def read_super(image_parts, col_context, slab_context, level_context,
               passes=3, name="project"):
    """
    Multi-pass vision read for superstructure.
    Returns (consensus_floor_heights, consensus_observed, warnings).
    """
    prompt = _super_read_prompt(col_context, slab_context, level_context)
    results = []
    for i in range(passes):
        print(f"  🔍 Super vision pass {i+1}/{passes}...")
        r = _call_gemini(prompt, image_parts, f"{name}_super_pass{i+1}")
        if r:
            results.append(r)
        if i < passes - 1:
            time.sleep(1)

    if not results:
        print("  ✗ All super vision passes failed!")
        return {}, [], []

    if len(results) == 1:
        r = results[0]
        return r.get("floorHeights",{}), r.get("observedElements",[]), r.get("warnings",[])

    fh, obs = _consensus_super(results)
    warns = []
    for r in results:
        warns.extend(r.get("warnings",[]))

    print(f"  ✓ Super consensus from {len(results)} passes: {len(obs)} observed elements")
    return fh, obs, warns


def read_arch(image_parts, gf_h, ff_h, ext_h, combo, roof_area, parapet_h,
              passes=3, name="project",
              grid_L=None, grid_W=None, parsed_dw=None):
    """
    Improved arch reading with focused per-page calls + structural anchors.

    Strategy:
      1. D&W Schedule — 1 focused call (1 image)
      2. GF Floor Plan — 2-3 focused calls (1 image + anchors)
      3. FF Floor Plan — 2-3 focused calls (1 image + anchors)
      4. Cross-validate all readings against grid dims
      5. Auto-correct wet+dry=total

    image_parts order:
      [0] GF Floor Plan
      [1] FF Floor Plan
      [2] Elevations Front+Right
      [3] Elevations Rear+Left
      [4] Windows & Doors Schedule

    New params (optional, for cross-validation):
      grid_L, grid_W : structural grid dims in metres (from sub result)
      parsed_dw : pre-parsed D&W from text layer (skips vision D&W call)
    """
    use_pro = True   # Pro model for arch = much better spatial reasoning
    total_area = round(grid_L * grid_W, 2) if grid_L and grid_W else None
    ext_perim = round(2 * (grid_L + grid_W), 2) if grid_L and grid_W else None

    if total_area:
        print(f"  📐 Structural anchors: area={total_area}m² perim={ext_perim}m (grid {grid_L}×{grid_W})")

    # ── Step 1: D&W Schedule ─────────────────────────────────────
    if parsed_dw:
        dw = parsed_dw
        print(f"  ✓ D&W from text: {len(dw)} entries")
    else:
        print("  🔍 Reading D&W schedule...")
        # Send D&W page + elevations (D&W details often span multiple pages)
        dw_imgs = []
        if len(image_parts) > 4:
            dw_imgs = [image_parts[4]]  # D&W schedule page
        if len(image_parts) > 3:
            dw_imgs.extend([image_parts[2], image_parts[3]])  # elevations show window/door sizes
        if not dw_imgs:
            dw_imgs = image_parts[-1:]

        # Try flash first (faster, good at table reading)
        r = _call_gemini(_dw_schedule_prompt(), dw_imgs, f"{name}_dw", use_pro=False)
        dw = r.get("dw", []) if r else []
        if not dw:
            # Retry with pro model
            print("  → D&W retry with pro model...")
            time.sleep(3)
            r = _call_gemini(_dw_schedule_prompt(), dw_imgs, f"{name}_dw_pro", use_pro=True)
            dw = r.get("dw", []) if r else []
        if not dw:
            # Final: send ALL images
            print("  → D&W final retry (all images, flash)...")
            time.sleep(3)
            r = _call_gemini(_dw_schedule_prompt(), image_parts, f"{name}_dw_all", use_pro=False)
            dw = r.get("dw", []) if r else []
        print(f"  → D&W: {len(dw)} entries")
        for e in dw:
            print(f"     {e.get('id','?')}: {e.get('cat','?')} {e.get('w',0)}×{e.get('h',0)}m n={e.get('n',0)}")

    # Build D&W summary for floor prompts
    dw_lines = []
    for e in dw:
        dw_lines.append(
            f"  {e.get('id','?')}: {e.get('cat','?')} "
            f"{e.get('w',0)}×{e.get('h',0)}m = {e.get('a', round(e.get('w',0)*e.get('h',0), 2))}m²"
        )
    dw_summary = "\n".join(dw_lines) if dw_lines else "  (No D&W schedule available)"

    # ── Step 2: Per-Floor Reading ────────────────────────────────
    observed = []
    warnings = []

    for floor, floor_h, img_idx in [("GF", gf_h, 0), ("FF", ff_h, 1)]:
        print(f"\n  🔍 Reading {floor} plan (pro model, focused)...")

        if img_idx >= len(image_parts):
            print(f"  ✗ No image for {floor}!")
            warnings.append(f"{floor} image missing")
            continue

        floor_imgs = [image_parts[img_idx]]
        prompt = _arch_floor_prompt(floor, floor_h, total_area, ext_perim, dw_summary)

        results = []
        n_passes = max(2, passes - 1)   # 2-3 passes per floor
        for i in range(n_passes):
            print(f"    pass {i+1}/{n_passes}...")
            r = _call_gemini(prompt, floor_imgs, f"{name}_{floor}_p{i+1}", use_pro=use_pro)
            if r:
                results.append(r)
                # Print key values for monitoring
                wet = r.get("wet_total_area", 0)
                dry = r.get("dry_total_area", 0)
                ext = r.get("ext_perim", 0)
                print(f"      → wet={wet} dry={dry} ext_p={ext} total_check={round(wet+dry, 1)}")
            if i < n_passes - 1:
                time.sleep(3)

        if not results:
            print(f"  ✗ {floor}: all passes failed!")
            warnings.append(f"{floor} all vision passes failed")
            continue

        consensus = _consensus_floor(results)

        # ── Validate: wet + dry ≈ usable floor area ──
        # Grid area = gross footprint. Net usable ≈ grid × 0.82 (walls ~18%)
        wet_a = consensus.get("wet_total_area", 0)
        dry_a = consensus.get("dry_total_area", 0)
        check_sum = round(wet_a + dry_a, 2)
        net_area = round(total_area * 0.82, 2) if total_area else None

        if net_area and check_sum > 0:
            ratio = check_sum / net_area
            if ratio < 0.60 or ratio > 1.40:
                warnings.append(
                    f"{floor}: wet({wet_a})+dry({dry_a})={check_sum} "
                    f"vs net {net_area} (grid {total_area}×0.82, ratio {ratio:.2f})"
                )
                # Only auto-correct if vision total is WAY off (< 50% of net)
                # Use net_area (not gross grid) for correction
                if check_sum < net_area * 0.50:
                    old_dry = dry_a
                    consensus["dry_total_area"] = round(net_area - wet_a, 2)
                    print(f"    ⚠ {floor} dry auto-corrected: {old_dry} → {consensus['dry_total_area']} (net={net_area})")
                    if dry_a > 0 and consensus.get("dry_total_perim", 0):
                        scale_f = consensus["dry_total_area"] / dry_a
                        consensus["dry_total_perim"] = round(
                            consensus["dry_total_perim"] * (scale_f ** 0.5), 2
                        )
                else:
                    print(f"    ⚠ {floor} area ratio off ({ratio:.2f}) but not auto-correcting — vision total within 50%")
            else:
                print(f"    ✓ {floor} area check: {check_sum} ≈ net {net_area} (ratio {ratio:.2f})")

        # ── Validate: external perimeter ──
        ext_p = consensus.get("ext_perim", 0)
        if ext_perim and ext_p > 0:
            p_ratio = ext_p / ext_perim
            if p_ratio < 0.70 or p_ratio > 1.50:
                warnings.append(
                    f"{floor}: ext_perim={ext_p} vs grid 2×(L+W)={ext_perim} "
                    f"(ratio {p_ratio:.2f})"
                )
                # Don't auto-correct perimeter — can legitimately differ with setbacks

        # ── Convert to standard observed format ──
        rooms_str = ", ".join(
            f"{wr.get('name','')}({wr.get('L',0)}×{wr.get('W',0)}={wr.get('area',0)})"
            for wr in consensus.get("wet_rooms", [])
        )

        observed.extend([
            {"t": "ext_walls", "f": floor, "perim": consensus.get("ext_perim", 0)},
            {"t": "wet", "f": floor,
             "area": consensus.get("wet_total_area", 0),
             "perim": consensus.get("wet_total_perim", 0),
             "rooms": rooms_str},
            {"t": "dry", "f": floor,
             "total": round(
                 consensus.get("wet_total_area", 0) + consensus.get("dry_total_area", 0), 2
             ),
             "dry": consensus.get("dry_total_area", 0),
             "perim": consensus.get("dry_total_perim", 0)},
            {"t": "balcony", "f": floor, "area": consensus.get("balcony_area", 0)},
            {"t": "walls20", "f": floor, "len": consensus.get("walls_20cm_len", 0)},
            {"t": "walls10", "f": floor, "len": consensus.get("walls_10cm_len", 0)},
            {"t": "openings", "f": floor,
             "win_area": consensus.get("win_area", 0),
             "door_w": consensus.get("door_width_sum", 0),
             "door_area": round(
                 consensus.get("door_area_ext", 0) + consensus.get("door_area_int", 0), 2
             ),
             "door_area_ext": consensus.get("door_area_ext", 0),
             "door_area_int": consensus.get("door_area_int", 0)},
        ])

        print(f"  ✓ {floor}: wet={consensus.get('wet_total_area',0)} "
              f"dry={consensus.get('dry_total_area',0)} ext_p={consensus.get('ext_perim',0)}")

    if warnings:
        print(f"\n  ── Arch Warnings ({len(warnings)}) ──")
        for w in warnings:
            print(f"    ⚠ {w}")

    print(f"\n  ✓ Arch complete: {len(observed)} observed, {len(dw)} D&W entries")
    return observed, dw, warnings


# ═══════════════════════════════════════════════════════════════
# GUARD-TRIGGERED RE-READ
# ═══════════════════════════════════════════════════════════════

def retry_sub_value(image_parts, mark, value_type, current_value, name="project"):
    """
    Focused re-read for a single suspicious sub value.
    value_type: "footing_count" or "tb_length"
    """
    if value_type == "footing_count":
        prompt = f"""Look at the Foundation Layout plan.
COUNT how many footings of type '{mark}' exist.
Scan the ENTIRE plan systematically.
Current reading was {current_value} — verify this is correct.
Return JSON: {{"mark":"{mark}","count":0,"notes":"verification"}}"""
    elif value_type == "tb_length":
        prompt = f"""Look at the Tie Beam Layout plan.
What is the TOTAL RUN LENGTH (sum of all segments) of tie beam type '{mark}' in metres?
Current reading was {current_value}m — verify this is correct.
Return JSON: {{"mark":"{mark}","totalLength_m":0,"notes":"verification"}}"""
    else:
        return current_value

    r = _call_gemini(prompt, image_parts, f"{name}_retry_{mark}")
    if r:
        if value_type == "footing_count":
            return r.get("count", current_value)
        elif value_type == "tb_length":
            return r.get("totalLength_m", current_value)
    return current_value


def retry_super_value(image_parts, field, current_value, name="project"):
    """
    Focused re-read for a single suspicious super value.
    field: "beam_length_FF", "beam_length_Roof", "slab_area_FF", etc.
    """
    if "beam_length" in field:
        floor = field.split("_")[-1]
        prompt = f"""Look at the {floor} Slab Layout / Beam Schedule.
What is the TOTAL beam length for {floor} in metres?
Sum ALL individual beam spans. A typical villa has 50-200m per floor, NEVER over 400m.
Current reading was {current_value}m — verify this.
Return JSON: {{"floor":"{floor}","totalLength_m":0,"notes":"verification"}}"""
    elif "slab_area" in field:
        floor = field.split("_")[-1]
        prompt = f"""Look at the {floor} Slab Layout.
What is the net slab area for {floor} in m²?
Read from grid dimensions (L × W). A typical villa is 100-600 m².
Current reading was {current_value} m² — verify this.
Return JSON: {{"floor":"{floor}","area_m2":0,"notes":"verification"}}"""
    else:
        return current_value

    r = _call_gemini(prompt, image_parts, f"{name}_retry_{field}")
    if r:
        return r.get("totalLength_m") or r.get("area_m2") or current_value
    return current_value
