"""
compute_sub.py — Deterministic recalculation for substructure.
──────────────────────────────────────────────────────────────
Takes Gemini's observedElements (counts, dimensions, lengths)
and recomputes ALL 13 sub items using exact QS formulas.

This REPLACES Gemini's calculated values — we only trust Gemini
for what it can SEE (counts, lengths), not what it CALCULATES.
"""


def recompute_sub(observed_elements, parsed_footings, parsed_tbs, parsed_cols,
                  overall_L, overall_W, gf_level, tb_level,
                  excav_depth, road_base, road_base_t):
    """
    Recompute all 13 substructure items from observed + parsed data.

    Parameters
    ----------
    observed_elements : list[dict]
        Gemini's observedElements — we extract COUNTS and LENGTHS only.
    parsed_footings : list[dict]
        From parse_footing_schedule — {mark, L_cm, W_cm, H_cm}. 100% accurate.
    parsed_tbs : list[dict]
        From parse_tb_schedule — {mark, b_cm, d_cm}. 100% accurate.
    parsed_cols : list[dict]
        From parse_column_schedule — {mark, b_cm, d_cm}. 100% accurate.
    overall_L, overall_W : float
        Grid dimensions (metres) — from parse_grid_dims. 100% accurate.
    gf_level : float
        GF slab level above NGL (metres).
    tb_level : float
        TB level (metres) — typically same as gf_level.
    excav_depth : float
        User-provided excavation depth (metres).
    road_base : bool
        Whether road base is required.
    road_base_t : float
        Road base thickness (metres).

    Returns
    -------
    items : list[dict]
        13 QTO items with {id, description, unit, totalQty, breakdown, source}.
    corrections : list[str]
        List of corrections made vs Gemini's original values.
    """
    r = lambda v: round(v, 3)
    corrections = []

    if gf_level is None:
        gf_level = 0.80   # typical UAE default

    # ── Extract COUNTS from Gemini's observed (vision data) ────────
    # Build: footing_counts = {mark: count}, tb_lengths = {mark: total_length_m}
    footing_counts = {}
    tb_lengths = {}
    col_counts = {}   # {mark: count} — may not be needed for sub, but useful

    for el in observed_elements:
        etype = str(el.get("type", "")).lower().replace(" ", "")
        mark  = str(el.get("mark", "")).upper()
        count = el.get("count", 0) or 0
        dims  = el.get("dims", {})

        if etype in ("footing", "isolatedfooting", "isolated_footing", "foundation"):
            if mark and count > 0:
                footing_counts[mark] = footing_counts.get(mark, 0) + count
        elif etype in ("tiebeam", "tie_beam", "tbeam", "tb"):
            length = dims.get("totalLength_m") or dims.get("L") or el.get("totalLength_m") or 0
            if mark and length:
                tb_lengths[mark] = tb_lengths.get(mark, 0) + float(length)
        elif etype in ("column", "neckcolumn", "neck_column"):
            if mark and count > 0:
                col_counts[mark] = col_counts.get(mark, 0) + count

    # ── Match parsed dims to Gemini counts ─────────────────────────
    # Footings: parser gives dims, Gemini gives counts
    ftg_data = []   # [{mark, L_m, W_m, H_m, count}]
    for pf in parsed_footings:
        mark = pf["mark"]
        L_m = pf["L_cm"] / 100
        W_m = pf["W_cm"] / 100
        H_m = pf["H_cm"] / 100
        # Try exact mark match first
        count = footing_counts.get(mark, 0)
        if count == 0:
            # Try matching by dims — Gemini might use different mark names
            for gmark, gcount in footing_counts.items():
                # Check if any observed element has similar dims
                for el in observed_elements:
                    if str(el.get("mark", "")).upper() == gmark:
                        d = el.get("dims", {})
                        el_L = d.get("L", 0)
                        el_W = d.get("W", 0)
                        if (abs(el_L - L_m) < 0.05 and abs(el_W - W_m) < 0.05) or \
                           (abs(el_L - W_m) < 0.05 and abs(el_W - L_m) < 0.05):
                            count = gcount
                            corrections.append(
                                f"  Matched footing {mark} ({L_m}×{W_m}m) to Gemini mark '{gmark}' (count={gcount})"
                            )
                            break
                if count > 0:
                    break
        if count == 0:
            corrections.append(f"  ⚠ Footing {mark}: count=0 from Gemini — using 0")
        ftg_data.append({"mark": mark, "L": L_m, "W": W_m, "H": H_m, "count": count})

    # ── Fallback: build ftg_data from Gemini elements when parser found nothing ──
    # This handles PDFs where text layer has no footing schedule (SCHEDULE OF FOOTING/S)
    if not ftg_data:
        for el in observed_elements:
            etype = str(el.get("type", "")).lower().replace(" ", "")
            if etype not in ("footing", "isolatedfooting", "isolated_footing", "foundation"):
                continue
            mark  = str(el.get("mark", "")).upper()
            count = el.get("count", 0) or 0
            dims  = el.get("dims", {})
            L_m = float(dims.get("L", 0))
            W_m = float(dims.get("W", dims.get("B", 0)))
            H_m = float(dims.get("H") or dims.get("T") or 0)
            # If H still 0 — use default 0.40 m (standard UAE villa footing depth)
            if H_m <= 0:
                H_m = 0.40
                corrections.append(f"  Footing {mark}: H not in Gemini output — defaulted to 0.40m")
            if mark and count > 0 and L_m > 0 and W_m > 0:
                ftg_data.append({"mark": mark, "L": L_m, "W": W_m, "H": H_m, "count": count})
        if ftg_data:
            corrections.append(
                f"  Footings: parser found nothing — used Gemini dims directly "
                f"({len(ftg_data)} types)"
            )

    # TBs: parser gives b×d, Gemini gives lengths
    tb_data = []   # [{mark, b_m, d_m, length_m}]
    for pt in parsed_tbs:
        mark = pt["mark"]
        b_m = pt["b_cm"] / 100
        d_m = pt["d_cm"] / 100
        length = tb_lengths.get(mark, 0)
        if length == 0:
            # Try case-insensitive or partial match
            for gmark, glen in tb_lengths.items():
                if gmark.replace(" ", "") == mark.replace(" ", ""):
                    length = glen
                    break
        if length == 0:
            corrections.append(f"  ⚠ TB {mark}: length=0 from Gemini — using 0")
        tb_data.append({"mark": mark, "b": b_m, "d": d_m, "length": length})

    # ── Fallback: build tb_data from Gemini elements when parser found nothing ──
    if not tb_data:
        for el in observed_elements:
            etype = str(el.get("type", "")).lower().replace(" ", "")
            if etype not in ("tiebeam", "tie_beam", "tbeam", "tb"):
                continue
            mark  = str(el.get("mark", "")).upper()
            dims  = el.get("dims", {})
            b_m   = float(dims.get("b", dims.get("B", 0)))
            d_m   = float(dims.get("d", dims.get("D", 0)))
            # Lengths may be in L or totalLength_m
            length = float(dims.get("totalLength_m", dims.get("L", 0))) or \
                     float(el.get("totalLength_m", 0))
            # Also check tb_lengths by mark
            if length == 0:
                length = tb_lengths.get(mark, 0)
            if b_m <= 0:
                b_m = 0.20  # default
            if d_m <= 0:
                d_m = 0.40  # default
                corrections.append(f"  TB {mark}: depth from Gemini = 0 — defaulted to 0.40m")
            if mark and length > 0:
                tb_data.append({"mark": mark, "b": b_m, "d": d_m, "length": length})
        if tb_data:
            corrections.append(
                f"  TBs: parser found nothing — used Gemini dims directly "
                f"({len(tb_data)} types)"
            )

    # Columns: parser gives b×d, we need count per type
    # For neck columns: total count should = total footing count
    total_footing_count = sum(f["count"] for f in ftg_data)

    # ── Fallback: build parsed_cols from Gemini elements when parser found nothing ──
    if not parsed_cols:
        for el in observed_elements:
            etype = str(el.get("type", "")).lower().replace(" ", "")
            if etype not in ("column", "neckcolumn", "neck_column"):
                continue
            mark = str(el.get("mark", "")).upper()
            dims = el.get("dims", {})
            b_cm = float(dims.get("b", dims.get("B", 0))) * 100  # Gemini gives in m
            d_cm = float(dims.get("d", dims.get("D", 0))) * 100
            if mark and b_cm > 0 and d_cm > 0:
                parsed_cols.append({"mark": mark, "b_cm": b_cm, "d_cm": d_cm})

    # ── CALCULATIONS ── (exact QS formulas) ────────────────────────

    # Areas
    excav_area = r((overall_L + 2.0) * (overall_W + 2.0))
    sog_area   = r(overall_L * overall_W)
    gf_perim   = r(2 * (overall_L + overall_W))

    # 1. Excavation
    excavation = r(excav_area * excav_depth)

    # 2. Road Base
    road_base_v = r(sog_area * road_base_t) if road_base else 0

    # 3. PCC under Footings: Count × (L+0.10) × (W+0.10) × 0.10 per type
    pcc_ftg_parts = []
    pcc_ftg = 0
    for f in ftg_data:
        v = r(f["count"] * (f["L"] + 0.10) * (f["W"] + 0.10) * 0.10)
        pcc_ftg += v
        pcc_ftg_parts.append(f"{f['mark']}:{f['count']}×({f['L']}+0.1)×({f['W']}+0.1)×0.1={v}")
    pcc_ftg = r(pcc_ftg)

    # 4. PCC under TBs: Length × (b+0.20) × 0.10 per type
    pcc_tb_parts = []
    pcc_tb = 0
    for t in tb_data:
        v = r(t["length"] * (t["b"] + 0.20) * 0.10)
        pcc_tb += v
        pcc_tb_parts.append(f"{t['mark']}:{t['length']}×({t['b']}+0.2)×0.1={v}")
    pcc_tb = r(pcc_tb)

    # 5. Footing Concrete: Count × L × W × H per type
    ftg_conc_parts = []
    ftg_conc = 0
    for f in ftg_data:
        v = r(f["count"] * f["L"] * f["W"] * f["H"])
        ftg_conc += v
        ftg_conc_parts.append(f"{f['mark']}:{f['count']}×{f['L']}×{f['W']}×{f['H']}={v}")
    ftg_conc = r(ftg_conc)

    # 6. Neck Column: Count × col_b × col_d × H_neck per type
    # Equation sheet: H_neck = (GFL + excav_depth) - TB_depth - PCC(0.10)
    # Using per-footing height: H_neck = (GFL + excav) - footing_H - PCC
    neck_parts = []
    neck_conc = 0
    PCC_T = 0.10   # PCC thickness always 10cm
    # Default column dims (smallest column from schedule, skip entries without dims)
    cols_with_dims = [c for c in parsed_cols if "b_cm" in c and "d_cm" in c]
    if cols_with_dims:
        def_b = min(c["b_cm"] for c in cols_with_dims) / 100
        def_d = min(c["d_cm"] for c in cols_with_dims) / 100
    else:
        def_b, def_d = 0.30, 0.30

    for f in ftg_data:
        h_neck = r((excav_depth + gf_level) - f["H"] - PCC_T)
        if h_neck <= 0:
            h_neck = 0.10   # minimum
        # Find column that fits inside this footing (col ≤ footing)
        col_b, col_d = def_b, def_d
        for c in cols_with_dims:
            cb, cd = c["b_cm"]/100, c["d_cm"]/100
            if cb <= f["L"] + 0.01 and cd <= f["W"] + 0.01:
                col_b, col_d = cb, cd
                break
            if cd <= f["L"] + 0.01 and cb <= f["W"] + 0.01:
                col_b, col_d = cd, cb
                break
        v = r(f["count"] * col_b * col_d * h_neck)
        neck_conc += v
        neck_parts.append(f"{f['mark']}:{f['count']}×{col_b}×{col_d}×{h_neck}={v}")
    neck_conc = r(neck_conc)

    # 7. TB Concrete: Length × b × d per type
    tb_conc_parts = []
    tb_conc = 0
    for t in tb_data:
        v = r(t["length"] * t["b"] * t["d"])
        tb_conc += v
        tb_conc_parts.append(f"{t['mark']}:{t['length']}×{t['b']}×{t['d']}={v}")
    tb_conc = r(tb_conc)

    # 8. Bitumen (5 components)
    # a) Footing sides: Count × 2×(L+W) × H per type
    bit_ftg_sides = 0
    for f in ftg_data:
        bit_ftg_sides += f["count"] * 2 * (f["L"] + f["W"]) * f["H"]
    bit_ftg_sides = r(bit_ftg_sides)

    # b) Footing tops (exposed area minus column footprint)
    bit_ftg_tops = 0
    for f in ftg_data:
        col_b, col_d = def_b, def_d
        for c in parsed_cols:
            cb, cd = c["b_cm"]/100, c["d_cm"]/100
            if (cb <= f["L"] + 0.01 and cd <= f["W"] + 0.01) or \
               (cd <= f["L"] + 0.01 and cb <= f["W"] + 0.01):
                col_b, col_d = cb, cd
                break
        bit_ftg_tops += f["count"] * (f["L"] * f["W"] - col_b * col_d)
    bit_ftg_tops = r(bit_ftg_tops)

    # c) Neck column sides: Count × 2×(col_b+col_d) × h_neck
    bit_nc_sides = 0
    for f in ftg_data:
        h_neck = r((excav_depth + gf_level) - f["H"] - PCC_T)
        if h_neck <= 0:
            h_neck = 0.10
        col_b, col_d = def_b, def_d
        for c in parsed_cols:
            cb, cd = c["b_cm"]/100, c["d_cm"]/100
            if (cb <= f["L"] + 0.01 and cd <= f["W"] + 0.01) or \
               (cd <= f["L"] + 0.01 and cb <= f["W"] + 0.01):
                col_b, col_d = cb, cd
                break
        bit_nc_sides += f["count"] * 2 * (col_b + col_d) * h_neck
    bit_nc_sides = r(bit_nc_sides)

    # d) Block wall sub: GFPerimeter × block_h × 2 (both faces)
    # Equation sheet: block_h = (GFL + excav_depth) - TB_depth - PCC_thickness
    deepest_tb_d = max((t["d"] for t in tb_data), default=0.60)
    block_h = r((excav_depth + gf_level) - deepest_tb_d - PCC_T)
    if block_h <= 0:
        block_h = 0.50
    bit_block = r(gf_perim * block_h * 2)

    # e) TB top face: total_tb_length × tb_b (average width)
    avg_tb_b = sum(t["b"] for t in tb_data) / len(tb_data) if tb_data else 0.25
    total_tb_len = sum(t["length"] for t in tb_data)
    bit_tb = r(total_tb_len * avg_tb_b)

    bitumen = r(bit_ftg_sides + bit_ftg_tops + bit_nc_sides + bit_block + bit_tb)

    # 9. Block wall sub-structure: GFPerimeter × block_h
    blockwall = r(gf_perim * block_h)

    # 10. Slab on Grade
    slab_on_grade = r(sog_area * 0.10)

    # 11. Polythene: PCC_ftg_area + PCC_tb_area + SoG_area
    pcc_ftg_area = 0
    for f in ftg_data:
        pcc_ftg_area += f["count"] * (f["L"] + 0.10) * (f["W"] + 0.10)
    pcc_ftg_area = r(pcc_ftg_area)

    pcc_tb_area = 0
    for t in tb_data:
        pcc_tb_area += t["length"] * (t["b"] + 0.20)
    pcc_tb_area = r(pcc_tb_area)

    polythene = r(pcc_ftg_area + pcc_tb_area + sog_area)

    # 12. Anti-Termite
    anti_termite = r(polythene * 1.15)

    # 13. Backfill = Excavated void − ALL items placed inside the excavation
    # Equation sheet: (Area × Excav_level) - (All items volume)
    # Void = excavation volume (below road level only)
    backfill_void = r(excav_area * excav_depth)
    block_vol     = r(blockwall * 0.20)   # 20cm block
    all_items_vol = r(pcc_ftg + pcc_tb + ftg_conc + neck_conc + tb_conc
                      + slab_on_grade + block_vol + road_base_v)
    backfill = r(backfill_void - all_items_vol)
    if backfill < 0:
        corrections.append(f"  ⚠ Backfill negative ({backfill}) — clamped to 0")
        backfill = 0

    # ── Build items list ───────────────────────────────────────────
    items = [
        {"id": "excavation",          "description": "Bulk Excavation",
         "unit": "m3", "totalQty": excavation,
         "breakdown": f"({overall_L}+2)×({overall_W}+2)×{excav_depth}={excavation}",
         "source": "deterministic"},

        {"id": "road_base",           "description": "Road Base",
         "unit": "m3", "totalQty": road_base_v,
         "breakdown": f"{overall_L}×{overall_W}×{road_base_t}={road_base_v}" if road_base else "N/A",
         "source": "deterministic"},

        {"id": "pcc_footings",        "description": "PCC under Footings",
         "unit": "m3", "totalQty": pcc_ftg,
         "breakdown": " + ".join(pcc_ftg_parts),
         "source": "parser_dims + vision_counts"},

        {"id": "pcc_tb",              "description": "PCC under Tie Beams",
         "unit": "m3", "totalQty": pcc_tb,
         "breakdown": " + ".join(pcc_tb_parts),
         "source": "parser_dims + vision_lengths"},

        {"id": "footing_concrete",    "description": "Isolated Footing Concrete",
         "unit": "m3", "totalQty": ftg_conc,
         "breakdown": " + ".join(ftg_conc_parts),
         "source": "parser_dims + vision_counts"},

        {"id": "neck_column",         "description": "Neck Column Concrete",
         "unit": "m3", "totalQty": neck_conc,
         "breakdown": " + ".join(neck_parts),
         "source": "parser_dims + vision_counts"},

        {"id": "tb_concrete",         "description": "Tie Beam RC Concrete",
         "unit": "m3", "totalQty": tb_conc,
         "breakdown": " + ".join(tb_conc_parts),
         "source": "parser_dims + vision_lengths"},

        {"id": "bitumen",             "description": "Bituminous Waterproofing",
         "unit": "m2", "totalQty": bitumen,
         "breakdown": f"ftg_sides={bit_ftg_sides}+ftg_tops={bit_ftg_tops}+nc_sides={bit_nc_sides}+block={bit_block}+tb={bit_tb}",
         "source": "deterministic"},

        {"id": "blockwall_solid_sub", "description": "Solid Block Sub-Structure",
         "unit": "m2", "totalQty": blockwall,
         "breakdown": f"{gf_perim}×{block_h}={blockwall}",
         "source": "deterministic"},

        {"id": "slab_on_grade",       "description": "Slab on Grade Concrete",
         "unit": "m3", "totalQty": slab_on_grade,
         "breakdown": f"{overall_L}×{overall_W}×0.10={slab_on_grade}",
         "source": "deterministic"},

        {"id": "polythene",           "description": "Polythene Sheet",
         "unit": "m2", "totalQty": polythene,
         "breakdown": f"pcc_ftg={pcc_ftg_area}+pcc_tb={pcc_tb_area}+sog={sog_area}",
         "source": "deterministic"},

        {"id": "anti_termite",        "description": "Anti-Termite Treatment",
         "unit": "m2", "totalQty": anti_termite,
         "breakdown": f"{polythene}×1.15={anti_termite}",
         "source": "deterministic"},

        {"id": "backfill",            "description": "Backfill Compacted",
         "unit": "m3", "totalQty": backfill,
         "breakdown": f"void={backfill_void}-all_items={all_items_vol}(pcc_f={pcc_ftg}+pcc_t={pcc_tb}+ftg={ftg_conc}+nc={neck_conc}+tb={tb_conc}+sog={slab_on_grade}+blk={block_vol}+rb={road_base_v})",
         "source": "deterministic"},
    ]

    return items, corrections
