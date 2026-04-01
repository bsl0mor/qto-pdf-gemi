"""
guards.py — Sanity guards for QTO-AI pipeline.
─────────────────────────────────────────────────
Villa-specific range checks for observed values and computed items.
Any value outside bounds is flagged; the caller decides what to do
(auto-fix, re-query Gemini, or warn the user).
"""

# ═══════════════════════════════════════════════════════════════════
# VILLA BOUNDS — UAE residential villa G+1 (200–800 m² footprint)
# ═══════════════════════════════════════════════════════════════════

# (min, max) — inclusive.  None = no bound on that side.

# ── Substructure observed ──────────────────────────────────────────
SUB_OBSERVED = {
    "overall_L":   (8.0,   50.0),    # metres — villa grid length
    "overall_W":   (6.0,   35.0),    # metres — villa grid width
    "gf_level":    (0.0,    2.0),    # metres above NGL
    "tb_level":    (0.0,    1.5),    # metres above NGL
    "footing_count_total": (4, 60),  # total isolated footings
    "footing_L":   (0.80,   4.0),    # metres — single footing L
    "footing_W":   (0.80,   4.0),    # metres — single footing W
    "footing_H":   (0.25,   0.85),   # metres — footing depth
    "tb_b":        (0.15,   0.50),   # metres — tie beam width
    "tb_d":        (0.30,   0.80),   # metres — tie beam depth
    "tb_total_length": (20, 500),    # metres — total TB run
    "col_b":       (0.15,   0.80),   # metres — column short dim
    "col_d":       (0.15,   0.80),   # metres — column long dim
    "neck_h":      (0.10,   2.50),   # metres — neck column height
}

# ── Substructure computed items ────────────────────────────────────
SUB_ITEMS = {
    "excavation":          (10,    3000),   # m³
    "road_base":           (0,      300),   # m³
    "pcc_footings":        (1,      100),   # m³
    "pcc_tb":              (1,       50),   # m³
    "footing_concrete":    (5,      400),   # m³
    "neck_column":         (1,       50),   # m³
    "tb_concrete":         (5,      200),   # m³
    "bitumen":             (50,    3000),   # m²
    "blockwall_solid_sub": (20,     500),   # m²
    "slab_on_grade":       (5,      200),   # m³
    "polythene":           (50,    2000),   # m²
    "anti_termite":        (60,    2500),   # m²
    "backfill":            (10,    3000),   # m³
}

# ── Superstructure observed ────────────────────────────────────────
SUPER_OBSERVED = {
    "gf_floor_height":  (2.5,   5.5),   # metres
    "ff_floor_height":  (2.5,   5.5),   # metres
    "parapet_height":   (0.50,  2.0),   # metres
    "slab_thickness":   (0.12,  0.30),  # metres
    "slab_area":        (50,    800),   # m² per floor
    "beam_total_length":(10,    400),   # metres per floor
    "beam_b":           (0.15,  0.60),  # metres
    "beam_d":           (0.30,  1.00),  # metres
    "col_count_floor":  (2,     40),    # columns per floor
    "rf_perimeter":     (20,    200),   # metres
}

# ── Superstructure computed items ──────────────────────────────────
SUPER_ITEMS = {
    "gf_columns":       (1,     80),    # m³
    "ff_columns":       (1,     80),    # m³
    "ff_beams":         (2,     60),    # m³
    "ff_slab":          (10,   200),    # m³
    "roof_beams":       (2,     60),    # m³
    "roof_slab":        (10,   200),    # m³
    "parapet_concrete":  (0.5,  10),    # m³
    "parapet_block":    (5,    200),    # m²
}

# ── Architectural observed ─────────────────────────────────────────
ARCH_OBSERVED = {
    "ext_perimeter":    (20,   200),    # metres per floor
    "wet_area":         (5,    120),    # m² per floor
    "wet_perimeter":    (10,   250),    # metres per floor
    "dry_area":         (30,   500),    # m² per floor
    "dry_perimeter":    (30,   400),    # metres per floor
    "balcony_area":     (0,    100),    # m² per floor
    "walls_20_len":     (10,   400),    # metres per floor
    "walls_10_len":     (0,    200),    # metres per floor
    "win_area":         (0,    150),    # m² per floor
    "door_area":        (0,    100),    # m² per floor
    "door_w_sum":       (0,     50),    # metres per floor
}

# ── Architectural computed items ───────────────────────────────────
ARCH_ITEMS = {
    "block_20_ext":     (20,  1000),   # m²
    "block_20_int":     (10,   800),   # m²
    "block_10_int":     (0,    500),   # m²
    "plaster_int":      (50,  2000),   # m²
    "flooring_dry":     (30,   500),   # m²
    "flooring_wet":     (5,    120),   # m²
    "skirting":         (10,   400),   # m
    "paint":            (50,  2000),   # m²
    "ceiling_dry":      (30,   500),   # m²
    "ceiling_wet":      (5,    120),   # m²
    "tiles_wall":       (10,   600),   # m²
    "finish_ext":       (100, 3000),   # m²
    "marble_threshold": (3,     60),   # RM
    "balcony_flooring": (0,    200),   # m²
    "waterproofing":    (0,    200),   # m²
    "roof_waterproofing": (50, 800),   # m²
    "combo_roof":       (60,  1000),   # m²
    "doors_schedule":   (3,     50),   # No.
    "windows_schedule": (5,    200),   # m²
}


# ═══════════════════════════════════════════════════════════════════
# CHECK FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

def check_value(value, bounds, label=""):
    """
    Check if value is within bounds.
    Returns (ok, message).
    """
    if value is None or value == 0:
        return True, ""   # skip zero/None — might be legitimately absent
    lo, hi = bounds
    if lo is not None and value < lo:
        return False, f"  ✗ {label} = {value} < min {lo}"
    if hi is not None and value > hi:
        return False, f"  ✗ {label} = {value} > max {hi}"
    return True, ""


def check_sub_items(items_dict):
    """
    Check substructure QTO items against villa bounds.
    items_dict: {item_id: qty_value}
    Returns list of (item_id, value, ok, message).
    """
    results = []
    for iid, bounds in SUB_ITEMS.items():
        val = items_dict.get(iid, 0)
        ok, msg = check_value(val, bounds, iid)
        results.append((iid, val, ok, msg))
    return results


def check_super_items(items_dict):
    """Check superstructure QTO items against villa bounds."""
    results = []
    for iid, bounds in SUPER_ITEMS.items():
        val = items_dict.get(iid, 0)
        ok, msg = check_value(val, bounds, iid)
        results.append((iid, val, ok, msg))
    return results


def check_arch_items(items_dict):
    """
    Check arch QTO items against villa bounds.
    Items may have GF/FF suffix — strip it for bound lookup.
    """
    results = []
    for iid, val in items_dict.items():
        # Strip _gf/_ff suffix for bounds lookup
        base = iid.replace("_gf", "").replace("_ff", "")
        bounds = ARCH_ITEMS.get(base)
        if bounds:
            ok, msg = check_value(val, bounds, iid)
            results.append((iid, val, ok, msg))
    return results


def check_super_observed(observed_elements, floor_heights):
    """Check superstructure observed data quality."""
    results = []

    # Floor heights
    for key, bound_key in [
        ("gf_floor_height_m", "gf_floor_height"),
        ("ff_floor_height_m", "ff_floor_height"),
        ("parapet_height_m",  "parapet_height"),
    ]:
        val = floor_heights.get(key, 0)
        bounds = SUPER_OBSERVED.get(bound_key)
        if bounds and val:
            ok, msg = check_value(val, bounds, key)
            results.append((key, val, ok, msg))

    # Observed elements
    for el in observed_elements:
        t = str(el.get("type", "")).lower()
        fl = str(el.get("floor", "")).upper()

        if t == "column":
            count = el.get("count", 0)
            ok, msg = check_value(count, SUPER_OBSERVED["col_count_floor"],
                                  f"column count {fl}")
            results.append((f"col_count_{fl}", count, ok, msg))

        elif t == "slab":
            area = el.get("area_m2", 0)
            ok, msg = check_value(area, SUPER_OBSERVED["slab_area"],
                                  f"slab area {fl}")
            results.append((f"slab_area_{fl}", area, ok, msg))

            thick = el.get("thickness_m", 0)
            if thick:
                ok, msg = check_value(thick, SUPER_OBSERVED["slab_thickness"],
                                      f"slab thickness {fl}")
                results.append((f"slab_t_{fl}", thick, ok, msg))

        elif t == "beam":
            total_l = el.get("totalLength_m", 0)
            if total_l:
                ok, msg = check_value(total_l, SUPER_OBSERVED["beam_total_length"],
                                      f"beam total length {fl}")
                results.append((f"beam_len_{fl}", total_l, ok, msg))

        elif t == "parapet":
            perim = el.get("RF_perimeter_m", 0)
            if perim:
                ok, msg = check_value(perim, SUPER_OBSERVED["rf_perimeter"],
                                      f"RF perimeter")
                results.append(("rf_perimeter", perim, ok, msg))

    return results


def check_arch_observed(observed_list):
    """Check architectural observed data quality."""
    results = []
    for o in observed_list:
        t = o.get("t", "")
        f_ = o.get("f", "")

        if t == "ext_walls":
            p = o.get("perim", 0)
            ok, msg = check_value(p, ARCH_OBSERVED["ext_perimeter"], f"ext_perim {f_}")
            results.append((f"ext_perim_{f_}", p, ok, msg))

        elif t == "wet":
            a = o.get("area", 0)
            ok, msg = check_value(a, ARCH_OBSERVED["wet_area"], f"wet_area {f_}")
            results.append((f"wet_area_{f_}", a, ok, msg))
            p = o.get("perim", 0)
            ok2, msg2 = check_value(p, ARCH_OBSERVED["wet_perimeter"], f"wet_perim {f_}")
            results.append((f"wet_perim_{f_}", p, ok2, msg2))

        elif t == "dry":
            d = o.get("dry", 0)
            ok, msg = check_value(d, ARCH_OBSERVED["dry_area"], f"dry_area {f_}")
            results.append((f"dry_area_{f_}", d, ok, msg))

        elif t == "walls20":
            length = o.get("len", 0)
            ok, msg = check_value(length, ARCH_OBSERVED["walls_20_len"], f"walls20 {f_}")
            results.append((f"walls20_{f_}", length, ok, msg))

        elif t == "walls10":
            length = o.get("len", 0)
            ok, msg = check_value(length, ARCH_OBSERVED["walls_10_len"], f"walls10 {f_}")
            results.append((f"walls10_{f_}", length, ok, msg))

        elif t == "openings":
            da = o.get("door_area", 0)
            ok, msg = check_value(da, ARCH_OBSERVED["door_area"], f"door_area {f_}")
            results.append((f"door_area_{f_}", da, ok, msg))
            wa = o.get("win_area", 0)
            ok2, msg2 = check_value(wa, ARCH_OBSERVED["win_area"], f"win_area {f_}")
            results.append((f"win_area_{f_}", wa, ok2, msg2))

    return results


def run_all_checks(phase, items_dict=None, observed=None, floor_heights=None):
    """
    Run all sanity checks for a phase and print report.
    phase: "sub", "super", or "arch"
    Returns (pass_count, fail_count, failures_list).
    """
    results = []

    if phase == "sub" and items_dict:
        results = check_sub_items(items_dict)
    elif phase == "super":
        if items_dict:
            results += check_super_items(items_dict)
        if observed and floor_heights:
            results += check_super_observed(observed, floor_heights)
    elif phase == "arch":
        if items_dict:
            results += check_arch_items(items_dict)
        if observed:
            results += check_arch_observed(observed)

    passes = [(r[0], r[1]) for r in results if r[2]]
    fails  = [(r[0], r[1], r[3]) for r in results if not r[2]]

    print(f"\n── SANITY CHECK ({phase.upper()}) ────────────────────────────")
    if fails:
        print(f"  {len(passes)} passed, {len(fails)} FAILED:")
        for iid, val, msg in fails:
            print(msg)
    else:
        print(f"  ALL {len(passes)} checks passed ✓")
    print(f"──────────────────────────────────────────────────────\n")

    return len(passes), len(fails), fails
