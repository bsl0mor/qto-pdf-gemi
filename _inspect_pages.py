import fitz

base = r"B:\work\projects estimation\projects\downloads\2 villas\TENDER FOR MOHAMMED ALI JAFFAR ALBLOOSHI\TENDER FOR MOHAMMED ALI JAFFAR ALBLOOSHI"
str_path = base + r"\ST\mohammed_ali_jaffar_hassan_alblooshi1769074679863.pdf"
doc = fitz.open(str_path)

# Show full text of pages 6, 7, 11 (foundation, SOG+TB, schedule)
for pg_idx in [6, 7, 11]:
    t = doc[pg_idx].get_text()
    print(f"\n{'='*60}")
    print(f"PAGE {pg_idx} (S-{pg_idx+1:02d}) — {len(t)} chars")
    print(f"{'='*60}")
    print(t[:3000])

doc.close()
