import fitz

base = r"B:\work\projects estimation\projects\downloads\2 villas\TENDER FOR MOHAMMED ALI JAFFAR ALBLOOSHI\TENDER FOR MOHAMMED ALI JAFFAR ALBLOOSHI"

# STR PDF
str_path = base + r"\ST\mohammed_ali_jaffar_hassan_alblooshi1769074679863.pdf"
doc = fitz.open(str_path)
print(f"STR: {doc.page_count} pages")
for i in range(doc.page_count):
    t = doc[i].get_text()[:300].replace("\n", " ")
    print(f"  pg{i}: {len(doc[i].get_text())} chars | {t[:150]}")
doc.close()

print()

# ARCH PDF
arch_path = base + r"\ARCH\arch1767502231079.pdf"
doc = fitz.open(arch_path)
print(f"ARCH: {doc.page_count} pages")
for i in range(doc.page_count):
    t = doc[i].get_text()[:300].replace("\n", " ")
    print(f"  pg{i}: {len(doc[i].get_text())} chars | {t[:150]}")
doc.close()

print()

# ELEVATION PDF
elev_path = base + r"\ARCH\elevation_color1767502267431.pdf"
doc = fitz.open(elev_path)
print(f"ELEVATION: {doc.page_count} pages")
for i in range(doc.page_count):
    t = doc[i].get_text()[:300].replace("\n", " ")
    print(f"  pg{i}: {len(doc[i].get_text())} chars | {t[:150]}")
doc.close()
