"""
run_batch.py — Batch runner for 5 projects (BELHAL, FATMA, SAIF, SULTAN, MANSOOR)
Bypasses interactive input — all configs hardcoded from PDF analysis.
"""

import os, sys, json, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

# ── Import modules ────────────────────────────────────────────────────────────
def load_module(filename, module_name):
    spec = importlib.util.spec_from_file_location(
        module_name, os.path.join(HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

print("Loading modules...")
sub_mod  = load_module("test2.py",  "sub_mod")
sup_mod  = load_module("super.py",  "sup_mod")
arch_mod = load_module("arch.py",   "arch_mod")
print("Modules loaded.\n")

from utils import extract_super_heights

# ── Base paths ────────────────────────────────────────────────────────────────
# Override by setting environment variables, or edit the strings below to match
# your local folder structure.  Use forward slashes or raw strings for Windows.
#
#   set QTO_BASE=C:\path\to\projects\folder
#   set QTO_BASE_2VILLAS=C:\path\to\2villas\folder
#
BASE         = os.environ.get(
    "QTO_BASE",
    os.path.join(HERE, "projects"),      # relative fallback — put PDFs here
)
BASE_2VILLAS = os.environ.get(
    "QTO_BASE_2VILLAS",
    os.path.join(HERE, "projects_2villas"),
)

# ══════════════════════════════════════════════════════════════════════════════
# PROJECT CONFIGS
# ══════════════════════════════════════════════════════════════════════════════

PROJECTS = [

    # ─── ALBLOOSHI ────────────────────────────────────────────────────────────
    # G+1 Villa, Tasees Consulting Engineers
    # STR: 12 pages  |  ARCH: 13 pages + elevation_color (1 page)
    # pg6=S-07 Foundation Layout (F1-F8)  pg3=S-04 Column+TieBeam  pg7=S-08 SOG+TieBeam
    # ARCH: pg1=GF Plan  pg2=FF Plan  pg4=Elevation1-2  pg5=Elevation3-4
    {
        "name": "ALBLOOSHI",
        "struct_pdf": BASE_2VILLAS + r"\ST\mohammed_ali_jaffar_hassan_alblooshi1769074679863.pdf",
        "arch_pdf":   BASE_2VILLAS + r"\ARCH\arch1767502231079.pdf",
        # STR pages (0-indexed)
        "pg_foundation": 6,   # pg7 — S-07 FOUNDATION LAYOUT (F1-F8)
        "pg_tbeam":      7,   # pg8 — S-08 SOG + TIEBEAM (TB1, TB2)
        "pg_columns":    3,   # pg4 — S-04 COLUMN LAYOUT + TIE BEAM
        "pg_gf_cols":    3,
        "pg_ff_cols":    4,   # pg5 — S-05 (same column set, next page)
        "pg_ff_slab":    8,   # pg9 — S-09 SLAB LAYOUT
        "pg_roof_slab":  9,   # pg10 — S-10 ROOF SLAB LAYOUT
        # ARCH pages (0-indexed)
        "pg_elevation":  6,   # arch pg7 — SECTION A-B (for floor heights)
        "pg_gf_plan":    1,   # arch pg2 — GROUND FLOOR PLAN AR-06
        "pg_ff_plan":    2,   # arch pg3 — FIRST FLOOR PLAN AR-06
        "pg_elev1":      4,   # arch pg5 — ELEVATION 1-2 AR-07
        "pg_elev2":      5,   # arch pg6 — ELEVATION 3-4 AR-07
        "pg_dw_sched":   7,   # arch pg8 — DOORS DETAILS
        # User inputs
        "excav_depth":  1.25,
        "road_base":    False,
        "road_base_t":  0.00,
        "parapet_type": "block",
        "img_scale":    1.0,
    },

    # ─── BELHAL ───────────────────────────────────────────────────────────────
    # G+1 Villa, Madinat Hind 4, Plot 9140161, Alnoor Engineering
    # STR: 15 pages (text-extractable)  |  ARCH: 14 pages
    {
        "name": "BELHAL",
        "struct_pdf": BASE + r"\16 _Abdulla Ali Rashed Mohammad Belhal\DRAWINGS\Full STR Drawings.pdf",
        "arch_pdf":   BASE + r"\16 _Abdulla Ali Rashed Mohammad Belhal\DRAWINGS\arch.pdf",
        # STR pages (0-indexed)
        "pg_foundation": 7,   # pg8 — FOUNDATIONS LAYOUT
        "pg_tbeam":      8,   # pg9 — TIE BEAMS LAYOUT
        "pg_columns":    5,   # pg6 — COLUMNS LAYOUT AT GROUND FLOOR
        "pg_gf_cols":    5,   # same as columns
        "pg_ff_cols":    6,   # pg7 — FF COLUMNS LAYOUT
        "pg_ff_slab":    9,   # pg10 — FF SLAB LAYOUT
        "pg_roof_slab": 10,   # pg11 — ROOF SLAB LAYOUT
        # ARCH pages (0-indexed)
        "pg_elevation":  8,   # arch pg9 — SECTIONS (for heights)
        "pg_gf_plan":    2,   # pg3 — GF FLOOR PLAN
        "pg_ff_plan":    3,   # pg4 — FF FLOOR PLAN
        "pg_elev1":      6,   # pg7 — ELEVATIONS 1 & 2
        "pg_elev2":      7,   # pg8 — ELEVATIONS 3 & 4
        "pg_dw_sched":  11,   # pg12 — DOORS & WINDOWS SCHEDULE
        # User inputs
        "excav_depth":  1.20,
        "road_base":    True,
        "road_base_t":  0.15,
        "parapet_type": "block",
        "img_scale":    1.0,
    },

    # ─── FATMA ────────────────────────────────────────────────────────────────
    # G+1 Villa, Plot 39.81m x 16.74m footprint
    # STR: 12 pages (text-extractable)  |  ARCH: 12 pages
    {
        "name": "FATMA",
        "struct_pdf": BASE + r"\Fatma\structure1698313636724.pdf",
        "arch_pdf":   BASE + r"\Fatma\architecture1698313266785.pdf",
        # STR pages (0-indexed)
        "pg_foundation": 9,   # pg10 — FOUNDATION LAYOUT
        "pg_tbeam":     10,   # pg11 — TIEBEAM LAYOUT
        "pg_columns":    3,   # pg4  — COLUMN LAYOUT
        "pg_gf_cols":    3,
        "pg_ff_cols":    4,   # pg5  — FF COLUMN LAYOUT
        "pg_ff_slab":    6,   # pg7  — FF SLAB
        "pg_roof_slab":  7,   # pg8  — ROOF SLAB
        # ARCH pages (0-indexed)
        "pg_elevation":  4,   # arch pg5 — shows FFL levels +0.45/+4.74/+9.08
        "pg_gf_plan":    1,   # pg2 — GF PLAN
        "pg_ff_plan":    2,   # pg3 — FF PLAN
        "pg_elev1":      4,   # pg5 — ELEVATIONS
        "pg_elev2":      6,   # pg7 — MORE ELEVATIONS
        "pg_dw_sched":   8,   # pg9 — DOORS & WINDOWS
        # User inputs
        "excav_depth":  1.20,
        "road_base":    True,
        "road_base_t":  0.15,
        "parapet_type": "block",
        "img_scale":    1.0,
    },

    # ─── SAIF ─────────────────────────────────────────────────────────────────
    # G+1+R + Car Parking + Compound Wall, Al Awir First, Plot 71115090, MX Concept
    # STR: 10 pages  |  ARCH: merged from 10 individual PDFs → SAIF_ARCH_combined.pdf
    # Excav: 2.50m (clearly stated in STR)
    {
        "name": "SAIF",
        "struct_pdf": BASE + r"\SAIF ISMAIL ABDULLA  AHLI (1)\STR\2024_01_10_str_saif1707468594010.pdf",
        "arch_pdf":   os.path.join(HERE, "SAIF_ARCH_combined.pdf"),
        # STR pages (0-indexed)
        "pg_foundation": 3,   # pg4  — FOUNDATION LAYOUT + Schedule
        "pg_tbeam":      4,   # pg5  — GROUND BEAMS LAYOUT (tiebeam)
        "pg_columns":    2,   # pg3  — GF COLUMN LAYOUT (C1/C2/C3/C4/NC1)
        "pg_gf_cols":    2,   # same
        "pg_ff_cols":    2,   # same page — columns designed for G+1 only
        "pg_ff_slab":    5,   # pg6  — FIRST SLAB LAYOUT
        "pg_roof_slab":  6,   # pg7  — ROOF SLAB LAYOUT
        # ARCH pages (0-indexed in merged PDF)
        "pg_elevation":  5,   # merged pg6 — SECTIONS (for heights)
        "pg_gf_plan":    0,   # merged pg1 — GF FLOOR PLAN
        "pg_ff_plan":    1,   # merged pg2 — FF FLOOR PLAN
        "pg_elev1":      3,   # merged pg4 — ELEVATIONS E1 & E2
        "pg_elev2":      4,   # merged pg5 — ELEVATIONS E3 & E4
        "pg_dw_sched":   6,   # merged pg7 — DOORS DETAILS
        # User inputs
        "excav_depth":  2.50,
        "road_base":    True,
        "road_base_t":  0.15,
        "parapet_type": "block",
        "img_scale":    1.0,
    },

    # ─── SULTAN ───────────────────────────────────────────────────────────────
    # G+1+R + Compound Wall + Service Block + Guard Room + Car Parking Shade
    # Umm Suqeim Second, Plot 3621343, MX Concept (DXB-180)
    # STR: 13 pages (image-based)  |  ARCH: 33 pages (image-based)
    {
        "name": "SULTAN",
        "struct_pdf": BASE + r"\SULTAN NASSER ALSUWAIDI\Str\Str.pdf",
        "arch_pdf":   BASE + r"\SULTAN NASSER ALSUWAIDI\Arch\Arch.pdf",
        # STR pages (0-indexed) — confirmed from thumbnails
        "pg_foundation": 1,   # pg2  — FOOTING LAYOUT + SCHEDULE OF FOOTINGS
        "pg_tbeam":      2,   # pg3  — FOOTING LAYOUT (details + TIE BEAM SCHEDULE)
        "pg_columns":    0,   # pg1  — COLUMNS LAYOUT
        "pg_gf_cols":    0,
        "pg_ff_cols":    0,   # same columns page (all floors)
        "pg_ff_slab":    3,   # pg4  — FIRST FLOOR SLAB LAYOUT
        "pg_roof_slab":  4,   # pg5  — ROOF SLAB LAYOUT
        # ARCH pages (0-indexed) — confirmed from thumbnails
        "pg_elevation":  7,   # pg8  — SECTIONS (Section B-B, Section A-A)
        "pg_gf_plan":    2,   # pg3  — GF FLOOR PLAN
        "pg_ff_plan":    3,   # pg4  — FF FLOOR PLAN
        "pg_elev1":      5,   # pg6  — ELEVATIONS E1 & E2
        "pg_elev2":      6,   # pg7  — ELEVATIONS E3 & E4
        "pg_dw_sched":  31,   # pg32 — ALUMINUM WINDOWS DETAILS
        # User inputs
        "excav_depth":  1.00,
        "road_base":    True,
        "road_base_t":  0.15,
        "parapet_type": "block",
        "img_scale":    1.0,
    },

    # ─── MANSOOR ──────────────────────────────────────────────────────────────
    # G+1+R Villa, Al Khwaneej Second, Plot 2827500, Muhammad Yaseen Razvi
    # Footprint: 15.50m x 15.60m, Parapet 1.20m
    # STR: 17 pages (text-extractable)  |  ARCH: 42 pages (text-extractable)
    {
        "name": "MANSOOR",
        "struct_pdf": BASE + r"\VILLA\2827500 - G+1 MANSOOR VILLA_STR DRAWINGS.pdf",
        "arch_pdf":   BASE + r"\VILLA\2827500 - G+1 MANSOOR VILLA GENERAL + ARCHITECTURAL.pdf",
        # STR pages (0-indexed)
        "pg_foundation": 7,   # pg8  — LAYOUT OF FOUNDATION
        "pg_tbeam":     11,   # pg12 — TIE BEAM (TIE BEAM REFER SCHEDULE)
        "pg_columns":    5,   # pg6  — COLUMN LAYOUT FOUNDATION TO ROOF FLOOR
        "pg_gf_cols":    5,
        "pg_ff_cols":    5,   # same page (columns foundation to roof)
        "pg_ff_slab":    8,   # pg9  — FF SLAB LAYOUT
        "pg_roof_slab":  9,   # pg10 — ROOF SLAB LAYOUT
        # ARCH pages (0-indexed)
        "pg_elevation":  4,   # pg5  — SECTION showing +0.60 GF, +4.60 FF, +8.60 Roof
        "pg_gf_plan":    9,   # pg10 — GF FLOOR PLAN
        "pg_ff_plan":   10,   # pg11 — FF FLOOR PLAN
        "pg_elev1":     14,   # pg15 — ELEVATION 1
        "pg_elev2":     15,   # pg16 — ELEVATION 2
        "pg_dw_sched":  29,   # pg30 — DOORS & WINDOWS
        # User inputs
        "excav_depth":  1.50,
        "road_base":    True,
        "road_base_t":  0.15,
        "parapet_type": "block",
        "img_scale":    1.0,
    },
]


# ══════════════════════════════════════════════════════════════════════════════
# extract_super_heights imported from utils.py
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
# BUILD CFG TUPLES FROM FLAT CONFIG
# ══════════════════════════════════════════════════════════════════════════════

def build_cfgs(p):
    """Convert flat project dict → (sub_cfg, sup_cfg, arch_cfg) tuple."""

    sub_cfg = {
        "name":          p["name"],
        "multi_pdf":     False,
        "pdf":           p["struct_pdf"],
        "pg_foundation": p["pg_foundation"],
        "pg_tbeam":      p["pg_tbeam"],
        "pg_columns":    p["pg_columns"],
        "excav_depth":   p["excav_depth"],
        "road_base":     p["road_base"],
        "road_base_t":   p["road_base_t"],
    }

    sup_cfg = {
        "name":         p["name"],
        "multi_pdf":    False,
        "struct_pdf":   p["struct_pdf"],
        "arch_pdf":     p["arch_pdf"],
        "pg_gf_cols":   p["pg_gf_cols"],
        "pg_ff_cols":   p["pg_ff_cols"],
        "pg_ff_slab":   p["pg_ff_slab"],
        "pg_roof_slab": p["pg_roof_slab"],
        "pg_elevation": p["pg_elevation"],
        "parapet_type": p.get("parapet_type", "block"),
    }

    arch_cfg = {
        "name":        p["name"],
        "multi_pdf":   False,
        "arch_pdf":    p["arch_pdf"],
        "pg_gf_plan":  p["pg_gf_plan"],
        "pg_ff_plan":  p["pg_ff_plan"],
        "pg_elev1":    p["pg_elev1"],
        "pg_elev2":    p["pg_elev2"],
        "pg_dw_sched": p["pg_dw_sched"],
        "img_scale":   p.get("img_scale", 1.0),
    }

    return sub_cfg, sup_cfg, arch_cfg


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    import sys

    # Allow running specific project(s): py run_batch.py BELHAL FATMA
    if len(sys.argv) > 1:
        names = [n.upper() for n in sys.argv[1:]]
        projects = [p for p in PROJECTS if p["name"] in names]
        if not projects:
            print(f"⚠ No matching projects for: {names}")
            print(f"  Available: {[p['name'] for p in PROJECTS]}")
            return
    else:
        projects = PROJECTS

    project_names = [p["name"] for p in projects]
    print("=" * 65)
    print(f"  QTO BATCH — {len(projects)} projects: {', '.join(project_names)}")
    print("=" * 65)

    for p in projects:
        name = p["name"]
        sub_cfg, sup_cfg, arch_cfg = build_cfgs(p)

        print(f"\n{'═'*65}")
        print(f"  RUNNING — {name}")
        print(f"{'═'*65}")

        # PHASE 1 — SUBSTRUCTURE
        print(f"\n[1/3] SUBSTRUCTURE — {name}")
        sub_mod.run_project(sub_cfg)

        # PHASE 2 — SUPERSTRUCTURE
        print(f"\n[2/3] SUPERSTRUCTURE — {name}")
        sup_mod.run_project(sup_cfg)

        # PHASE 3 — ARCH FINISHES
        print(f"\n[3/3] ARCHITECTURAL FINISHES — {name}")
        gf_h, ff_h, roof_area, parapet_h = extract_super_heights(name, HERE)
        arch_cfg["gf_height_m"]  = gf_h
        arch_cfg["ff_height_m"]  = ff_h
        arch_cfg["roof_slab_m2"] = roof_area
        arch_cfg["parapet_h"]    = parapet_h
        arch_mod.run_project(arch_cfg)

        print(f"\n  ✓ {name} COMPLETE")

    # ── EXPORT ────────────────────────────────────────────────────────────────
    from export_boq import write_batch_boq
    out_path = os.path.join(HERE, "BOQ_Batch.xlsx")
    print(f"\n{'═'*65}")
    print("  EXPORTING TO EXCEL")
    print(f"{'═'*65}")
    write_batch_boq(project_names, out_path)

    import subprocess
    subprocess.Popen(["start", out_path], shell=True)
    print(f"\nDone — {len(projects)} projects. BOQ_Batch.xlsx opened.")


if __name__ == "__main__":
    main()
