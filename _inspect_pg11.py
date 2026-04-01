import fitz

base = r"B:\work\projects estimation\projects\downloads\2 villas\TENDER FOR MOHAMMED ALI JAFFAR ALBLOOSHI\TENDER FOR MOHAMMED ALI JAFFAR ALBLOOSHI"
str_path = base + r"\ST\mohammed_ali_jaffar_hassan_alblooshi1769074679863.pdf"
doc = fitz.open(str_path)

# Show full text of page 11 (S-12)
t = doc[11].get_text()
print(f"PAGE 11 (S-12) — {len(t)} chars")
print(t)

doc.close()
