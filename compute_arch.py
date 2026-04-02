"""
compute_arch.py
───────────────
Deterministic calculation for ALL 31 architectural items.
Takes observed measurements + D&W schedule and computes every item.
NO vision or LLM involvement — pure math.
"""

import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def compute_arch_items(observed, dw, gf_h, ff_h, roof_area, parapet_h=1.20):
    """
    Compute all 31 architectural QTO items from observed data.

    Parameters
    ----------
    observed : list[dict]
        Observed data. Each: {t, f, perim/area/len/...}
    dw : list[dict]
        D&W schedule. Each: {id, cat, w, h, n, a}
    gf_h, ff_h : float
        Floor heights in metres.
    roof_area : float
        Roof slab area in m².
    parapet_h : float
        Parapet height in metres.

    Returns
    -------
    items : list[dict]  — 31 items: {id, u, q, bd}
    """
    def get(t, fl):
        for o in observed:
            if o.get("t") == t and str(o.get("f","")).upper() == fl.upper():
                return o
        return {}

    gf_ext  = get("ext_walls", "GF");  ff_ext  = get("ext_walls", "FF")
    gf_wet  = get("wet",       "GF");  ff_wet  = get("wet",       "FF")
    gf_dry  = get("dry",       "GF");  ff_dry  = get("dry",       "FF")
    gf_bal  = get("balcony",   "GF");  ff_bal  = get("balcony",   "FF")
    gf_w20  = get("walls20",   "GF");  ff_w20  = get("walls20",   "FF")
    gf_w10  = get("walls10",   "GF");  ff_w10  = get("walls10",   "FF")
    gf_op   = get("openings",  "GF");  ff_op   = get("openings",  "FF")

    gf_ext_p  = gf_ext.get("perim", 0);   ff_ext_p  = ff_ext.get("perim", 0)
    gf_wet_a  = gf_wet.get("area",  0);   ff_wet_a  = ff_wet.get("area",  0)
    gf_wet_p  = gf_wet.get("perim", 0);   ff_wet_p  = ff_wet.get("perim", 0)
    gf_dry_a  = gf_dry.get("dry",   0);   ff_dry_a  = ff_dry.get("dry",   0)
    gf_dry_p  = gf_dry.get("perim", 0);   ff_dry_p  = ff_dry.get("perim", 0)
    gf_bal_a  = gf_bal.get("area",  0);   ff_bal_a  = ff_bal.get("area",  0)
    gf_l20    = gf_w20.get("len",   0);   ff_l20    = ff_w20.get("len",   0)
    gf_l10    = gf_w10.get("len",   0);   ff_l10    = ff_w10.get("len",   0)
    gf_win_a  = gf_op.get("win_area",  0);ff_win_a  = ff_op.get("win_area",  0)
    gf_door_w = gf_op.get("door_w",    0);ff_door_w = ff_op.get("door_w",    0)
    gf_door_a = gf_op.get("door_area", 0);ff_door_a = ff_op.get("door_area", 0)
    # Prefer split values; fall back to total so old result files still work.
    gf_door_a_ext = gf_op.get("door_area_ext", gf_door_a)
    ff_door_a_ext = ff_op.get("door_area_ext", ff_door_a)
    gf_door_a_int = gf_op.get("door_area_int", gf_door_a)
    ff_door_a_int = ff_op.get("door_area_int", ff_door_a)

    ext_h  = round(gf_h + ff_h + parapet_h, 3)
    combo  = round(roof_area * 1.2, 3)
    balcony_total = round(gf_bal_a + ff_bal_a, 3)

    doors_count = sum(
        (e.get("n") or 0) for e in dw
        if str(e.get("cat","")).lower() in ("door","d")
    )
    if doors_count == 0:
        doors_count = len([e for e in dw if str(e.get("cat","")).lower() in ("door","d")])
    windows_area = round(sum(
        (e.get("a") or 0) for e in dw
        if str(e.get("cat","")).lower() in ("win","window","w")
    ), 3)
    if windows_area == 0:
        windows_area = round(gf_win_a + ff_win_a, 3)

    def r(v): return round(max(v, 0), 3)  # clamp negatives to 0

    # GF — external block: subtract only external door openings from external wall area.
    # Internal block walls: subtract only internal door openings.
    block_20_ext_gf = r(gf_ext_p * gf_h - gf_win_a - gf_door_a_ext)
    block_20_int_gf = r(gf_l20   * gf_h - 0.4 * gf_door_a_int)
    block_10_int_gf = r(gf_l10   * gf_h - 0.4 * gf_door_a_int)
    plaster_int_gf  = r((gf_l20 + gf_l10) * gf_h * 2 + gf_ext_p * gf_h
                        - gf_door_a_int * 2 - gf_door_a_ext * 1 - gf_win_a)
    flooring_dry_gf = r(gf_dry_a)
    flooring_wet_gf = r(gf_wet_a)
    skirting_gf     = r(gf_dry_p - 0.4 * gf_door_w)
    paint_gf        = r(skirting_gf * gf_h)
    tiles_wall_gf   = r(gf_wet_p * (gf_h - 0.5))

    # FF — same split as GF
    block_20_ext_ff = r(ff_ext_p * ff_h - ff_win_a - ff_door_a_ext)
    block_20_int_ff = r(ff_l20   * ff_h - 0.4 * ff_door_a_int)
    block_10_int_ff = r(ff_l10   * ff_h - 0.4 * ff_door_a_int)
    plaster_int_ff  = r((ff_l20 + ff_l10) * ff_h * 2 + ff_ext_p * ff_h
                        - ff_door_a_int * 2 - ff_door_a_ext * 1 - ff_win_a)
    flooring_dry_ff = r(ff_dry_a)
    flooring_wet_ff = r(ff_wet_a)
    skirting_ff     = r(ff_dry_p - 0.4 * ff_door_w)
    paint_ff        = r(skirting_ff * ff_h)
    tiles_wall_ff   = r(ff_wet_p * (ff_h - 0.5))

    # General
    finish_ext       = r(gf_ext_p * ext_h)
    marble_threshold = r(gf_door_w + ff_door_w)
    waterproofing    = flooring_wet_ff

    return [
        {"id":"block_20_ext_gf","u":"m2","q":block_20_ext_gf,
         "bd":f"{gf_ext_p}x{gf_h}-{gf_win_a}(win)-{gf_door_a_ext}(door_ext)"},
        {"id":"block_20_int_gf","u":"m2","q":block_20_int_gf,
         "bd":f"{gf_l20}x{gf_h}-0.4x{gf_door_a_int}(door_int)"},
        {"id":"block_10_int_gf","u":"m2","q":block_10_int_gf,
         "bd":f"{gf_l10}x{gf_h}-0.4x{gf_door_a_int}(door_int)"},
        {"id":"plaster_int_gf","u":"m2","q":plaster_int_gf,
         "bd":f"({gf_l20}+{gf_l10})x{gf_h}x2+{gf_ext_p}x{gf_h}-{gf_door_a_int}x2-{gf_door_a_ext}-{gf_win_a}"},
        {"id":"flooring_dry_gf","u":"m2","q":flooring_dry_gf,"bd":"dry area GF"},
        {"id":"flooring_wet_gf","u":"m2","q":flooring_wet_gf,"bd":"wet area GF"},
        {"id":"skirting_gf","u":"m","q":skirting_gf,
         "bd":f"{gf_dry_p}-0.4x{gf_door_w}"},
        {"id":"paint_gf","u":"m2","q":paint_gf,
         "bd":f"{skirting_gf}x{gf_h}"},
        {"id":"ceiling_dry_gf","u":"m2","q":flooring_dry_gf,"bd":"=flooring_dry_gf"},
        {"id":"ceiling_wet_gf","u":"m2","q":flooring_wet_gf,"bd":"=flooring_wet_gf"},
        {"id":"tiles_wall_gf","u":"m2","q":tiles_wall_gf,
         "bd":f"{gf_wet_p}x({gf_h}-0.5)"},

        {"id":"block_20_ext_ff","u":"m2","q":block_20_ext_ff,
         "bd":f"{ff_ext_p}x{ff_h}-{ff_win_a}(win)-{ff_door_a_ext}(door_ext)"},
        {"id":"block_20_int_ff","u":"m2","q":block_20_int_ff,
         "bd":f"{ff_l20}x{ff_h}-0.4x{ff_door_a_int}(door_int)"},
        {"id":"block_10_int_ff","u":"m2","q":block_10_int_ff,
         "bd":f"{ff_l10}x{ff_h}-0.4x{ff_door_a_int}(door_int)"},
        {"id":"plaster_int_ff","u":"m2","q":plaster_int_ff,
         "bd":f"({ff_l20}+{ff_l10})x{ff_h}x2+{ff_ext_p}x{ff_h}-{ff_door_a_int}x2-{ff_door_a_ext}-{ff_win_a}"},
        {"id":"flooring_dry_ff","u":"m2","q":flooring_dry_ff,"bd":"dry area FF"},
        {"id":"flooring_wet_ff","u":"m2","q":flooring_wet_ff,"bd":"wet area FF"},
        {"id":"skirting_ff","u":"m","q":skirting_ff,
         "bd":f"{ff_dry_p}-0.4x{ff_door_w}"},
        {"id":"paint_ff","u":"m2","q":paint_ff,
         "bd":f"{skirting_ff}x{ff_h}"},
        {"id":"ceiling_dry_ff","u":"m2","q":flooring_dry_ff,"bd":"=flooring_dry_ff"},
        {"id":"ceiling_wet_ff","u":"m2","q":flooring_wet_ff,"bd":"=flooring_wet_ff"},
        {"id":"tiles_wall_ff","u":"m2","q":tiles_wall_ff,
         "bd":f"{ff_wet_p}x({ff_h}-0.5)"},

        {"id":"finish_ext","u":"m2","q":finish_ext,
         "bd":f"{gf_ext_p}x{ext_h}"},
        {"id":"marble_threshold","u":"RM","q":marble_threshold,
         "bd":f"{gf_door_w}+{ff_door_w}"},
        {"id":"balcony_flooring","u":"m2","q":balcony_total,
         "bd":f"GF {gf_bal_a}+FF {ff_bal_a}"},
        {"id":"balcony_wp","u":"m2","q":balcony_total,
         "bd":"=balcony_flooring"},
        {"id":"waterproofing","u":"m2","q":waterproofing,
         "bd":"FF wet only"},
        {"id":"roof_waterproofing","u":"m2","q":r(roof_area),
         "bd":f"roof slab area={roof_area}"},
        {"id":"combo_roof","u":"m2","q":combo,
         "bd":f"{roof_area}x1.2={combo}"},
        {"id":"doors_schedule","u":"No.","q":doors_count,
         "bd":"total doors GF+FF"},
        {"id":"windows_schedule","u":"m2","q":windows_area,
         "bd":f"GF {gf_win_a}+FF {ff_win_a}"},
    ]


def compute(name, gf_h, ff_h, roof_area, parapet_h=1.20):
    """Load {name}_arch_result.json, extract observed+dw, compute, save back."""
    arch_path = os.path.join(HERE, f"{name}_arch_result.json")
    with open(arch_path, encoding="utf-8") as f:
        data = json.load(f)

    observed = data.get("observed", [])
    dw       = data.get("dw", [])

    items = compute_arch_items(observed, dw, gf_h, ff_h, roof_area, parapet_h)

    # ── Print ─────────────────────────────────────────────────────────────────
    ext_h = round(gf_h + ff_h + parapet_h, 3)
    print(f"\n{'='*65}")
    print(f"  ARCH COMPUTED QTO — PROJECT {name}  ({len(items)} items)")
    print(f"  GF h={gf_h}m | FF h={ff_h}m | Roof={roof_area}m² | ext_h={ext_h}m")
    print(f"{'='*65}")
    for it in items:
        print(f"  {it['id']:<22} => {it['q']:>10}  {it['u']}   {it['bd']}")
    print(f"{'='*65}")

    # ── Save ──────────────────────────────────────────────────────────────────
    data["items"] = items
    with open(arch_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  Saved → {name}_arch_result.json  (items added)\n")


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Load roof_slab_m2 from super result
    super_path = os.path.join(HERE, "NAQI_super_result.json")
    roof_area  = 410.55   # default
    if os.path.exists(super_path):
        with open(super_path, encoding="utf-8") as f:
            sup = json.load(f)
        for it in sup.get("qtoItems", []):
            if it.get("id") == "roof_slab":
                t  = it.get("totalQty", 0)
                th = 0.20   # assumed slab thickness
                roof_area = round(t / th, 3)
                break
        print(f"  Roof slab area from super: {roof_area} m²")

    compute(
        name      = "NAQI",
        gf_h      = 4.20,
        ff_h      = 4.20,
        roof_area = roof_area,
    )
