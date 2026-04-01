"""Quick test: run BELHAL arch only with the new focused vision."""
import os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

from utils import extract_super_heights
import arch as arch_mod

# BELHAL arch config (from run_batch.py)
BASE = r"B:\work\projects estimation\projects\unknown jobs\id\done\done payment"
cfg = {
    "name":        "BELHAL",
    "multi_pdf":   False,
    "arch_pdf":    BASE + r"\16 _Abdulla Ali Rashed Mohammad Belhal\DRAWINGS\arch.pdf",
    "pg_gf_plan":  2,
    "pg_ff_plan":  3,
    "pg_elev1":    6,
    "pg_elev2":    7,
    "pg_dw_sched": 11,
    "img_scale":   1.0,
}

# Load heights from super result
gf_h, ff_h, roof_area, parapet_h = extract_super_heights("BELHAL", HERE)
cfg["gf_height_m"]  = gf_h
cfg["ff_height_m"]  = ff_h
cfg["roof_slab_m2"] = roof_area
cfg["parapet_h"]    = parapet_h

print(f"Running BELHAL arch with: gf_h={gf_h} ff_h={ff_h} roof={roof_area} parapet={parapet_h}")
arch_mod.run_project(cfg)
