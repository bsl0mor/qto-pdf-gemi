import fitz, re

base = r"B:\work\projects estimation\projects\downloads\2 villas\TENDER FOR MOHAMMED ALI JAFFAR ALBLOOSHI\TENDER FOR MOHAMMED ALI JAFFAR ALBLOOSHI"

def extract_titles(path, label):
    doc = fitz.open(path)
    print(f"\n{'='*60}")
    print(f"{label}: {doc.page_count} pages")
    print(f"{'='*60}")
    for i in range(doc.page_count):
        t = doc[i].get_text()
        # Look for DWG NO patterns
        dwg_match = re.findall(r'(?:DWG\.?\s*NO\.?|SHEET\s*NO\.?)\s*[:.]?\s*(\S+)', t, re.IGNORECASE)
        # Look for drawing titles - common patterns
        title_match = re.findall(r'((?:FOUNDATION|COLUMN|TIE.?BEAM|BEAM|SLAB|ROOF|STAIR|SECTION|DETAIL|SCHEDULE|ELEVATION|FLOOR\s*PLAN|GROUND\s*FLOOR|FIRST\s*FLOOR|SECOND\s*FLOOR|PARAPET|LINTEL|FOOTING|RAFT|PILE|GF|FF|SOG|DOOR|WINDOW|D\s*&\s*W|D&W|FINISHING|CEILING|COMPOUND|FENCE|LAYOUT|SITE|PLAN)[^\n]{0,50})', t, re.IGNORECASE)
        # Look for S-XX or AR-XX patterns
        code_match = re.findall(r'[SA]R?-\d+', t)
        
        print(f"\n  pg{i}:")
        if dwg_match:
            print(f"    DWG NOs: {dwg_match[:5]}")
        if code_match:
            print(f"    Codes: {list(set(code_match))[:10]}")
        if title_match:
            for tm in title_match[:8]:
                print(f"    Title: {tm.strip()}")
        
        # Also show first 400 chars for context
        preview = t[:400].replace('\n', ' | ')
        print(f"    Preview: {preview[:200]}")
    doc.close()

extract_titles(base + r"\ST\mohammed_ali_jaffar_hassan_alblooshi1769074679863.pdf", "STR")
extract_titles(base + r"\ARCH\arch1767502231079.pdf", "ARCH")
extract_titles(base + r"\ARCH\elevation_color1767502267431.pdf", "ELEVATION")
