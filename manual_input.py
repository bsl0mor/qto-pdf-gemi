"""
manual_input.py — No-AI measurement input module for QTO pipeline.
════════════════════════════════════════════════════════════════════
Replaces vision_reader.py completely.  Exposes the same three
public functions (read_sub, read_super, read_arch) with identical
return types so that test2.py / super.py / arch.py need only a
one-line import change.

What changes:
  • Text-parser results (footing dims, TB dims, column dims, grid
    dims, floor levels, slab thickness, D&W schedule) are pre-filled
    automatically — no user action needed for these.
  • The user is asked ONLY for the spatial measurements that cannot
    be extracted from the PDF text layer:
      Sub   : footing counts per type + TB total lengths per type
      Super : column counts per floor, slab areas, beam lengths,
              floor heights (if text parse missed them), RF perim,
              avg beam b and d_net
      Arch  : ext perimeter, wet/dry areas, wall lengths, openings,
              balcony per floor; D&W schedule if text parse failed

Accuracy target: 97–99 % (all errors from wrong user measurements,
zero errors from AI hallucination).
"""

import re as _re
import json as _json
import math as _math


# ══════════════════════════════════════════════════════════════════
# I/O HELPERS
# ══════════════════════════════════════════════════════════════════

def _section(title):
    print(f"\n{'─'*65}")
    print(f"  {title}")
    print(f"{'─'*65}")


def _ask_float(prompt, default=None, lo=None, hi=None):
    """Prompt for a float with optional default and range validation."""
    hint = ""
    if default is not None:
        hint += f"  [default: {default}]"
    if lo is not None and hi is not None:
        hint += f"  (typical: {lo}–{hi})"
    full_prompt = f"  {prompt}{hint}: "
    while True:
        raw = input(full_prompt).strip()
        if raw == "" and default is not None:
            return float(default)
        try:
            v = float(raw)
        except ValueError:
            print("    ✗ Enter a number (e.g. 12.50)")
            continue
        if lo is not None and v < lo:
            print(f"    ✗ Value {v} < minimum {lo}")
            continue
        if hi is not None and v > hi:
            print(f"    ✗ Value {v} > maximum {hi}")
            continue
        return v


def _ask_int(prompt, default=None, lo=0, hi=999):
    """Prompt for an integer with optional default and range validation."""
    hint = ""
    if default is not None:
        hint += f"  [default: {default}]"
    full_prompt = f"  {prompt}{hint}: "
    while True:
        raw = input(full_prompt).strip()
        if raw == "" and default is not None:
            return int(default)
        try:
            v = int(raw)
        except ValueError:
            print("    ✗ Enter a whole number")
            continue
        if v < lo or v > hi:
            print(f"    ✗ Must be {lo}–{hi}")
            continue
        return v


def _ask_yn(prompt, default=True):
    """Prompt for yes/no."""
    hint = "[Y/n]" if default else "[y/N]"
    raw = input(f"  {prompt} {hint}: ").strip().lower()
    if raw == "":
        return default
    return raw in ("y", "yes")


# ══════════════════════════════════════════════════════════════════
# CONTEXT PARSERS — extract structured data from formatted strings
# ══════════════════════════════════════════════════════════════════

def _parse_tb_from_context(parsed_context):
    """
    Extract TB schedule from the formatted parsed_context string.
    Returns list of {mark, b_m, d_m}.
    """
    tbs = []
    in_sched = False
    for line in parsed_context.split('\n'):
        if _re.search(r'SCHEDULE OF TIE BEAMS', line, _re.I):
            in_sched = True
            continue
        if not in_sched:
            continue
        # Stop at next schedule header
        if _re.search(r'SCHEDULE OF (FOOTINGS|COLUMNS)|OVERALL DIMS|GF LEVEL', line, _re.I):
            break
        # Match "  TB1    0.25    0.60" or "  CTB1   0.25    0.60"
        m = _re.match(r'\s+((?:C)?TB\d+|WF\d+)\s+([\d.]+)\s+([\d.]+)', line, _re.I)
        if m:
            tbs.append({
                'mark': m.group(1).upper(),
                'b_m':  float(m.group(2)),
                'd_m':  float(m.group(3)),
            })
    return tbs


def _parse_col_from_context(context_str):
    """
    Extract column schedule from col_context string.
    Returns list of {mark, b_cm, d_cm}.
    """
    cols = []
    in_sched = False
    for line in context_str.split('\n'):
        if _re.search(r'SCHEDULE OF COLUMNS', line, _re.I):
            in_sched = True
            continue
        if not in_sched:
            continue
        if _re.search(r'NOTE:', line, _re.I) or line.strip().startswith('─'):
            continue
        # Match "  C1       0.20    0.50    rect"
        m = _re.match(r'\s+((?:C|NC)\d+(?:/DC)?)\s+([\d.]+)\s+([\d.]+)', line, _re.I)
        if m:
            mark = m.group(1).upper()
            b_cm = round(float(m.group(2)) * 100)
            d_cm = round(float(m.group(3)) * 100)
            cols.append({'mark': mark, 'b_cm': b_cm, 'd_cm': d_cm})
    return cols


def _parse_levels_from_context(level_context):
    """
    Try to extract floor heights from the level_context string.
    Returns dict with optional keys: gf_ffl, ff_ffl, roof_ffl, parapet_top.
    """
    levels = {}
    for line in level_context.split('\n'):
        for pat, key in [
            (r'gf_ffl\s*=\s*\+?([\d.]+)', 'gf_ffl'),
            (r'ff_ffl\s*=\s*\+?([\d.]+)', 'ff_ffl'),
            (r'roof_slab_top\s*=\s*\+?([\d.]+)', 'roof_ffl'),
            (r'parapet_top\s*=\s*\+?([\d.]+)', 'parapet_top'),
        ]:
            m = _re.search(pat, line, _re.I)
            if m:
                levels[key] = float(m.group(1))
    # Fallback: scan for all +N.NN values and auto-assign
    if 'gf_ffl' not in levels:
        alls = levels.get('_all_plus_levels', [])
        if not alls:
            raw = _re.findall(r'\+\s*([\d]+\.[\d]+)', level_context)
            alls = sorted(set(round(float(x), 3) for x in raw))
        if len(alls) >= 2:
            levels.setdefault('gf_ffl', alls[0])
            levels.setdefault('ff_ffl', alls[1])
        if len(alls) >= 3:
            levels.setdefault('roof_ffl', alls[2])
        if len(alls) >= 4:
            levels.setdefault('parapet_top', alls[3])
    return levels


# ══════════════════════════════════════════════════════════════════
# PUBLIC API — SUBSTRUCTURE
# ══════════════════════════════════════════════════════════════════

def read_sub(image_parts, parsed_context, excav_depth, gf_level, cfg,
             passes=3, name="project", parsed_footings=None):
    """
    Manual-input replacement for Gemini sub-structure reading.

    Pre-fills from parsed_footings (dims) and parsed_context (TB dims).
    Asks the user ONLY for:
      • Footing count per type  (read from Foundation Layout plan)
      • TB total run length per type  (read from Tie Beam Layout plan)
      • Grid dims L, W  (if text parse returned None)

    Returns
    -------
    observed_elements : list[dict]  — same format as vision_reader.read_sub
    grid_dims : dict                — {L_m, W_m}
    warnings  : list[str]
    """
    print("\n" + "="*65)
    print(f"  MANUAL INPUT — SUBSTRUCTURE  [{name}]")
    print("="*65)
    print("  Open the Foundation Layout and Tie Beam Layout drawings.")
    print("  Enter the values you read directly from the drawings.\n")

    observed_elements = []
    warnings = []

    # ── FOOTINGS ──────────────────────────────────────────────────
    _section("FOOTINGS — Count each type on the Foundation Layout plan")

    if parsed_footings:
        print("  Footing schedule from PDF text (dims are 100% accurate):\n")
        print(f"  {'TYPE':<8} {'L(m)':<7} {'W(m)':<7} {'H(m)':<7}")
        print("  " + "─" * 30)
        for f in parsed_footings:
            print(f"  {f['mark']:<8} {f['L_cm']/100:<7.2f} {f['W_cm']/100:<7.2f} {f['H_cm']/100:<7.2f}")
        print()
        print("  For each footing type, count how many appear on the Foundation")
        print("  Layout plan (not in the schedule — count the symbols on the plan):\n")

        for f in parsed_footings:
            mark = f['mark']
            L_m = round(f['L_cm'] / 100, 3)
            W_m = round(f['W_cm'] / 100, 3)
            H_m = round(f['H_cm'] / 100, 3)
            count = _ask_int(
                f"{mark} ({L_m}×{W_m}×{H_m}m) — count on plan",
                lo=0, hi=100
            )
            observed_elements.append({
                "type": "Footing",
                "mark": mark,
                "count": count,
                "dims": {"L": L_m, "W": W_m, "H": H_m, "unit": "m"},
                "notes": "manual input — count from plan",
            })
    else:
        # No text-parsed schedule — ask user to enter footing data manually
        warnings.append("Footing schedule not found in text — entered manually")
        _section("No footing schedule in text. Enter each footing type manually.")
        print("  How many footing types does this project have?")
        n_ftg = _ask_int("Number of footing types", default=3, lo=1, hi=20)
        for i in range(n_ftg):
            print(f"\n  Footing type {i+1}:")
            mark = input(f"    Mark (e.g. F{i+1}): ").strip().upper() or f"F{i+1}"
            L_m  = _ask_float("    Length L (m)", lo=0.5, hi=5.0)
            W_m  = _ask_float("    Width W (m)", lo=0.5, hi=5.0)
            H_m  = _ask_float("    Depth H (m)", default=0.40, lo=0.20, hi=0.90)
            count = _ask_int(f"    Count on plan", lo=0, hi=100)
            observed_elements.append({
                "type": "Footing",
                "mark": mark,
                "count": count,
                "dims": {"L": L_m, "W": W_m, "H": H_m, "unit": "m"},
                "notes": "manual input (no text schedule)",
            })

    total_ftg = sum(el['count'] for el in observed_elements if el.get('type') == 'Footing')
    print(f"\n  Total footings entered: {total_ftg}  (typical villa: 20–50)")
    if not 4 <= total_ftg <= 80:
        warnings.append(f"Footing count {total_ftg} outside typical range 4–80")

    # ── TIE BEAMS ─────────────────────────────────────────────────
    _section("TIE BEAMS — Total run length per type from Tie Beam Layout plan")
    print("  Add up all segment lengths per TB type to get the total run.")
    print("  Grid bay spacings written on the plan give individual lengths.\n")

    tb_from_context = _parse_tb_from_context(parsed_context)

    if tb_from_context:
        print("  TB schedule from PDF text (dims are 100% accurate):\n")
        print(f"  {'TYPE':<8} {'b(m)':<7} {'d(m)':<7}")
        print("  " + "─" * 24)
        for t in tb_from_context:
            print(f"  {t['mark']:<8} {t['b_m']:<7.2f} {t['d_m']:<7.2f}")
        print()
        print("  Now enter the TOTAL RUN LENGTH (m) of each type on the plan:\n")

        for t in tb_from_context:
            mark = t['mark']
            b_m  = t['b_m']
            d_m  = t['d_m']
            length = _ask_float(
                f"{mark} ({b_m}×{d_m}m) — total run length (m)",
                lo=0, hi=500
            )
            observed_elements.append({
                "type": "Tie Beam",
                "mark": mark,
                "dims": {"L": length, "b": b_m, "d": d_m, "unit": "m"},
                "notes": "manual input — length from plan",
            })
    else:
        # No text-parsed TB schedule — enter manually
        warnings.append("TB schedule not found in text — entered manually")
        print("  No TB schedule found in text. Enter each TB type manually.\n")
        n_tb = _ask_int("Number of TB types", default=2, lo=0, hi=10)
        for i in range(n_tb):
            print(f"\n  TB type {i+1}:")
            mark   = input(f"    Mark (e.g. TB{i+1}): ").strip().upper() or f"TB{i+1}"
            b_m    = _ask_float("    Width b (m)", default=0.25, lo=0.15, hi=0.50)
            d_m    = _ask_float("    Depth d (m)", default=0.60, lo=0.30, hi=0.80)
            length = _ask_float(f"    Total run length (m)", lo=0, hi=500)
            observed_elements.append({
                "type": "Tie Beam",
                "mark": mark,
                "dims": {"L": length, "b": b_m, "d": d_m, "unit": "m"},
                "notes": "manual input (no text schedule)",
            })

    total_tb = sum(
        el['dims'].get('L', 0)
        for el in observed_elements if el.get('type') == 'Tie Beam'
    )
    print(f"\n  Total TB run entered: {total_tb:.1f} m  (typical villa: 50–400 m)")
    if total_tb > 0 and not 20 <= total_tb <= 600:
        warnings.append(f"TB total length {total_tb}m outside typical range 20–600m")

    # ── GRID DIMS (if not from text parser) ───────────────────────
    # These values come from parse_grid_dims in test2.py.
    # If they were found, they override what we return here (see test2.py lines 864-869).
    # We still ask here as fallback in case text parse returned None.
    overall_L = cfg.get('_parsed_overall_L')
    overall_W = cfg.get('_parsed_overall_W')

    if not overall_L or not overall_W:
        _section("GRID DIMENSIONS — if not shown automatically above")
        print("  Overall building grid from Foundation Layout plan.\n")
        if not overall_L:
            overall_L = _ask_float("Overall length L (m) — longer direction", lo=5, hi=60)
        if not overall_W:
            overall_W = _ask_float("Overall width W (m) — shorter direction", lo=4, hi=40)

    grid_dims = {}
    if overall_L and overall_W:
        grid_dims = {"L_m": overall_L, "W_m": overall_W}

    print(f"\n  ✓ Sub input complete — {len(observed_elements)} elements entered")
    return observed_elements, grid_dims, warnings


# ══════════════════════════════════════════════════════════════════
# PUBLIC API — SUPERSTRUCTURE
# ══════════════════════════════════════════════════════════════════

def read_super(image_parts, col_context, slab_context, level_context,
               passes=3, name="project"):
    """
    Manual-input replacement for Gemini super-structure reading.

    Pre-fills from:
      • col_context  — column schedule (marks + dims already parsed)
      • slab_context — slab thickness (already parsed)
      • level_context — floor levels (already parsed; used to compute heights)

    Asks the user for:
      • Column counts per mark per floor (GF + FF)
      • FF slab area, Roof slab area  (m²)
      • FF beam total length, Roof beam total length  (m)
      • Avg beam b and net depth  (for accurate volume)
      • RF perimeter  (m)
      • Floor heights if not derivable from level_context

    Returns
    -------
    floor_heights : dict   {gf_floor_height_m, ff_floor_height_m, parapet_height_m}
    observed      : list[dict]
    warnings      : list[str]
    """
    print("\n" + "="*65)
    print(f"  MANUAL INPUT — SUPERSTRUCTURE  [{name}]")
    print("="*65)
    print("  Open the Column Layout, Slab Layout, and Section drawings.\n")

    observed = []
    warnings = []

    # ── FLOOR HEIGHTS ─────────────────────────────────────────────
    _section("FLOOR HEIGHTS — from Section or Elevation drawing")

    levels = _parse_levels_from_context(level_context)
    gf_ffl      = levels.get('gf_ffl')
    ff_ffl      = levels.get('ff_ffl')
    roof_ffl    = levels.get('roof_ffl')
    parapet_top = levels.get('parapet_top')

    if gf_ffl is not None and ff_ffl is not None:
        print(f"  Levels from text: GF={gf_ffl:+.3f}m  FF={ff_ffl:+.3f}m", end="")
        if roof_ffl is not None:
            print(f"  Roof={roof_ffl:+.3f}m", end="")
        if parapet_top is not None:
            print(f"  Parapet={parapet_top:+.3f}m", end="")
        print()
        computed_gf_h      = round(ff_ffl   - gf_ffl,      3)
        computed_ff_h      = round(roof_ffl  - ff_ffl,      3) if roof_ffl  else None
        computed_parapet_h = round(parapet_top - roof_ffl,  3) if (parapet_top and roof_ffl) else None
        print(f"  → GF floor height  = {computed_gf_h}m")
        if computed_ff_h is not None:
            print(f"  → FF floor height  = {computed_ff_h}m")
        if computed_parapet_h is not None:
            print(f"  → Parapet height   = {computed_parapet_h}m")
        print()

        gf_h = _ask_float("GF floor height (m) — FFL to underside of FF slab",
                          default=computed_gf_h, lo=2.0, hi=6.0)
        ff_h = _ask_float("FF floor height (m) — FFL to underside of Roof slab",
                          default=computed_ff_h if computed_ff_h else 3.20, lo=2.0, hi=6.0)
        par_h = _ask_float("Parapet height (m) — top of Roof slab to top of parapet",
                           default=computed_parapet_h if computed_parapet_h else 1.20,
                           lo=0.50, hi=2.0)
    else:
        warnings.append("Floor levels not found in text — entered manually")
        print("  Floor levels not found in text. Read from Section/Elevation drawing:\n")
        gf_h  = _ask_float("GF floor height (m)", default=3.20, lo=2.0, hi=6.0)
        ff_h  = _ask_float("FF floor height (m)", default=3.20, lo=2.0, hi=6.0)
        par_h = _ask_float("Parapet height (m)", default=1.20, lo=0.50, hi=2.0)

    floor_heights = {
        "gf_floor_height_m":  gf_h,
        "ff_floor_height_m":  ff_h,
        "parapet_height_m":   par_h,
        "source": "manual input",
    }

    # ── COLUMN COUNTS ─────────────────────────────────────────────
    _section("COLUMN COUNTS — from Column Layout plans")

    col_schedule = _parse_col_from_context(col_context)
    if col_schedule:
        print("  Column schedule from PDF text (dims are 100% accurate):\n")
        print(f"  {'MARK':<8} {'b(cm)':<7} {'d(cm)':<7}")
        print("  " + "─" * 24)
        for c in col_schedule:
            print(f"  {c['mark']:<8} {c['b_cm']:<7} {c['d_cm']:<7}")
        print()
    else:
        warnings.append("Column schedule not found in text — counts only from manual input")
        print("  (Column schedule not found in text — enter counts below)\n")

    print("  Count how many of each column mark appear on the GF plan:")
    gf_counts = {}
    for c in (col_schedule or [{'mark': 'C1', 'b_cm': 30, 'd_cm': 30}]):
        mark = c['mark']
        gf_counts[mark] = _ask_int(f"GF — {mark}", lo=0, hi=50)

    same_ff = _ask_yn("Same column layout for FF (typical for G+1)?", default=True)
    ff_counts = {}
    if same_ff:
        ff_counts = dict(gf_counts)
        print(f"  FF column counts: same as GF")
    else:
        print("\n  Count how many of each column mark appear on the FF plan:")
        for c in (col_schedule or [{'mark': 'C1'}]):
            mark = c['mark']
            ff_counts[mark] = _ask_int(f"FF — {mark}", lo=0, hi=50)

    for mark, count in gf_counts.items():
        observed.append({
            "type": "column", "mark": mark, "floor": "GF",
            "count": count, "notes": "manual input",
        })
    for mark, count in ff_counts.items():
        observed.append({
            "type": "column", "mark": mark, "floor": "FF",
            "count": count, "notes": "manual input",
        })

    # ── SLAB AREAS ────────────────────────────────────────────────
    _section("SLAB AREAS — from Slab Layout plans")
    print("  Read the net slab area (L × W of the slab boundary) in m².\n")

    ff_area   = _ask_float("FF (First Floor) slab area (m²)", lo=30, hi=800)
    roof_area = _ask_float("Roof slab area (m²)", lo=30, hi=800)

    # Extract slab thickness from slab_context
    slab_t = 0.20
    m_slab = _re.search(r'SLAB THICKNESS[^\d]*([\d.]+)\s*m', slab_context, _re.I)
    if m_slab:
        slab_t = float(m_slab.group(1))
        print(f"  Slab thickness from text: {slab_t}m")

    observed.append({"type": "slab", "floor": "FF",   "area_m2": ff_area,
                     "thickness_m": slab_t, "notes": "manual input"})
    observed.append({"type": "slab", "floor": "Roof", "area_m2": roof_area,
                     "thickness_m": slab_t, "notes": "manual input"})

    # ── BEAM LENGTHS & DIMS ───────────────────────────────────────
    _section("BEAMS — Total length per floor from Beam/Slab Layout plans")
    print("  Sum all individual beam span lengths shown on the plan.\n")

    ff_beam_len   = _ask_float("FF beam total length (m)", lo=0, hi=400)
    roof_beam_len = _ask_float("Roof beam total length (m)  [Enter 0 if same as FF]",
                               lo=0, hi=400)
    if roof_beam_len == 0 and ff_beam_len > 0:
        roof_beam_len = ff_beam_len
        print(f"  Roof beam length = FF ({ff_beam_len}m)")

    print()
    avg_beam_b    = _ask_float("Avg beam width b (m)", default=0.25, lo=0.15, hi=0.60)
    avg_beam_d    = _ask_float("Avg beam total depth d (m)", default=0.60, lo=0.30, hi=1.0)
    avg_beam_d_net = round(avg_beam_d - slab_t, 3)
    print(f"  → Beam net depth (d - slab_t) = {avg_beam_d} - {slab_t} = {avg_beam_d_net}m")

    observed.append({
        "type": "beam", "floor": "FF", "totalLength_m": ff_beam_len,
        "b_m": avg_beam_b, "d_net_m": avg_beam_d_net,
        "notes": "manual input",
    })
    observed.append({
        "type": "beam", "floor": "Roof", "totalLength_m": roof_beam_len,
        "b_m": avg_beam_b, "d_net_m": avg_beam_d_net,
        "notes": "manual input",
    })

    # ── PARAPET / RF PERIMETER ────────────────────────────────────
    _section("PARAPET — Roof perimeter from Roof Slab Layout plan")
    print("  Sum the outer edge dimensions around the roof slab.\n")

    # Prefer structural grid dims for perimeter estimate (more accurate than
    # sqrt approximation, which assumes a square slab).
    if grid_L and grid_W:
        estimated_perim = round(2 * (grid_L + grid_W), 1)
    else:
        # Rough estimate assuming a square slab — may differ for rectangular plans.
        estimated_perim = round(4 * _math.sqrt(roof_area), 1)
    rf_perim = _ask_float(
        "Roof perimeter (m)",
        default=estimated_perim,
        lo=10, hi=250
    )
    observed.append({
        "type": "parapet",
        "RF_perimeter_m": rf_perim,
        "notes": "manual input",
    })

    print(f"\n  ✓ Super input complete — {len(observed)} elements entered")
    return floor_heights, observed, warnings


# ══════════════════════════════════════════════════════════════════
# PUBLIC API — ARCHITECTURAL FINISHES
# ══════════════════════════════════════════════════════════════════

def read_arch(image_parts, gf_h, ff_h, ext_h, combo, roof_area, parapet_h,
              passes=3, name="project",
              grid_L=None, grid_W=None, parsed_dw=None):
    """
    Manual-input replacement for Gemini architectural reading.

    Pre-fills from:
      • parsed_dw       — D&W schedule from text layer (if available)
      • grid_L, grid_W  — structural anchors for cross-check hints

    Asks the user for (per floor GF + FF):
      • External perimeter
      • Wet area + wet perimeter
      • Dry area + dry perimeter
      • 20cm and 10cm wall total lengths
      • Window area
      • External door area + internal door area + door width sum
      • Balcony area

    Returns
    -------
    observed : list[dict]  — same format as vision_reader.read_arch
    dw       : list[dict]
    warnings : list[str]
    """
    print("\n" + "="*65)
    print(f"  MANUAL INPUT — ARCHITECTURAL FINISHES  [{name}]")
    print("="*65)
    print("  Open the GF and FF floor plans. Enter measurements from the drawings.\n")

    if grid_L and grid_W:
        total_area = round(grid_L * grid_W, 1)
        ext_perim_hint = round(2 * (grid_L + grid_W), 1)
        print(f"  Structural anchors: L={grid_L}m × W={grid_W}m")
        print(f"  → Total floor area ≈ {total_area} m²  |  Ext perimeter ≈ {ext_perim_hint} m\n")
    else:
        total_area = None
        ext_perim_hint = None

    observed = []
    warnings = []

    # ── D&W SCHEDULE ──────────────────────────────────────────────
    if parsed_dw:
        dw = parsed_dw
        print(f"  ✓ D&W schedule from PDF text: {len(dw)} entries")
        for e in dw:
            print(f"     {e['id']}: {e['cat']} {e['w']}×{e['h']}m  n={e['n']}")
    else:
        dw = _enter_dw_schedule()
        if not dw:
            warnings.append("D&W schedule not entered — door/window areas will be 0")

    # ── PER-FLOOR MEASUREMENTS ────────────────────────────────────
    for floor, fl_h in [("GF", gf_h), ("FF", ff_h)]:
        _section(f"{floor} FLOOR  (height = {fl_h}m)")
        print(f"  Measure on the {floor} Floor Plan:\n")

        # External perimeter
        ext_p = _ask_float(
            f"{floor} External perimeter (m) — outer wall centerline",
            default=ext_perim_hint, lo=10, hi=300
        )
        observed.append({"t": "ext_walls", "f": floor, "perim": ext_p})

        # Wet rooms
        print(f"\n  {floor} WET AREAS (kitchens, bathrooms, WC, laundry):")
        if total_area:
            print(f"  (Total floor area ≈ {total_area}m²  |  Wet + Dry must ≈ total)\n")
        wet_area  = _ask_float(f"{floor} Wet area total (m²)", lo=0, hi=200)
        wet_perim = _ask_float(f"{floor} Wet perimeter total (m)", lo=0, hi=300)
        observed.append({"t": "wet", "f": floor,
                         "area": wet_area, "perim": wet_perim, "rooms": ""})

        # Dry rooms
        print(f"\n  {floor} DRY AREAS (bedrooms, living, majlis, corridors, stairs):")
        dry_hint = round(total_area - wet_area, 1) if total_area else None
        dry_area  = _ask_float(f"{floor} Dry area total (m²)", default=dry_hint, lo=0, hi=600)
        dry_perim = _ask_float(f"{floor} Dry perimeter total (m)", lo=0, hi=500)
        observed.append({"t": "dry", "f": floor,
                         "dry": dry_area, "total": round((dry_area or 0) + (wet_area or 0), 2),
                         "perim": dry_perim})

        # Walls
        print(f"\n  {floor} INTERIOR WALLS:")
        l20 = _ask_float(f"{floor} 20cm block wall total length (m)", lo=0, hi=400)
        l10 = _ask_float(f"{floor} 10cm partition wall total length (m)", lo=0, hi=300)
        observed.append({"t": "walls20", "f": floor, "len": l20})
        observed.append({"t": "walls10", "f": floor, "len": l10})

        # Openings
        print(f"\n  {floor} OPENINGS:")
        win_a      = _ask_float(f"{floor} Window area total (m²)", lo=0, hi=200)
        door_a_ext = _ask_float(f"{floor} External door area (m²)", lo=0, hi=60)
        door_a_int = _ask_float(f"{floor} Internal door area (m²)", lo=0, hi=100)
        door_w     = _ask_float(f"{floor} Door width sum (m) — add up all door widths", lo=0, hi=60)
        observed.append({
            "t": "openings", "f": floor,
            "win_area":       win_a,
            "door_area":      round((door_a_ext or 0) + (door_a_int or 0), 3),
            "door_area_ext":  door_a_ext,
            "door_area_int":  door_a_int,
            "door_w":         door_w,
        })

        # Balcony
        bal_a = _ask_float(f"\n  {floor} Balcony area (m²)  [0 if none]",
                           default=0, lo=0, hi=100)
        observed.append({"t": "balcony", "f": floor, "area": bal_a})

    print(f"\n  ✓ Arch input complete — {len(observed)} observed entries, {len(dw)} D&W types")
    return observed, dw, warnings


# ══════════════════════════════════════════════════════════════════
# D&W SCHEDULE — manual entry helper
# ══════════════════════════════════════════════════════════════════

def _enter_dw_schedule():
    """
    Interactively enter the Doors & Windows schedule.
    Returns list of {id, cat, w, h, n, a}.
    """
    _section("DOORS & WINDOWS SCHEDULE — from D&W Schedule drawing")
    print("  Enter each door/window type from the schedule table.\n")

    entries = []
    while True:
        entry_id = input("  Type ID (e.g. D1, W1) or ENTER to finish: ").strip().upper()
        if not entry_id:
            break
        cat = "door" if "D" in entry_id else "win"
        w   = _ask_float(f"  {entry_id} Width (m)", lo=0.30, hi=5.0)
        h   = _ask_float(f"  {entry_id} Height (m)", lo=0.30, hi=4.0)
        n   = _ask_int(f"  {entry_id} Count (0 if not shown)", lo=0, hi=100)
        a   = round(w * h, 3)
        entries.append({"id": entry_id, "cat": cat, "w": w, "h": h, "n": n, "a": a})
        print(f"    Added: {entry_id} {cat} {w}×{h}m  n={n}  area={a}m²\n")

    return entries
