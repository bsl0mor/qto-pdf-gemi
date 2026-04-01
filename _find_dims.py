import fitz, re

base = r"B:\work\projects estimation\projects\downloads\2 villas\TENDER FOR MOHAMMED ALI JAFFAR ALBLOOSHI\TENDER FOR MOHAMMED ALI JAFFAR ALBLOOSHI"
str_path = base + r"\ST\mohammed_ali_jaffar_hassan_alblooshi1769074679863.pdf"
doc = fitz.open(str_path)

# Collect all 4-digit numbers from 1000-3000 across all pages
all_candidates = []
for i in range(doc.page_count):
    t = doc[i].get_text()
    for line in t.split("\n"):
        s = line.strip()
        if re.fullmatch(r'\d{4}', s):
            v = int(s)
            if 1000 <= v <= 3000:
                all_candidates.append((i, v))

print("All 4-digit numbers in 1000-3000 range (page, value):")
for pg, v in sorted(all_candidates, key=lambda x: -x[1])[:30]:
    print(f"  pg{pg}: {v}cm = {v/100:.2f}m")

doc.close()
