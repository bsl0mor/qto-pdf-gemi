import fitz, re

d = fitz.open(r"B:\work\projects estimation\projects\downloads\2 villas\TENDER FOR MOHAMMED ALI JAFFAR ALBLOOSHI\TENDER FOR MOHAMMED ALI JAFFAR ALBLOOSHI\ST\mohammed_ali_jaffar_hassan_alblooshi1769074679863.pdf")
t = d[3].get_text()
lines = t.split("\n")

marks_b = []
a1_dims = []
for line in lines:
    s = line.strip()
    m = re.match(r'%%U((?:C\d+|NC))\1', s, re.I)
    if m:
        marks_b.append(m.group(1).upper())
        continue
    if s == 'NC' and marks_b:
        marks_b.append('NC')
        continue
    m2 = re.match(r'\\A1;(\d+)', s)
    if m2:
        a1_dims.append(int(m2.group(1)))

print("marks:", marks_b)
print("dims:", a1_dims)

# Also count column instances
for mk in ['C1', 'C2', 'C3', 'NC']:
    cnt = sum(1 for l in lines if l.strip() == mk)
    print(f"  {mk} count on layout: {cnt}")
