"""
compute_super.py — Deterministic recalculation for superstructure.
─────────────────────────────────────────────────────────────────
Takes Gemini's observedElements (column counts, slab areas, beam lengths,
floor heights) and recomputes ALL 8 super items using exact QS formulas.
"""


def recompute_super(observed_elements, floor_heights, parsed_cols,
                    slab_thickness=0.20, parapet_type="block",
                    avg_beam_b=0.25, avg_beam_d_net=0.40):
    """
    Recompute all 8 superstructure items from observed + parsed data.

    Parameters
    ----------
    observed_elements : list[dict]
        Gemini's observedElements — column counts, slab areas, beam lengths, parapet.
    floor_heights : dict
        {gf_floor_height_m, ff_floor_height_m, parapet_height_m}
    parsed_cols : list[dict]
        From parse_column_schedule — {mark, b_cm, d_cm}. 100% accurate.
    slab_thickness : float
        Slab thickness in metres (from text parser or default 0.20).
    parapet_type : str
        "block" or "concrete"

    avg_beam_b    : float, optional
        Average beam width in metres (default 0.25).  Override via manual input
        or extracted from observed beam elements.
    avg_beam_d_net : float, optional
        Average beam net depth (d − slab_t) in metres (default 0.40).

    Returns
    -------
    items : list[dict]
        8 QTO items with {id, description, unit, totalQty, breakdown, source}.
    corrections : list[str]
    """
    r = lambda v: round(v, 3)
    corrections = []

    gf_h = float(floor_heights.get("gf_floor_height_m", 3.20))
    ff_h = float(floor_heights.get("ff_floor_height_m", 3.20))
    parapet_h = float(floor_heights.get("parapet_height_m", 1.20))
    slab_t = float(slab_thickness)

    # ── Extract from observed elements ─────────────────────────────
    # Column counts by floor: {mark: count}
    gf_cols = {}   # {mark: count}
    ff_cols = {}
    ff_slab_area = 0
    roof_slab_area = 0
    ff_beam_total_length = 0
    roof_beam_total_length = 0
    ff_beam_schedule = []   # [{mark, length, b, d}]
    roof_beam_schedule = []
    rf_perimeter = 0

    for el in observed_elements:
        etype = str(el.get("type", "")).lower().replace(" ", "")
        floor = str(el.get("floor", "")).upper()
        mark  = str(el.get("mark", "")).upper()

        if etype == "column":
            count = el.get("count", 0) or 0
            dims = el.get("dims", {})
            if floor == "GF":
                gf_cols[mark] = gf_cols.get(mark, 0) + count
            elif floor in ("FF", "1F", "1ST"):
                ff_cols[mark] = ff_cols.get(mark, 0) + count

        elif etype == "slab":
            area = el.get("area_m2", 0) or 0
            if floor in ("FF", "1F", "1ST", "FIRST"):
                ff_slab_area = area
            elif floor in ("ROOF", "RF", "ROOF SLAB"):
                roof_slab_area = area

        elif etype == "beam":
            total_l = el.get("totalLength_m", 0) or 0
            if floor in ("FF", "1F", "1ST", "FIRST"):
                ff_beam_total_length = total_l
            elif floor in ("ROOF", "RF", "ROOF SLAB"):
                roof_beam_total_length = total_l

        elif etype == "parapet":
            rf_perimeter = el.get("RF_perimeter_m", 0) or 0

    # ── Sanity-clamp observed values using villa bounds ────────────
    MAX_BEAM_LEN = 400   # metres per floor (villa max)
    MAX_COL_PER_FLOOR = 40

    if ff_beam_total_length > MAX_BEAM_LEN:
        # Estimate from slab: beams ≈ 2×perimeter + internal grid ≈ sqrt(area)*6
        import math
        est = round(math.sqrt(ff_slab_area) * 6, 1) if ff_slab_area > 0 else 80
        corrections.append(
            f"  ⚠ FF beam length {ff_beam_total_length}m > {MAX_BEAM_LEN}m → estimated {est}m from slab area"
        )
        ff_beam_total_length = est

    if roof_beam_total_length > MAX_BEAM_LEN:
        import math
        est = round(math.sqrt(roof_slab_area) * 6, 1) if roof_slab_area > 0 else 80
        corrections.append(
            f"  ⚠ Roof beam length {roof_beam_total_length}m > {MAX_BEAM_LEN}m → estimated {est}m from slab area"
        )
        roof_beam_total_length = est

    for cols_dict, label in [(gf_cols, "GF"), (ff_cols, "FF")]:
        total = sum(cols_dict.values())
        if total > MAX_COL_PER_FLOOR:
            corrections.append(f"  ⚠ {label} column count={total} > {MAX_COL_PER_FLOOR} — may be inflated")

    # ── Override column counts with text-parsed counts if available ─
    # parsed_cols from text parser have 100% accurate counts.
    # Gemini often miscounts (e.g. counts grid intersections = 49 instead of actual columns).
    text_col_counts = {}
    for c in parsed_cols:
        cnt = c.get("count", 0)
        if cnt > 0:
            text_col_counts[c["mark"]] = cnt

    if text_col_counts:
        total_text = sum(text_col_counts.values())
        total_gemini_gf = sum(gf_cols.values())
        if total_text != total_gemini_gf:
            corrections.append(
                f"  Column counts from text={total_text} vs Gemini GF={total_gemini_gf} — using text counts"
            )
        gf_cols = dict(text_col_counts)
        ff_cols = dict(text_col_counts)   # Same layout for GF and FF in typical G+1 villa

    # ── Parse column dims from schedule ────────────────────────────
    # Map mark → (b_m, d_m) — prefer parsed dims, fallback to Gemini observed dims
    col_dims = {}
    for c in parsed_cols:
        if "b_cm" in c and "d_cm" in c:
            col_dims[c["mark"]] = (c["b_cm"] / 100, c["d_cm"] / 100)

    # If parser didn't get dims, use Gemini's observed dims
    if not col_dims:
        for el in observed_elements:
            if str(el.get("type","")).lower().replace(" ","") == "column":
                mk = str(el.get("mark","")).upper()
                dims = el.get("dims", {})
                b = float(dims.get("b_cm", 30)) / 100
                d = float(dims.get("d_cm", 30)) / 100
                if mk and mk not in col_dims:
                    col_dims[mk] = (b, d)

    # ── Roof beams fallback: if roof=0 but FF>0, copy FF ──────────
    if roof_beam_total_length == 0 and ff_beam_total_length > 0:
        roof_beam_total_length = ff_beam_total_length
        corrections.append(
            f"  Roof beam length=0 → using FF beam length ({ff_beam_total_length}m) as estimate"
        )

    # ── GF Columns ─────────────────────────────────────────────────
    gf_col_parts = []
    gf_col_total = 0
    for mark, count in gf_cols.items():
        b, d = col_dims.get(mark, (0.30, 0.30))
        v = r(count * b * d * gf_h)
        gf_col_total += v
        gf_col_parts.append(f"{mark}:{count}×{b}×{d}×{gf_h}={v}")
    gf_col_total = r(gf_col_total)

    # ── FF Columns ─────────────────────────────────────────────────
    ff_col_parts = []
    ff_col_total = 0
    for mark, count in ff_cols.items():
        b, d = col_dims.get(mark, (0.30, 0.30))
        v = r(count * b * d * ff_h)
        ff_col_total += v
        ff_col_parts.append(f"{mark}:{count}×{b}×{d}×{ff_h}={v}")
    ff_col_total = r(ff_col_total)

    # ── Slabs ──────────────────────────────────────────────────────
    ff_slab  = r(ff_slab_area * slab_t)
    roof_slab = r(roof_slab_area * slab_t)

    # ── Beams ──────────────────────────────────────────────────────
    # Use b_m / d_net_m from observed beam elements if the caller stored them
    # (manual_input.py writes these fields).  Fall back to the function arguments
    # (which themselves fall back to defaults 0.25 / 0.40).
    for el in observed_elements:
        etype = str(el.get("type", "")).lower().replace(" ", "")
        if etype == "beam":
            if el.get("b_m"):
                avg_beam_b = float(el["b_m"])
            if el.get("d_net_m"):
                avg_beam_d_net = float(el["d_net_m"])
            break   # one beam element is enough — all floors share same avg dims

    ff_beams  = r(ff_beam_total_length * avg_beam_b * avg_beam_d_net)
    roof_beams = r(roof_beam_total_length * avg_beam_b * avg_beam_d_net)

    if ff_beams == 0 and ff_beam_total_length == 0:
        corrections.append("  ⚠ FF beam total length = 0")
    if roof_beams == 0 and roof_beam_total_length == 0:
        corrections.append("  ⚠ Roof beam total length = 0")

    # ── Parapet ────────────────────────────────────────────────────
    if rf_perimeter == 0 and roof_slab_area > 0:
        # Estimate: assume square slab
        import math
        side = math.sqrt(roof_slab_area)
        rf_perimeter = r(4 * side)
        corrections.append(f"  RF perimeter estimated from area: {rf_perimeter}m")

    if parapet_type == "concrete":
        parapet_conc = r(rf_perimeter * 0.20 * parapet_h)
        parapet_block = 0
    else:
        parapet_conc = r(rf_perimeter * 0.20 * 0.20)   # coping beam
        parapet_block = r(rf_perimeter * (parapet_h - 0.20))

    # ── Build items ────────────────────────────────────────────────
    items = [
        {"id": "gf_columns", "description": "GF Columns Concrete",
         "unit": "m3", "totalQty": gf_col_total,
         "breakdown": " + ".join(gf_col_parts) if gf_col_parts else "no cols",
         "source": "parser_dims + vision_counts"},

        {"id": "ff_columns", "description": "FF Columns Concrete",
         "unit": "m3", "totalQty": ff_col_total,
         "breakdown": " + ".join(ff_col_parts) if ff_col_parts else "no cols",
         "source": "parser_dims + vision_counts"},

        {"id": "ff_beams", "description": "First Floor Beams Concrete",
         "unit": "m3", "totalQty": ff_beams,
         "breakdown": f"{ff_beam_total_length}×{avg_beam_b}×{avg_beam_d_net}={ff_beams}",
         "source": "vision_lengths + default_dims"},

        {"id": "ff_slab", "description": "First Floor Slab Concrete",
         "unit": "m3", "totalQty": ff_slab,
         "breakdown": f"{ff_slab_area}×{slab_t}={ff_slab}",
         "source": "vision_area + parser_thickness"},

        {"id": "roof_beams", "description": "Roof Beams Concrete",
         "unit": "m3", "totalQty": roof_beams,
         "breakdown": f"{roof_beam_total_length}×{avg_beam_b}×{avg_beam_d_net}={roof_beams}",
         "source": "vision_lengths + default_dims"},

        {"id": "roof_slab", "description": "Roof Slab Concrete",
         "unit": "m3", "totalQty": roof_slab,
         "breakdown": f"{roof_slab_area}×{slab_t}={roof_slab}",
         "source": "vision_area + parser_thickness"},

        {"id": "parapet_concrete", "description": "Parapet Coping Concrete",
         "unit": "m3", "totalQty": parapet_conc,
         "breakdown": f"{rf_perimeter}×0.20×{'0.20' if parapet_type=='block' else parapet_h}={parapet_conc}",
         "source": "deterministic"},

        {"id": "parapet_block", "description": "Parapet Block Work",
         "unit": "m2", "totalQty": parapet_block,
         "breakdown": f"{rf_perimeter}×({parapet_h}-0.20)={parapet_block}" if parapet_type == "block" else "N/A (concrete parapet)",
         "source": "deterministic"},
    ]

    return items, corrections
