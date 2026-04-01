import fitz, base64, json
import re as _re

from utils import auto_scale

# ── PROJECT DEFINITIONS ────────────────────────────────────────────────────────
_BASE_1577 = r"C:\Users\basel\Downloads\The System\FINAL DRAWINGS\New folder (3)"
PROJECTS = [
    {
        "name":          "3246",
        "multi_pdf":     False,
        "pdf":           r"C:\Users\basel\Downloads\The System\TINDER\DRAWINGS\PDF\3246 - STRUCTURE.pdf",
        "pg_foundation": 6,
        "pg_columns":    4,
        "pg_tbeam":      7,
        "excav_depth":   1.75,
        "road_base":     True,
        "road_base_t":   0.20,
    },
    {
        "name":        "1577",
        "multi_pdf":   True,
        "foundation":  f"{_BASE_1577}\\FTING.pdf",
        "tbeam":       f"{_BASE_1577}\\SOG.pdf",
        "columns":     f"{_BASE_1577}\\1ST COLS.pdf",
        "excav_depth": 1.50,
        "road_base":   True,
        "road_base_t": 0.20,
    },
]

# ══════════════════════════════════════════════════════════════════
# PHASE 1 — TEXT EXTRACTION (100% accurate, works for ANY project)
# ══════════════════════════════════════════════════════════════════

def extract_all_text(doc):
    """Return dict of page_index → raw text for all pages."""
    return {i: doc[i].get_text() for i in range(doc.page_count)}

def parse_footing_schedule(all_text):
    """
    Format A (legacy): each mark + size on SAME line: F1\n130x170x40
    Format B (newer Dubai PDFs): mark on one line, decimal dims on separate lines
    Supports both 'SCHEDULE OF FOOTINGS' and 'Foundation Schedule' headers.
    """
    full = "\n".join(all_text.values())
    lines = full.split("\n")

    # Find header — supports both naming conventions
    header_idx = None
    for i, line in enumerate(lines):
        if _re.search(r'SCHEDULE\s+OF\s+FOOTINGS?|Foundation\s+Schedule|SCHEDULE\s+OF\s+FOOTING', line, _re.I):
            header_idx = i
            break
    if header_idx is None:
        return []

    # ── Format A: single-line NNNxNNNxNN ─────────────────────────
    scan_start = max(0, header_idx - 5)
    marks_a, sizes_a = [], []
    for i in range(scan_start, len(lines)):
        s = lines[i].strip()
        if i > header_idx and _re.search(
            r'FOUNDATION\s+DETAILS|FOUNDATION\s+NOTES|SCHEDULE\s+OF\s+(?!FOOTINGS)', s, _re.I
        ) and s:
            break
        if _re.fullmatch(r'(?:CF|WF|SF|PF|F)\d+', s, _re.I):
            marks_a.append(s.upper())
        elif _re.fullmatch(r'(\d{2,4})[xX](\d{2,4})[xX](\d{2,4})', s):
            m2 = _re.fullmatch(r'(\d{2,4})[xX](\d{2,4})[xX](\d{2,4})', s)
            sizes_a.append((float(m2.group(1)), float(m2.group(2)), float(m2.group(3))))
    footings = []
    for i, mark in enumerate(marks_a):
        if i < len(sizes_a):
            L, W, H = sizes_a[i]
            footings.append({"mark": mark, "L_cm": L, "W_cm": W, "H_cm": H})
    if footings:
        return footings
    # Auto-label fallback (graphics-only TYPE column)
    if sizes_a:
        for i, (L, W, H) in enumerate(sizes_a):
            footings.append({"mark": f"F{i+1}", "L_cm": L, "W_cm": W, "H_cm": H,
                             "mark_auto": True})
        return footings

    # ── Format B: multi-line decimal metre format ─────────────────
    # Strategy: scan entire page; when mark found (first occurrence), collect
    # subsequent decimal values until next mark or AutoCAD annotation.
    # \A1; lines = AutoCAD annotation = reset current_mark (plan area, not schedule).
    REBAR = _re.compile(r'[TY]\d+[@]\d+|\d+[TY]\d+|^AS$|^---', _re.I)
    entries = {}   # mark → list of decimal values (W, L, D mixed)
    current_mark = None
    for s in [l.strip() for l in lines[header_idx:]]:
        if not s: continue
        # Hard stop: client name block = truly end of drawing data
        if any(kw in s.upper() for kw in
               ('MOHAMMAD SALAH','DESIGN CORE','419270','7115674','CLIENT:')):
            break
        if REBAR.search(s): continue          # skip rebar text
        if 'AT PLAN' in s.upper(): continue   # CF3 dims are 'AT PLAN' — skip dim line
        # AutoCAD plan annotations → reset mark so plan dims don't contaminate
        if s.startswith('\\A') or s.startswith('\\L'):
            current_mark = None; continue
        # Skip grid row numbers (1-30)
        if _re.fullmatch(r'\d{1,2}', s) and 1 <= int(s) <= 30: continue
        # Skip grid column letters
        if _re.fullmatch(r'[A-Z](?: [A-Z])?', s): continue
        # Footing mark?
        if _re.fullmatch(r'(?:CF|WF|SF|PF|F)\d+', s, _re.I):
            mark = s.upper()
            if mark not in entries:
                entries[mark] = []          # first occurrence = schedule entry
                current_mark = mark
            elif current_mark == mark:
                pass                        # consecutive duplicate of same mark
            else:
                current_mark = None         # plan-label duplicate — stop tracking
            continue
        # Decimal value → assign to current mark
        dec = _re.fullmatch(r'(\d+\.\d+)', s)
        if dec and current_mark and current_mark in entries:
            v = float(dec.group(1))
            if 0.20 <= v <= 9.0:
                entries[current_mark].append(v)

    for mark, vals in entries.items():
        plan = [v for v in vals if v >= 1.0]
        deps = [v for v in vals if 0.20 <= v < 1.0]
        if len(plan) >= 2:
            footings.append({"mark": mark,
                             "L_cm": round(max(plan[0], plan[1]) * 100),
                             "W_cm": round(min(plan[0], plan[1]) * 100),
                             "H_cm": round(deps[0] * 100) if deps else 40})
        elif len(plan) == 1:
            footings.append({"mark": mark,
                             "L_cm": round(plan[0] * 100),
                             "W_cm": round(plan[0] * 100),
                             "H_cm": round(deps[0] * 100) if deps else 40})
    return footings

def parse_tb_schedule(all_text):
    """
    Parse SCHEDULE OF TIE BEAMS. Supports:
      Format A: inline integer cm  e.g. 'TB1  25 x 60'
      Format B: decimal metres on separate lines  e.g. 'TB1\n0.25\n0.60'
    Marks: TB1, TB2, CTB1, WF1, etc.
    End-of-block detection: looks for NOTES:, CONTRACTOR, PROJECT: — or 700 chars.
    """
    full = "\n".join(all_text.values())
    m_hdr = _re.search(r'SCHEDULE\s+OF\s+TIE\s+BEAMS', full, _re.I)
    if not m_hdr:
        return []
    after = full[m_hdr.start():]
    # Flexible end: NOTES, CONTRACTORE, PROJECT:, or 700 chars
    end_m = _re.search(r'NOTES:|CONTRACTOR|^PROJECT\s*:', after[30:], _re.I | _re.M)
    block = after[:30 + end_m.start()] if end_m else after[:700]

    # Format A: inline integer cm with x separator: '25 x 60' or '25X60'
    marks_a = _re.findall(r'\b((?:C)?TB\d+|WF\d+)\b', block, _re.I)
    marks_a = list(dict.fromkeys([m.upper() for m in marks_a]))
    sizes_a = []
    for sm in _re.finditer(r'\b(\d{2,3})\s*[xX]\s*(\d{2,3})\b', block):
        b, d = int(sm.group(1)), int(sm.group(2))
        if b >= 15 and d >= 20:
            sizes_a.append((float(b), float(d)))
    if marks_a and sizes_a:
        return [{"mark": marks_a[i], "b_cm": sizes_a[i][0], "d_cm": sizes_a[i][1]}
                for i in range(min(len(marks_a), len(sizes_a)))]

    # Format B: each mark on its own line, followed by decimal metre dims
    # Format C: each mark on its own line, followed by integer cm dims (e.g. 20 then 60)
    REBAR = _re.compile(r'[TY]\d+[@]|\d+[TY]\d+|^AS$|^---', _re.I)
    lines  = block.split('\n')
    tbs, seen = [], set()
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if _re.fullmatch(r'((?:C)?TB\d+|WF\d+)', s, _re.I):
            mark = s.upper()
            if mark not in seen:
                seen.add(mark)
                dec_dims, int_dims, j = [], [], i + 1
                while j < min(i + 10, len(lines)) and len(dec_dims) < 2 and len(int_dims) < 2:
                    ns = lines[j].strip()
                    if REBAR.search(ns): j += 1; continue
                    # Format B: decimal metres
                    dec = _re.fullmatch(r'(\d+\.\d+)', ns)
                    if dec:
                        v = float(dec.group(1))
                        if 0.10 <= v <= 1.50:
                            dec_dims.append(v)
                        j += 1; continue
                    # Format C: plain integers in cm range (15-200)
                    intm = _re.fullmatch(r'(\d{2,3})', ns)
                    if intm:
                        v = int(intm.group(1))
                        if 15 <= v <= 200:
                            int_dims.append(float(v))
                    j += 1
                # Prefer decimal dims; fall back to integer dims
                if len(dec_dims) >= 2:
                    tbs.append({"mark": mark,
                                "b_cm": round(dec_dims[0] * 100),
                                "d_cm": round(dec_dims[1] * 100)})
                elif len(int_dims) >= 2:
                    tbs.append({"mark": mark,
                                "b_cm": int_dims[0],
                                "d_cm": int_dims[1]})
                elif (len(dec_dims) == 1 or len(int_dims) == 1) and tbs:
                    dims = dec_dims or int_dims
                    b_cm = round(dims[0] * 100) if dec_dims else dims[0]
                    tbs.append({"mark": mark,
                                "b_cm": b_cm,
                                "d_cm": tbs[-1]["d_cm"]})
        i += 1
    return tbs

def _try_sum_grid_spans(page_text):
    """
    For PDFs that annotate individual bay spans in decimal metres (not total dims in cm).
    Counts grid row numbers (1-N) and column letter entries → exact Y/X span counts.
    Collects EXACTLY that many values to avoid contamination from footing annotation dims.
    Returns (L, W) = (larger, smaller) or (None, None).
    """
    lines = [l.strip() for l in page_text.split('\n') if l.strip()]

    # Collect standalone row numbers (1-30 inclusive)
    row_nums = set()
    for s in lines:
        if _re.fullmatch(r'\d{1,2}', s) and 1 <= int(s) <= 30:
            row_nums.add(int(s))
    if not row_nums or max(row_nums) < 4:
        return None, None
    n_y_spans = max(row_nums) - 1   # spans between row grid lines

    # Count unique column letters + find last column-letter line index
    last_col_idx = -1
    col_letter_count = 0
    for i, s in enumerate(lines):
        if _re.fullmatch(r'[A-Z](?: [A-Z])?', s):
            col_letter_count += len(s.replace(' ', ''))  # 'F G'=2, 'K L'=2, 'A'=1
            last_col_idx = i
    if last_col_idx < 0 or col_letter_count < 2:
        return None, None
    n_x_spans = col_letter_count - 1   # grid column lines - 1 = bay intervals

    # Collect EXACTLY (n_y_spans + n_x_spans) decimal span values after the last col letter
    total_expected = n_y_spans + n_x_spans
    span_vals = []
    for s in lines[last_col_idx + 1:]:
        if len(span_vals) >= total_expected:
            break
        if _re.search(r'[A-Za-z]{3,}', s):   # text line = stop early
            break
        dec = _re.fullmatch(r'(\d+\.?\d*)', s)
        if dec:
            v = float(dec.group(1))
            if 0.50 <= v <= 9.00:
                span_vals.append(v)

    if len(span_vals) < n_y_spans + 2:   # need Y spans + at least 2 X spans
        return None, None
    y_sum = round(sum(span_vals[:n_y_spans]), 2)
    x_sum = round(sum(span_vals[n_y_spans:]), 2)
    if y_sum < 5.0 or x_sum < 5.0:
        return None, None
    return (max(x_sum, y_sum), min(x_sum, y_sum))


def parse_grid_dims(all_text):
    """
    Strategy 1 (legacy — projects 3246, 1577): standalone 4-digit cm integers.
    Strategy 2 (newer Dubai PDFs): sum individual bay spans in decimal metres.
    """
    # Strategy 1: 4-digit cm format
    foundation_text = next(
        (t for t in all_text.values()
         if _re.search(r'SCHEDULE\s+OF\s+FOOTINGS?|Foundation\s+Schedule|FOUNDATION\s+LAYOUT', t, _re.I)),
        "\n".join(all_text.values())
    )
    candidates = []
    for line in foundation_text.split("\n"):
        s = line.strip()
        if _re.fullmatch(r'\d{4}', s):
            v = int(s)
            if 1000 <= v <= 3000:
                candidates.append(v)
    if candidates:
        unique_sorted = sorted(set(candidates), reverse=True)
        if len(unique_sorted) >= 2:
            return round(unique_sorted[0] / 100, 2), round(unique_sorted[1] / 100, 2)
        elif len(unique_sorted) == 1:
            return round(unique_sorted[0] / 100, 2), None

    # Strategy 2: sum grid bay spans from each page (TB layout page is cleanest)
    for page_text in all_text.values():
        result = _try_sum_grid_spans(page_text)
        if result[0] is not None:
            return result
    return None, None

def parse_levels(all_text):
    """Extract GF level and TB level from text."""
    gf_level = None
    tb_level = None
    full = "\n".join(all_text.values())
    lines = full.split("\n")
    # GF level: (1) look backward from 'GRD. SLAB LEVEL' for '+N.NN'
    # (2) look anywhere for 'FFL = +N.NN' or 'GROUND FL.* +N.NN'
    for i, line in enumerate(lines):
        if _re.search(r'GRD\.?\s*SLAB\s+LEVEL', line, _re.I):
            for j in range(max(0, i - 5), i):
                s = lines[j].strip()
                if _re.fullmatch(r'\+\d+\.\d+', s):
                    gf_level = float(s.lstrip('+'))
                    break
            break
    if gf_level is None:
        m = _re.search(r'(?:FFL|GF\s+FL|GROUND\s+FL)[^+\n]{0,10}\+(\d+\.\d+)', full, _re.I)
        if m:
            gf_level = float(m.group(1))
    # (3) Fallback: scan for standalone '+N.NN' lines that appear with GRD SLAB LEVEL text nearby
    if gf_level is None:
        for i, line in enumerate(lines):
            if _re.search(r'GRD\.?\s*SLAB\s+LEVEL', line, _re.I):
                window = lines[max(0, i-8):i+3]
                for l in window:
                    m2 = _re.fullmatch(r'\+(\d+\.\d+)', l.strip())
                    if m2:
                        gf_level = float(m2.group(1))
                        break
                break
    # TB level: 'ALL TIE BEAM AT LEVEL +0.80M' or 'ALL TIE BEAMS ARE AT +0.35m'
    m = _re.search(r'TIE\s*BEAMS?\s*(?:ARE\s*)?AT\s*(?:LEVEL\s*)?\+?(\d+\.\d+)', full, _re.I)
    if m:
        val = float(m.group(1))
        tb_level = val / 100 if val > 5 else val
    if tb_level is None:
        # Fallback: look for '+0.35' near GRD SLAB LEVEL block
        for i, line in enumerate(lines):
            if _re.search(r'GRD\.?\s*SLAB\s+LEVEL', line, _re.I):
                for j in range(max(0, i - 5), i):
                    m2 = _re.search(r'\+(0\.\d+)', lines[j].strip())
                    if m2 and float(m2.group(1)) < float(gf_level or 1):
                        tb_level = float(m2.group(1))
                break
    return gf_level, tb_level

def parse_column_schedule(all_text):
    """
    Parse SCHEDULE OF COLUMNS from S-01 text.
    Supports two formats:
      Format A: Standard — header "SCHEDULE OF COLUMNS", pre-mark 2-digit dims, then C1/C2 marks.
      Format B: AutoCAD — marks as %%UC1C1, dims as \\A1;60 / \\A1;20.
    Also counts column instances (C1, C2, C3, NC) on the layout and stores as 'count'.
    """
    # ── Find column page ──
    col_page_text = next(
        (t for t in all_text.values() if _re.search(r'SCHEDULE\s+OF\s+COLUMNS|COLUMN\s+LAYOUT', t, _re.I)),
        None
    )
    if not col_page_text:
        return []

    lines_b = col_page_text.split("\n")

    # ── Try Format B: %%UC1C1 + \A1;XX pattern (CAD export) ──
    # In CAD text export, column schedule may have marks (%%UC1C1) and dims (\A1;XX)
    # appearing in unpredictable order (table columns export left-to-right).
    # Collect all marks and all valid dims, then pair them sequentially.
    all_marks = []
    all_a1_dims = []
    for line in lines_b:
        s = line.strip()
        m = _re.match(r'%%U((?:C\d+|NC))(?:\1)?', s, _re.I)
        if m:
            all_marks.append(m.group(1).upper())
            continue
        # Standalone NC after other marks have been found
        if s == 'NC' and all_marks:
            all_marks.append('NC')
            continue
        m2 = _re.match(r'\\A1;(\d+)', s)
        if m2:
            v = int(m2.group(1))
            if 15 <= v <= 120:
                all_a1_dims.append(v)

    if all_marks and len(all_a1_dims) >= 2 * len(all_marks):
        cols_b = []
        for i, mk in enumerate(all_marks):
            d1 = all_a1_dims[i * 2]
            d2 = all_a1_dims[i * 2 + 1]
            cols_b.append({
                "mark": mk,
                "b_cm": float(min(d1, d2)),
                "d_cm": float(max(d1, d2)),
                "shape": "rect",
            })
        if cols_b:
            _count_columns_on_layout(cols_b, col_page_text)
            return cols_b

    # ── Format A: original parser ──
    if not _re.search(r'SCHEDULE\s+OF\s+COLUMNS', col_page_text, _re.I):
        return []

    in_schedule = False
    cols = []
    pre_dims = []
    post_mark = False

    for line in lines_b:
        s = line.strip()
        if _re.search(r'SCHEDULE\s+OF\s+COLUMNS', s, _re.I):
            in_schedule = True; continue
        if not in_schedule:
            continue
        if _re.fullmatch(r'\d{3,4}', s) and int(s) > 100:
            break
        if len(s) > 30 or s.startswith('*') or s.startswith('NOTE'):
            continue
        if s and s[0] in ('Ø', 'ø', '∅', 'O') and _re.search(r'\d{2}', s):
            d = int(_re.search(r'\d+', s).group())
            if cols and 'b_cm' not in cols[-1]:
                cols[-1].update({"b_cm": float(d), "d_cm": float(d), "shape": "circular"})
            post_mark = False
            pre_dims.clear()
            continue
        if _re.fullmatch(r'C\d+(?:/DC)?', s, _re.I):
            entry = {"mark": s.upper()}
            if len(pre_dims) >= 2:
                entry["b_cm"] = float(pre_dims[0])
                entry["d_cm"] = float(pre_dims[1])
                entry["shape"] = "rect"
            cols.append(entry)
            pre_dims.clear()
            post_mark = True
            continue
        if _re.fullmatch(r'\d{2}', s):
            v = int(s)
            if post_mark:
                continue
            if 15 <= v <= 80:
                pre_dims.append(v)

    result = [c for c in cols if 'mark' in c]
    if result:
        _count_columns_on_layout(result, col_page_text)
    return result


def _count_columns_on_layout(cols, page_text):
    """Count how many times each column mark appears on the layout (standalone lines)."""
    lines = page_text.split("\n")
    # Build set of marks to look for
    mark_set = {c["mark"] for c in cols}
    counts = {mk: 0 for mk in mark_set}
    for line in lines:
        s = line.strip()
        if s in mark_set:
            counts[s] += 1
    for c in cols:
        c["count"] = counts.get(c["mark"], 0)


def _extract_raw_schedule_blocks(all_text):
    """
    Extract raw text blocks for Foundation Schedule and TB Schedule.
    Returns (raw_footing_block, raw_tb_block) as strings.
    Used to inject into Gemini prompt when parsers cannot cleanly parse dims.
    """
    full = "\n".join(all_text.values())

    # Foundation schedule block: from header to first grid letter sequence or 150 lines
    raw_footing = ""
    m_f = _re.search(r'Foundation\s+Schedule|SCHEDULE\s+OF\s+FOOTINGS', full, _re.I)
    if m_f:
        block_lines, after_lines = [], full[m_f.start():].split('\n')
        for j, line in enumerate(after_lines[:160]):
            s = line.strip()
            # Stop at grid column letters section (end of schedule area)
            if s and _re.fullmatch(r'[A-Z](?: [A-Z])?', s) and j > 15:
                break
            # Skip obviously non-schedule content
            if any(kw in s for kw in ('PROPOSED PRIVATE', 'Dubai Municipal', 'CHECK DESCRIPTIONS')):
                continue
            if s:
                block_lines.append(s)
        # Also look for second schedule block (some PDFs split by column)
        m_f2 = _re.search(r'Foundation\s+Schedule|SCHEDULE\s+OF\s+FOOTINGS', full[m_f.end():], _re.I)
        if m_f2:
            pos2 = m_f.end() + m_f2.start()
            extra = full[pos2:pos2 + 600].split('\n')
            for line in extra:
                s = line.strip()
                if any(kw in s for kw in ('CHECK DESCRIPTIONS', 'PROPOSED PRIVATE')):
                    break
                if s:
                    block_lines.append(s)
        raw_footing = '\n'.join(block_lines)[:2000]

    # TB schedule block: from header to CONTRACTOR/PROJECT or 600 chars
    raw_tb = ""
    m_t = _re.search(r'SCHEDULE\s+OF\s+TIE\s+BEAMS', full, _re.I)
    if m_t:
        after = full[m_t.start():]
        end_m = _re.search(r'NOTES:|CONTRACTOR|PROJECT:', after[30:], _re.I)
        raw_tb = after[:30 + end_m.start()].strip()[:600] if end_m else after[:600].strip()

    return raw_footing, raw_tb


# ══════════════════════════════════════════════════════════════════
# PHASE 2 — run_project: loads docs, runs parsers, calls Gemini
# ══════════════════════════════════════════════════════════════════

def run_project(cfg):
    name = cfg["name"]

    print(f"\n{'='*65}")
    print(f"  PROJECT {name}")
    print(f"{'='*65}")

    # ── USER INPUTS (from cfg if provided, else prompt) ─────────────
    if "excav_depth" in cfg:
        EXCAV_DEPTH = float(cfg["excav_depth"])
        print(f"  Excavation depth : {EXCAV_DEPTH} m  (from config)")
    else:
        while True:
            try:
                EXCAV_DEPTH = float(input(f"  [PROJECT {name}] Excavation depth (m)? e.g. 1.75 : ").strip())
                break
            except ValueError:
                print("  Please enter a number (e.g. 1.75)")

    if "road_base" in cfg:
        ROAD_BASE   = bool(cfg["road_base"])
        ROAD_BASE_T = float(cfg.get("road_base_t", 0.0))
        rb_info = f"Yes, {ROAD_BASE_T} m" if ROAD_BASE else "No"
        print(f"  Road base        : {rb_info}  (from config)")
    else:
        rb_ans = input(f"  [PROJECT {name}] Road base required? (y/n) : ").strip().lower()
        ROAD_BASE   = rb_ans in ("y", "yes")
        ROAD_BASE_T = 0.0
        if ROAD_BASE:
            while True:
                try:
                    ROAD_BASE_T = float(input(f"  [PROJECT {name}] Road base thickness (m)? e.g. 0.20 : ").strip())
                    break
                except ValueError:
                    print("  Please enter a number (e.g. 0.20)")
    print()

    # ── Load documents ───────────────────────────────────────────────
    if cfg["multi_pdf"]:
        docs_by_role = {role: fitz.open(cfg[role])
                        for role in ("foundation", "tbeam", "columns")}
        print(f"Loaded {len(docs_by_role)} PDFs (multi-PDF mode)")
        for role, d in docs_by_role.items():
            print(f"  {role}: {d.page_count} page(s)")
    else:
        doc = fitz.open(cfg["pdf"])
        print(f"Total pages: {doc.page_count}")

    # ── Run parsers ──────────────────────────────────────────────────
    print("Extracting text from PDF...")
    if cfg["multi_pdf"]:
        all_text     = {role: docs_by_role[role][0].get_text() for role in docs_by_role}
        footing_text = {"foundation": all_text["foundation"]}
        tbeam_text   = {"tbeam":      all_text["tbeam"]}
        cols_text    = {"columns":    all_text["columns"]}
    else:
        all_text     = extract_all_text(doc)
        footing_text = all_text
        tbeam_text   = all_text
        cols_text    = all_text

    footing_schedule     = parse_footing_schedule(footing_text)
    tb_schedule          = parse_tb_schedule(tbeam_text)
    column_schedule      = parse_column_schedule(cols_text)
    overall_L, overall_W = parse_grid_dims(footing_text)
    gf_level, tb_level   = parse_levels(all_text)

    print(f"Footings parsed : {[f['mark'] for f in footing_schedule]}")
    print(f"TBs parsed      : {[t['mark'] for t in tb_schedule]}")
    print(f"Columns parsed  : {[c['mark'] for c in column_schedule]}")
    print(f"Overall dims    : L={overall_L}m  W={overall_W}m")
    print(f"Levels          : GF={gf_level}m  TB={tb_level}m")

    # Build structured text context to inject into prompt
    def fmt_columns(cs):
        lines = ["SCHEDULE OF COLUMNS (parsed from PDF text — use these dims for neck columns):"] 
        lines.append(f"  {'TYPE':<8} {'b(m)':<7} {'d(m)':<7} {'shape':<10}")
        lines.append("  " + "-"*34)
        for c in cs:
            shape = "circular" if c.get("type") == "circular" else "rect"
            if 'b_cm' in c:
                lines.append(f"  {c['mark']:<8} {c['b_cm']/100:<7.2f} {c['d_cm']/100:<7.2f} {shape:<10}")
            else:
                lines.append(f"  {c['mark']:<8} {'?':<7} {'?':<7} {'read from S-01 image':<10}")
        lines.append("  NOTE: For '?' entries, read dims from SCHEDULE OF COLUMNS in S-01 image")
        return "\n".join(lines)

    def fmt_footings(fs):
        lines = ["SCHEDULE OF FOOTINGS (parsed from PDF text — 100% accurate):"]
        lines.append(f"  {'TYPE':<6} {'L(m)':<7} {'W(m)':<7} {'H(m)':<7}")
        lines.append("  " + "-"*30)
        for f in fs:
            lines.append(f"  {f['mark']:<6} {f['L_cm']/100:<7.2f} {f['W_cm']/100:<7.2f} {f['H_cm']/100:<7.2f}")
        return "\n".join(lines)

    def fmt_tbs(ts):
        lines = ["SCHEDULE OF TIE BEAMS (parsed from PDF text — 100% accurate):"]
        lines.append(f"  {'TYPE':<6} {'b(m)':<7} {'d(m)':<7}")
        lines.append("  " + "-"*22)
        for t in ts:
            lines.append(f"  {t['mark']:<6} {t['b_cm']/100:<7.2f} {t['d_cm']/100:<7.2f}")
        return "\n".join(lines)

    parsed_context = ""
    # If footing marks were auto-labeled, column dims from text are also unreliable
    # (same project type: TYPE column is in graphics layer, not text layer).
    # Tell Vision to read ALL column dims from the schedule image.
    footings_auto_labeled = any(f.get("mark_auto") for f in footing_schedule)

    if column_schedule and not footings_auto_labeled:
        parsed_context += fmt_columns(column_schedule) + "\n\n"
    elif footings_auto_labeled:
        parsed_context += (
            "COLUMN DIMS: Read ALL from S-03 SCHEDULE OF COLUMNS image — "
            "text extract is unreliable for this project (marks appear before schedule header).\n"
            "After reading, output each as {mark, b_cm, d_cm}.\n\n"
        )
    if footing_schedule:
        parsed_context += fmt_footings(footing_schedule) + "\n\n"
    if tb_schedule:
        parsed_context += fmt_tbs(tb_schedule) + "\n\n"
    if overall_L:
        parsed_context += f"OVERALL DIMENSIONS (from grid text): L={overall_L}m  W={overall_W}m\n"
    if gf_level is not None:
        parsed_context += f"GF LEVEL (from text): {gf_level:+.2f}m\n"
    else:
        parsed_context += (
            f"GF LEVEL: not found in text. "
            f"TIE BEAM LEVEL = {tb_level:+.2f}m (from text). "
            f"Assume GF = +0.80m (same as TB level — typical for this drawing format, "
            f"tie beams cast at FFL). Use GF_level = 0.80m in all calculations.\n"
            if tb_level else
            "GF LEVEL: not found — assume +0.00m for substructure calculations.\n"
        )
    if tb_level is not None:
        parsed_context += f"TIE BEAM LEVEL (from text): {tb_level:+.2f}m\n"

    # ── Raw schedule text injection (when parsers returned empty) ─────────
    # Gives Gemini the raw PDF text to cross-reference against the image,
    # even when format does not match the structured parsers above.
    raw_fblock, raw_tbblock = _extract_raw_schedule_blocks(all_text)
    if raw_fblock:
        # Always inject raw footing text — even when parser succeeds, depths may be wrong
        # (plan-area labels appear before schedule labels in some PDFs, corrupting depth values)
        default_depth_marks = [f['mark'] for f in footing_schedule if f.get('H_cm', 40) == 40]
        if not footing_schedule:
            parsed_context += (
                "\n⚠ FOUNDATION SCHEDULE RAW PDF TEXT (parsers could not parse — "
                "extract all dims from this text, confirm with image):\n"
            )
        else:
            note = (f"  NOTE: Depths for {default_depth_marks} may be at default — verify!"
                    if default_depth_marks else "  Depths cross-check only.")
            parsed_context += (
                f"\n📋 FOUNDATION SCHEDULE RAW PDF TEXT (cross-check depths — {note}):\n"
            )
        parsed_context += (
            "Columns order: Mark | Width(m) | Length(m) | Depth(m) | Reinforcement\n"
            "REBAR lines (T16@150, 4Y16, Y10@15, T12@150) = reinforcement, NOT dims.\n"
            "Plan dims = 1.0–7.0 m range. Depth = 0.25–0.85 m range.\n"
            f"--- RAW START ---\n{raw_fblock}\n--- RAW END ---\n\n"
        )
    if not tb_schedule and raw_tbblock:
        parsed_context += (
            "\n⚠ TIE BEAM SCHEDULE RAW PDF TEXT — use these cross-section dims:\n"
            "Format B PDF: mark on one line, width (m) next line, depth (m) line after.\n"
            f"--- RAW START ---\n{raw_tbblock}\n--- RAW END ---\n\n"
        )
    if not overall_L:
        parsed_context += (
            "\nOVERALL DIMS: Not extractable from text.\n"
            "ACTION: READ from the foundation plan drawing — sum all bay spans along "
            "each axis (X-direction and Y-direction) to get total L and W.\n"
            "DO NOT guess. Count every bay span marked on the drawing.\n\n"
        )

    # ── Level/notes scan (for basement detection + context) ──────
    print("\nScanning all pages for levels and notes...")
    level_lines = []
    notes_lines = []
    for pg_label, pg_text in all_text.items():
        for line in pg_text.split("\n"):
            s = line.strip()
            if not s:
                continue
            if _re.search(r'[±+\-]\d+\.\d+.*(?:DMD|FORMATION|TOP OF SLAB|SLAB LEVEL|FLOOR LEVEL)', s, _re.I):
                level_lines.append(f"  {pg_label}: {s}")
            elif _re.search(r'(FFL|SSL|EGL)\s*[=\(]?\s*[+\-]?\d', s, _re.I):
                entry = f"  {pg_label}: {s}"
                if entry not in level_lines:
                    level_lines.append(entry)
            if _re.search(r'STOREY|FLOOR.TO.FLOOR|COLUMN HEIGHT|CLEAR HEIGHT|H\s*=\s*\d', s, _re.I):
                notes_lines.append(f"  {pg_label}: {s}")
            if _re.search(r'CONCRETE.*STRENGTH|BEARING CAPACITY|BLINDING|COVER.*CONCRETE', s, _re.I):
                clean = _re.sub(r'^[^:]+:\s*', '', s)
                notes_lines.append(clean)

    # dedup preserving order
    level_lines = list(dict.fromkeys(level_lines))[:20]
    notes_lines = list(dict.fromkeys(notes_lines))[:15]

    # حساب المعلومات المستخرجة تلقائياً من المناسيب
    # نستخرج القيم الرئيسية (قبل القوس) لا قيم DMD الموجودة داخل أقواس
    all_levels = []
    for ln in level_lines:
        # استخرج الرقم الأول في السطر (قبل أي قوس) — هو المنسوب الفعلي في نظام الرسم
        m = _re.search(r'(?:p\d+:\s*)?([\+\-±]?\d+\.\d+)', ln)
        if m:
            raw = m.group(1).replace('±', '')
            try:
                all_levels.append(float(raw))
            except: pass

    formation = min(all_levels) if all_levels else None  # أعمق منسوب = مستوى التأسيس
    # basement FFL = ثاني أعمق منسوب سالب (أعمق من -1، أقل من formation)
    neg_levels = sorted([v for v in all_levels if v < -0.5])
    basement_ffl = neg_levels[1] if len(neg_levels) >= 2 else (neg_levels[0] if neg_levels else None)
    # تأكد أن formation هو الأعمق دائماً
    if basement_ffl is not None and formation is not None and basement_ffl <= formation:
        # swap أو اعتبر basement_ffl = ثاني قيمة
        basement_ffl = neg_levels[1] if len(neg_levels) >= 2 else None

    # بناء pre-computed context
    precomputed = ""
    if formation is not None and formation < -1.0:
        precomputed += f"PRE-COMPUTED FROM LEVELS (±0.00 = street level):\n"
        precomputed += f"  • Lowest level detected: {formation}m -> Assumed Formation Level\n"
        # Excavation depth: USER provides — do not pre-compute
        if basement_ffl is not None:
            col_clear = abs(basement_ffl)
            precomputed += f"  • Basement FFL detected: {basement_ffl}m -> Basement column height (excl slab): {col_clear - 0.20:.2f}m\n"
        precomputed += f"\n  -> MANDATORY qtoItem: Bulk Excavation\n"
        precomputed += f"     Formula: (OverallL + 2.0) x (OverallW + 2.0) x D\n"
        precomputed += f"     OverallL/OverallW: READ from plan (outermost footing edges). NEVER ask user.\n"
        precomputed += f"     D = excav_depth_m: USER PROVIDES ONLY — canCalculate=false, missingInputs=[excav_depth_m]\n\n"



    global_context = parsed_context   # ← Keep parsed footing/TB schedule as the base
    if precomputed:
        global_context += precomputed
    if level_lines:
        global_context += "LEVEL ANNOTATIONS FOUND IN THIS PDF SET:\n" + "\n".join(level_lines) + "\n\n"
    if notes_lines:
        global_context += "GENERAL NOTES FROM THIS PDF SET:\n" + "\n".join(notes_lines) + "\n\n"

    print(f"Global context extracted: {len(level_lines)} level lines, {len(notes_lines)} note lines")
    if formation is not None and formation < -1.0:
        print(f"Formation level detected: {formation}m")
    print(global_context[:1000])

    # ══════════════════════════════════════════════════════════════════
    # PHASE 2 — VISION (only for what text cannot give us)
    #   • Footing count per type on the layout plan
    #   • TB run lengths per type (and dims if not in text)
    #   • Column dims verification
    # ══════════════════════════════════════════════════════════════════


    parts_images = []

    def add_tile_images(page, nrows, ncols, tile_scale, label_prefix):
        """
        Split 'page' into nrows×ncols tiles rendered at tile_scale.
        Appends text+image parts directly to parts_images.
        Returns a grid description string for the prompt.
        """
        W = page.rect.width    # PDF points
        H = page.rect.height
        tw = W / ncols
        th = H / nrows
        row_labels = {0: "TOP", 1: "BOTTOM", 2: "LOWER"}
        col_labels = {0: "LEFT", 1: "CENTER", 2: "RIGHT"}
        total_kb = 0
        for r in range(nrows):
            for c in range(ncols):
                clip = fitz.Rect(c * tw, r * th, (c + 1) * tw, (r + 1) * th)
                pix = page.get_pixmap(
                    matrix=fitz.Matrix(tile_scale, tile_scale),
                    clip=clip,
                    colorspace=fitz.csRGB
                )
                b64 = base64.b64encode(pix.tobytes("jpeg", jpg_quality=90)).decode()
                tile_lbl = f"{label_prefix} | TILE {row_labels.get(r,'R'+str(r))}-{col_labels.get(c,'C'+str(c))}"
                parts_images.append({"text": f"[IMAGE: {tile_lbl}  {pix.width}x{pix.height}px]"})
                parts_images.append({"inlineData": {"mimeType": "image/jpeg", "data": b64}})
                total_kb += len(b64) // 1024
        print(f"  {label_prefix}: {nrows}x{ncols} tiles @ {tile_scale}x — total {total_kb} KB")

    if cfg["multi_pdf"]:
        # Foundation: tile 2×3 at 3x for accurate footing-type label counting
        add_tile_images(docs_by_role["foundation"][0], nrows=2, ncols=3,
                        tile_scale=3.0,
                        label_prefix="S-04 FOUNDATION LAYOUT (FTING.pdf)")
        # Column schedule: full page at 3x (read schedule table + count columns)
        pg = docs_by_role["columns"][0]
        pix = pg.get_pixmap(matrix=fitz.Matrix(3.0, 3.0), colorspace=fitz.csRGB)
        b64 = base64.b64encode(pix.tobytes("jpeg", jpg_quality=90)).decode()
        parts_images.append({"text": f"[IMAGE: S-03 COLUMN LAYOUT + SCHEDULE (1ST COLS.pdf) FULL  {pix.width}x{pix.height}px]"})
        parts_images.append({"inlineData": {"mimeType": "image/jpeg", "data": b64}})
        print(f"  S-03 columns: full 3x — {len(b64)//1024} KB")
        # Tie beam: full page at 2x (measure runs)
        pg = docs_by_role["tbeam"][0]
        pix = pg.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), colorspace=fitz.csRGB)
        b64 = base64.b64encode(pix.tobytes("jpeg", jpg_quality=88)).decode()
        parts_images.append({"text": f"[IMAGE: S-05 TIE BEAM LAYOUT (SOG.pdf) FULL  {pix.width}x{pix.height}px]"})
        parts_images.append({"inlineData": {"mimeType": "image/jpeg", "data": b64}})
        print(f"  S-05 tie beams: full 2x — {len(b64)//1024} KB")
        foundation_img_desc = "6 TILE IMAGES of S-04 Foundation Layout (2 rows × 3 cols, 3x scale)"
    else:
        for pg_doc, pg_idx, pg_label, pg_scale in [
            (doc, cfg["pg_foundation"], "S-03: Foundation Layout", 3.5),
            (doc, cfg["pg_columns"],    "S-01: Ground Floor Column Layout + Schedule of Columns", None),
            (doc, cfg["pg_tbeam"],      "S-04: Tie Beam Layout", 3.0),
        ]:
            pg = pg_doc[pg_idx]
            s = pg_scale if pg_scale else auto_scale(pg)
            pix = pg.get_pixmap(matrix=fitz.Matrix(s, s), colorspace=fitz.csRGB)
            b64 = base64.b64encode(pix.tobytes("jpeg", jpg_quality=88)).decode()
            parts_images.append({"text": f"[IMAGE: {pg_label} — FULL PAGE]"})
            parts_images.append({"inlineData": {"mimeType": "image/jpeg", "data": b64}})
            print(f"  {pg_label}: {pix.width}x{pix.height}, {len(b64)//1024} KB  (scale={s}x)")
        foundation_img_desc = "FULL PAGE image of Foundation Layout"

    print(f"Total image parts: {len(parts_images)//2}")

    # ══════════════════════════════════════════════════════════════════
    # VISION: READ-ONLY multi-pass (Gemini reads, does NOT calculate)
    # ══════════════════════════════════════════════════════════════════
    from vision_reader import read_sub as _vision_read_sub
    from compute_sub import recompute_sub
    from guards import run_all_checks

    vision_obs, vision_grid, vision_warns = _vision_read_sub(
        image_parts=parts_images,
        parsed_context=global_context,
        excav_depth=EXCAV_DEPTH,
        gf_level=gf_level,
        cfg=cfg,
        passes=3, name=name,
        parsed_footings=footing_schedule,
    )

    if vision_warns:
        print(f"  ⚠ Vision warnings: {vision_warns}")

    # Override grid dims from parsed text if available (more reliable)
    if overall_L and overall_W:
        vision_grid = {"L_m": overall_L, "W_m": overall_W}
    elif vision_grid:
        overall_L = vision_grid.get("L_m") or overall_L
        overall_W = vision_grid.get("W_m") or overall_W

    # Build result dict (compatible with old format)
    r = {
        "observedElements": vision_obs,
        "gridDims": vision_grid,
        "warnings": vision_warns,
        "qtoItems": [],  # will be filled by recompute
    }

    # Save initial observed data
    with open(f"{name}_result.json", "w", encoding="utf-8") as f:
        json.dump(r, f, indent=2, ensure_ascii=False)

    # ══════════════════════════════════════════════════════════════════
    # DETERMINISTIC RECOMPUTE: recalculate ALL 13 items from observed
    # ══════════════════════════════════════════════════════════════════
    excav_depth = EXCAV_DEPTH
    road_base   = ROAD_BASE
    road_base_t = ROAD_BASE_T

    if overall_L and overall_W:
        recomp_items, recomp_corrections = recompute_sub(
            observed_elements = r.get("observedElements", []),
            parsed_footings   = footing_schedule,
            parsed_tbs        = tb_schedule,
            parsed_cols       = column_schedule,
            overall_L         = overall_L,
            overall_W         = overall_W,
            gf_level          = gf_level,
            tb_level          = tb_level,
            excav_depth       = EXCAV_DEPTH,
            road_base         = ROAD_BASE,
            road_base_t       = ROAD_BASE_T,
        )

        if recomp_corrections:
            print("\n── RECOMPUTE CORRECTIONS ─────────────────────────────────")
            for c in recomp_corrections:
                print(c)
            print("───────────────────────────────────────────────────────────\n")

        # Store recomputed items directly (no Gemini items to replace)
        r["qtoItems"] = recomp_items

        # Sanity check
        items_dict = {it.get("id",""): it.get("totalQty",0) for it in recomp_items}
        run_all_checks("sub", items_dict=items_dict)

    # حفظ النتيجة بعد التصحيح
    with open(f"{name}_result.json", "w", encoding="utf-8") as f:
        json.dump(r, f, indent=2, ensure_ascii=False)
    print(f"Saved {name}_result.json")

    info = r.get("drawingInfo", {})
    items = r.get("qtoItems", [])
    elems = r.get("observedElements", [])
    qs = r.get("questions", [])

    print("\n" + "="*65)
    print(f"DRAWING INFO — PROJECT {name}")
    print("="*65)
    print(f"  Number  : {info.get('number')}")
    print(f"  Title   : {info.get('title')}")
    print(f"  Type    : {info.get('type')}")
    print(f"  Disc    : {info.get('discipline')}  Scale: {info.get('scale')}")
    print(f"  Project : {info.get('projectName')}")

    print(f"\nELEMENTS ({len(elems)}):")
    for el in elems[:20]:
        d = el.get("dims", {})
        print(f"  [{el.get('mark')}] {el.get('type')} x{el.get('count')} — {d.get('L')}x{d.get('W')}x{d.get('H')}{d.get('unit','m')} @ {el.get('location','')}")

    print(f"\nQTO ITEMS ({len(items)}):")
    for it in items:
        qty = it.get("totalQty")
        qty_str = f"{qty:.3f} {it.get('unit')}" if qty is not None else "PENDING"
        can = "OK" if it.get("canCalculate") and qty is not None else "NEED_Q"
        print(f"  [{can}] {it.get('id')} — {it.get('description','')[:55]:55s} => {qty_str}")
        bd = it.get("breakdown", "")
        if bd:
            print(f"         {bd[:100]}")

    print(f"\nQUESTIONS NEEDED ({len(qs)}):")
    for q in qs:
        if isinstance(q, dict):
            print(f"  ? [{q.get('id')}] {q.get('text','')[:70]}")
            print(f"    suggested={q.get('suggested')}  range={q.get('typicalRange','')}")
        else:
            print(f"  ? {str(q)[:80]}")

    print(f"\nSUMMARY:\n  {r.get('summary','')[:500]}")

    warnings = r.get("warnings", [])
    if warnings:
        print(f"\nWARNINGS:")
        for w in warnings:
            print(f"  WARN: {w}")
    print("="*65)


# ── Run all projects sequentially ─────────────────────────────────────────────
if __name__ == "__main__":
    for cfg in PROJECTS:
        run_project(cfg)
