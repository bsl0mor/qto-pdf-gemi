import fitz, re

base = r"B:\work\projects estimation\projects\downloads\2 villas\TENDER FOR MOHAMMED ALI JAFFAR ALBLOOSHI\TENDER FOR MOHAMMED ALI JAFFAR ALBLOOSHI"
str_path = base + r"\ST\mohammed_ali_jaffar_hassan_alblooshi1769074679863.pdf"
doc = fitz.open(str_path)

for i in range(doc.page_count):
    t = doc[i].get_text()
    # Search for structural keywords more aggressively
    kws = re.findall(r'(FOUNDATION\s*(?:PLAN|LAYOUT|DETAIL)|FOOTING\s*(?:SCHEDULE|PLAN|LAYOUT|DETAIL)|COLUMN\s*(?:SCHEDULE|LAYOUT|PLAN|DETAIL)|TIE\s*BEAM|TBEAM|T\.?BEAM|GROUND\s*BEAM|SLAB\s*(?:PLAN|LAYOUT|ON\s*GRADE)|BEAM\s*(?:SCHEDULE|LAYOUT|PLAN)|ROOF\s*(?:SLAB|PLAN)|STAIR|SECTION|LINTEL|PARAPET|SOG|ASSESSMENT|GENERAL\s*NOTE|STRUCTURAL\s*DETAIL|RAFT)', t, re.IGNORECASE)
    
    # Find footing types (F1, F2, etc.)
    footing_types = re.findall(r'\b(F\d+[A-Z]?)\b', t)
    # Column types (C1, C2, etc.)
    column_types = re.findall(r'\b(C\d+[A-Z]?)\b', t)
    # TB types
    tb_types = re.findall(r'\b(TB\d+|GB\d+)\b', t, re.IGNORECASE)
    # Beam types
    beam_types = re.findall(r'\b(B\d+[A-Z]?)\b', t)
    # Slab types
    slab_types = re.findall(r'\b(SL\d+|S\d+)\b', t)
    
    # Drawing title block
    title_block = re.findall(r'(?:PROPOSED|DWG\.?\s*TITLE|TITLE)\s*[:.]?\s*([^\n]{5,80})', t, re.IGNORECASE)
    
    print(f"\n{'='*50}")
    print(f"STR pg{i} (S-{i+1:02d}):")
    if kws:
        print(f"  Keywords: {list(set(kws))}")
    if footing_types:
        print(f"  Footing types: {list(set(footing_types))[:10]}")
    if column_types:
        print(f"  Column types: {list(set(column_types))[:10]}")
    if tb_types:
        print(f"  TieBeam types: {list(set(tb_types))[:10]}")
    if beam_types:
        print(f"  Beam types: {list(set(beam_types))[:10]}")
    if slab_types:
        print(f"  Slab types: {list(set(slab_types))[:10]}")
    if title_block:
        for tb in title_block[:3]:
            print(f"  Title: {tb.strip()[:80]}")
    
    # Show dimensions if they exist
    dims = re.findall(r'(\d{3,5}\s*[xX×]\s*\d{3,5}|\d+\.?\d*\s*[mM]\s*[xX×]\s*\d+\.?\d*\s*[mM])', t)
    if dims:
        print(f"  Dimensions: {dims[:10]}")

doc.close()
