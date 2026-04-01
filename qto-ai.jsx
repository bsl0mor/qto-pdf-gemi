import { useState, useRef, useCallback } from "react";

// ════════════════════════════════════════════════════════════════════
// CONSTANTS & DEFAULT FORMULAS
// ════════════════════════════════════════════════════════════════════

const GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models";

const DEFAULT_FORMULAS = {
  excavation: {
    name: "Bulk Excavation",
    category: "CIVIL",
    formula: "Count × (L + 2×WS) × (W + 2×WS) × D",
    description: "WS=Working Space per side (m), L/W=Footing plan dims, D=Total excavation depth",
    defaults: { WS: 0.5 },
    unit: "m³"
  },
  pcc: {
    name: "PCC / Blinding Concrete",
    category: "STR",
    formula: "Count × (L + 2×WS) × (W + 2×WS) × t",
    description: "t=blinding thickness (typically 0.10m), WS=overhang each side (0.30m std)",
    defaults: { t: 0.10, WS: 0.30 },
    unit: "m³"
  },
  road_base: {
    name: "Road Base / Granular Fill",
    category: "CIVIL",
    formula: "Count × L × W × t",
    description: "t=road base/fill thickness as specified",
    defaults: { t: 0.30 },
    unit: "m³"
  },
  bitumen: {
    name: "Bituminous Waterproofing (Under Footing)",
    category: "STR",
    formula: "Count × (L + 2×OL) × (W + 2×OL)",
    description: "OL=Overlap each side (0.30m std), applied on PCC surface before footing pour",
    defaults: { OL: 0.30 },
    unit: "m²"
  },
  footing_concrete: {
    name: "Isolated Footing – Concrete",
    category: "STR",
    formula: "Count × L × W × H",
    description: "L/W/H from footing schedule or drawing annotations",
    defaults: {},
    unit: "m³"
  },
  footing_formwork: {
    name: "Isolated Footing – Formwork",
    category: "STR",
    formula: "Count × 2×(L+W)×H",
    description: "4 side faces only (top & bottom excluded)",
    defaults: {},
    unit: "m²"
  },
  footing_rebar: {
    name: "Reinforcement Steel",
    category: "STR",
    formula: "TotalBarLength × UnitWeight × (1 + WF)",
    description: "WF=Waste Factor (0.05=5%). UnitWeight kg/m: Ø8=0.395, Ø10=0.617, Ø12=0.888, Ø16=1.578, Ø20=2.466, Ø25=3.853",
    defaults: { WF: 0.05 },
    unit: "Ton"
  },
  column_concrete: {
    name: "Column – Concrete",
    category: "STR",
    formula: "Count × L × W × H",
    description: "H=clear height from top of slab to soffit of next slab",
    defaults: {},
    unit: "m³"
  },
  column_formwork: {
    name: "Column – Formwork",
    category: "STR",
    formula: "Count × 2×(L+W)×H",
    description: "All 4 faces, full clear height",
    defaults: {},
    unit: "m²"
  },
  beam_concrete: {
    name: "Beam – Concrete",
    category: "STR",
    formula: "Count × Length × B × (D−TS)",
    description: "D=total beam depth, TS=slab thickness (deducted to avoid double-count)",
    defaults: { TS: 0.20 },
    unit: "m³"
  },
  beam_formwork: {
    name: "Beam – Formwork (Sides + Soffit)",
    category: "STR",
    formula: "Count × Length × (2×(D−TS) + B)",
    description: "Both sides + soffit of beam stem",
    defaults: { TS: 0.20 },
    unit: "m²"
  },
  slab_concrete: {
    name: "Slab – Concrete",
    category: "STR",
    formula: "NetArea × t",
    description: "Net slab area (deduct openings >0.1m²) × slab thickness",
    defaults: { t: 0.20 },
    unit: "m³"
  },
  slab_formwork: {
    name: "Slab & Beam – Soffit Formwork",
    category: "STR",
    formula: "GrossSoffitArea × 1.0",
    description: "Gross soffit area including beam soffits, no deductions <0.5m²",
    defaults: {},
    unit: "m²"
  },
  blockwall: {
    name: "Masonry Block Wall",
    category: "ARCH",
    formula: "(TotalLength × H − OpeningsArea) × 1.0",
    description: "Deduct door/window openings >0.5m². H=clear wall height",
    defaults: {},
    unit: "m²"
  },
  plaster: {
    name: "Plaster / Render (per face)",
    category: "FINISHING",
    formula: "(TotalLength × H − OpeningsArea) × 1.0",
    description: "Calculate per face separately. Double for 2 faces. Deduct openings >0.5m²",
    defaults: {},
    unit: "m²"
  },
  tiling_floor: {
    name: "Floor Tiling",
    category: "FINISHING",
    formula: "Area × (1 + WF)",
    description: "WF=Waste factor: 0.10 (straight lay), 0.15 (diagonal/herringbone)",
    defaults: { WF: 0.10 },
    unit: "m²"
  },
  tiling_wall: {
    name: "Wall Tiling",
    category: "FINISHING",
    formula: "(Perimeter × H − OpeningsArea) × (1 + WF)",
    description: "WF=Waste factor 0.10–0.15. H=tiling height",
    defaults: { WF: 0.10 },
    unit: "m²"
  },
  painting: {
    name: "Painting",
    category: "FINISHING",
    formula: "Area × Coats",
    description: "Coats: 2 std (1 primer + 1 finish), 3 for feature walls",
    defaults: { Coats: 2 },
    unit: "m²"
  },
  waterproofing: {
    name: "Waterproofing Membrane (Wet Areas)",
    category: "FINISHING",
    formula: "Area × (1 + OL)",
    description: "OL=Overlap/wastage factor (0.15=15% std)",
    defaults: { OL: 0.15 },
    unit: "m²"
  },
  backfill: {
    name: "Backfill (Imported / Compacted)",
    category: "CIVIL",
    formula: "ExcavationVol − ConcreteVol × (1 + Swell)",
    description: "Swell factor 0.25 for compacted fill. = Excavation minus concrete volume",
    defaults: { Swell: 0.25 },
    unit: "m³"
  }
};

// ════════════════════════════════════════════════════════════════════
// SYSTEM PROMPT BUILDER
// ════════════════════════════════════════════════════════════════════

const buildSystemPrompt = (formulas) => {
  const fText = Object.entries(formulas).map(([k, f]) =>
    `  [${k}] ${f.name} → Formula: ${f.formula}  |  Unit: ${f.unit}\n    Notes: ${f.description}${Object.keys(f.defaults).length ? `  |  Defaults: ${JSON.stringify(f.defaults)}` : ""}`
  ).join("\n\n");

  return `You are a CHIEF QUANTITY SURVEYOR with 25+ years of experience on large-scale construction projects across the Middle East and internationally. You specialize in Quantity Take-Off (QTO) for structural, architectural, civil, and finishing works. You are precise, methodical, systematic, and never guess or fabricate critical dimensions.

═══════════════════════════════════════════════════════════════════════
DRAWING READING CAPABILITIES
═══════════════════════════════════════════════════════════════════════
You can read and interpret all construction drawing types:
• Foundation plans: isolated footings (F1, F2…), strip, raft, pile caps, grade beams
• Structural plans: column schedules, beam layouts, slab plans, shear walls, staircases
• Architectural plans: floor plans, elevations, sections, reflected ceiling plans
• Door/window schedules, finish schedules, room data sheets
• Detail drawings, typical sections, structural connection details
• Bar Bending Schedules (BBS), reinforcement plans
• Title blocks: drawing number, scale, revision, project name, date

From drawings you CAN extract directly:
→ Element counts (footings, columns, rooms from plan grids)
→ Plan dimensions (L × W from annotated dimensions)
→ Footing schedules / column schedules (mark, count, dims)
→ Grid spacings and span lengths
→ Floor areas from room dimensions
→ Wall lengths from plan perimeters
→ Bar sizes, spacing, marks from reinforcement drawings
→ Opening sizes from door/window schedules

═══════════════════════════════════════════════════════════════════════
MANDATORY QTO ITEMS BY DRAWING TYPE
═══════════════════════════════════════════════════════════════════════
Always extract ALL applicable items for the drawing type:

FOUNDATION PLAN:
  1. Bulk Excavation           → formulaKey: excavation      [NEEDS: depth, WS from user]
  2. Road Base / Granular Fill → formulaKey: road_base       [NEEDS: thickness from user]
  3. PCC / Blinding Concrete   → formulaKey: pcc             [CAN CALC if footing dims known]
  4. Bituminous Waterproofing  → formulaKey: bitumen         [CAN CALC from footing dims]
  5. Isolated Footing Concrete → formulaKey: footing_concrete [CAN CALC from schedule]
  6. Footing Formwork          → formulaKey: footing_formwork [CAN CALC from schedule]
  7. Footing Reinforcement     → formulaKey: footing_rebar   [NEEDS BBS or estimate]
  8. Backfill                  → formulaKey: backfill        [CALC after concrete known]

COLUMN SCHEDULE / PLAN:
  1. Column Concrete           → formulaKey: column_concrete [CAN CALC from schedule]
  2. Column Formwork           → formulaKey: column_formwork [CAN CALC from schedule]
  3. Column Reinforcement      → formulaKey: footing_rebar   [NEEDS: bar schedule]

BEAM / SLAB PLAN:
  1. Beam Concrete             → formulaKey: beam_concrete   [CAN CALC from dims]
  2. Beam Formwork             → formulaKey: beam_formwork   [CAN CALC from dims]
  3. Slab Concrete             → formulaKey: slab_concrete   [CAN CALC from area]
  4. Soffit Formwork           → formulaKey: slab_formwork   [CAN CALC from area]
  5. Slab/Beam Reinforcement   → formulaKey: footing_rebar   [NEEDS: rebar drawing]

ARCHITECTURAL FLOOR PLAN:
  1. Block Walls by type       → formulaKey: blockwall       [CAN CALC from plan]
  2. Plaster both faces        → formulaKey: plaster         [CAN CALC from walls]
  3. Door/Window counts        → No formula, count only
  4. Floor areas by room       → Input to tiling/painting

FINISH SCHEDULE / FLOOR PLAN WITH FINISHES:
  1. Floor Tiling by room      → formulaKey: tiling_floor    [CAN CALC from areas]
  2. Wall Tiling (wet areas)   → formulaKey: tiling_wall     [CAN CALC from dims]
  3. Painting                  → formulaKey: painting        [CAN CALC from areas]
  4. Waterproofing             → formulaKey: waterproofing   [CAN CALC from areas]
  5. False ceiling             → No formula, area only

═══════════════════════════════════════════════════════════════════════
USER-DEFINED FORMULAS — APPLY EXACTLY AS WRITTEN
═══════════════════════════════════════════════════════════════════════
${fText}

═══════════════════════════════════════════════════════════════════════
CALCULATION RULES
═══════════════════════════════════════════════════════════════════════
• Show: Formula name → Variable substitution → Result for every element
• Calculate each element mark (F1, F2, C1…) separately, then sum
• Use drawing schedule data first; use annotations if no schedule
• For rebar without BBS: estimate using standard ratios:
  - Isolated footings: 60–80 kg/m³ concrete
  - Columns: 150–200 kg/m³ concrete  
  - Beams: 120–160 kg/m³ concrete
  - Slabs: 80–100 kg/m³ concrete
• Round volumes/areas to 2 decimal places
• Flag estimates vs confirmed dimensions clearly

═══════════════════════════════════════════════════════════════════════
CRITICAL RULES
═══════════════════════════════════════════════════════════════════════
• Return ONLY valid JSON — absolutely no text or markdown outside JSON
• NEVER fabricate dimensions — only use clearly visible/readable values
• NEVER skip items that should be extracted from this drawing type
• If image is unclear, state what you CAN see and ask for confirmation
• Questions must be SPECIFIC and TARGETED — never ask what you can read
• Provide typical ranges as guidance for every question

═══════════════════════════════════════════════════════════════════════
JSON RESPONSE FORMAT
═══════════════════════════════════════════════════════════════════════
{
  "drawingInfo": {
    "type": "Foundation Plan",
    "title": "from title block",
    "number": "DWG-S-001",
    "scale": "1:100",
    "revision": "B",
    "discipline": "STR",
    "projectName": "from title block or Not visible"
  },
  "observedElements": [
    {
      "type": "Isolated Footing",
      "mark": "F1",
      "count": 6,
      "dims": { "L": 2.0, "W": 2.0, "H": 0.7, "unit": "m" },
      "location": "Grid A-C / 1-4",
      "notes": "Corner footings — from footing schedule"
    }
  ],
  "qtoItems": [
    {
      "id": "STR-001",
      "description": "Bulk Excavation for Isolated Footings — all types",
      "discipline": "CIVIL",
      "formulaKey": "excavation",
      "unit": "m³",
      "canCalculate": false,
      "elements": [],
      "totalQty": null,
      "breakdown": "Awaiting user input: excavation depth and working space",
      "missingInputs": ["excav_depth_m", "working_space_m"]
    },
    {
      "id": "STR-002",
      "description": "PCC Blinding Concrete 100mm thick under all Footings",
      "discipline": "STR",
      "formulaKey": "pcc",
      "unit": "m³",
      "canCalculate": true,
      "elements": [
        {
          "mark": "F1", "count": 6,
          "L": 2.0, "W": 2.0, "WS": 0.30, "t": 0.10,
          "subQty": 4.06,
          "calc": "6 × (2.0+0.60) × (2.0+0.60) × 0.10 = 6 × 2.60 × 2.60 × 0.10 = 4.06 m³"
        }
      ],
      "totalQty": 4.06,
      "breakdown": "F1×6: 4.06 m³  |  Total PCC = 4.06 m³",
      "missingInputs": []
    }
  ],
  "questions": [
    {
      "id": "excav_depth_m",
      "text": "What is the total excavation depth from existing ground level (EGL) to underside of PCC blinding?",
      "affectsItems": ["STR-001 Bulk Excavation"],
      "unit": "m",
      "typicalRange": "1.50 – 3.50m depending on foundation depth and soil conditions",
      "suggested": "2.0",
      "required": true
    }
  ],
  "summary": "Concise summary: drawing type found, elements identified, items calculated, what still needs input",
  "warnings": ["Any flags, unusual dimensions, or items needing QS review"]
}`;
};

const buildCalcPrompt = (analysis, answers, formulas) => {
  const fText = Object.entries(formulas)
    .map(([k, f]) => `  [${k}]: ${f.formula}  (${f.unit}) — defaults: ${JSON.stringify(f.defaults)}`)
    .join("\n");
  const aText = Object.entries(answers)
    .map(([id, val]) => `  ${id} = ${val}`)
    .join("\n");

  return `You are completing a QTO calculation. The drawing was already analyzed. The user has now answered all required questions.

PREVIOUS DRAWING ANALYSIS:
${JSON.stringify(analysis, null, 2)}

USER-PROVIDED VALUES:
${aText}

FORMULAS LIBRARY:
${fText}

TASK: Calculate every item that was pending (canCalculate: false, totalQty: null) using:
1. Observed element data already extracted from the drawing (counts, dimensions from observedElements)
2. The user-provided values listed above
3. The exact formulas provided

For each pending item:
→ Look up its formulaKey
→ Use the observedElements data for L, W, H, Count values
→ Insert user-provided values for depth, thickness, etc.
→ Calculate per element mark, then sum
→ Show full step-by-step substitution

Return ONLY valid JSON (no markdown, no text outside):
{
  "completedItems": [
    {
      "id": "STR-001",
      "description": "full description",
      "discipline": "CIVIL",
      "formulaKey": "excavation",
      "unit": "m³",
      "elements": [
        {
          "mark": "F1", "count": 6,
          "L": 2.0, "W": 2.0, "D": 2.0, "WS": 0.5,
          "subQty": 108.0,
          "calc": "6 × (2.0+1.0) × (2.0+1.0) × 2.0 = 6 × 3.0 × 3.0 × 2.0 = 108.00 m³"
        }
      ],
      "totalQty": 108.00,
      "breakdown": "F1×6: 108.00 m³  |  Grand Total = 108.00 m³"
    }
  ],
  "notes": "QS notes, any flags or recommendations"
}`;
};

// ════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ════════════════════════════════════════════════════════════════════

export default function QTOSystem() {
  const [apiKey, setApiKey] = useState("");
  const [geminiModel, setGeminiModel] = useState("gemini-2.5-pro");
  const [isReady, setIsReady] = useState(false);
  const [formulas, setFormulas] = useState(DEFAULT_FORMULAS);
  const [activeTab, setActiveTab] = useState("drawings");

  const [drawings, setDrawings] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingMsg, setProcessingMsg] = useState("");
  const [qtoTable, setQtoTable] = useState([]);
  const [editingKey, setEditingKey] = useState(null);

  const fileInputRef = useRef(null);
  const selectedDrawing = drawings.find(d => d.id === selectedId);

  // ── Gemini API ──────────────────────────────────────────────────
  const callGemini = async (parts) => {
    const url = `${GEMINI_BASE}/${geminiModel}:generateContent?key=${apiKey}`;
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contents: [{ role: "user", parts }],
        generationConfig: {
          temperature: 0.05,
          maxOutputTokens: 8192,
          responseMimeType: "application/json"
        }
      })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error?.message || `Gemini API error ${res.status}`);
    }
    const data = await res.json();
    const text = data.candidates?.[0]?.content?.parts?.[0]?.text || "{}";
    try {
      return JSON.parse(text.replace(/```json\n?|\n?```/g, "").trim());
    } catch {
      throw new Error("Gemini returned invalid JSON. Check drawing quality or try again.");
    }
  };

  // ── Helpers ─────────────────────────────────────────────────────
  const updateDrawing = useCallback((id, updates) => {
    setDrawings(prev => prev.map(d => d.id === id ? { ...d, ...updates } : d));
  }, []);

  const pushToTable = useCallback((drawing, items) => {
    const rows = items
      .filter(it => it.totalQty !== null && it.totalQty !== undefined)
      .map((it, i) => ({
        rowId: `${drawing.id}-${i}`,
        drawingId: drawing.id,
        drawingName: drawing.name,
        drawingType: drawing.analysis?.drawingInfo?.type || "",
        drawingNum: drawing.analysis?.drawingInfo?.number || "",
        discipline: it.discipline || "",
        itemCode: it.id,
        description: it.description,
        unit: it.unit,
        qty: it.totalQty,
        breakdown: it.breakdown || ""
      }));
    setQtoTable(prev => [...prev.filter(r => r.drawingId !== drawing.id), ...rows]);
  }, []);

  // ── Upload ───────────────────────────────────────────────────────
  const handleUpload = (e) => {
    Array.from(e.target.files).forEach(file => {
      const reader = new FileReader();
      reader.onload = ev => {
        const base64 = ev.target.result.split(",")[1];
        const drawing = {
          id: `d-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          name: file.name,
          mime: file.type,
          imageData: base64,
          imageUrl: ev.target.result,
          status: "uploaded",
          analysis: null,
          answers: {},
          results: [],
          error: null
        };
        setDrawings(prev => [...prev, drawing]);
        setSelectedId(drawing.id);
        setActiveTab("drawings");
      };
      reader.readAsDataURL(file);
    });
    e.target.value = "";
  };

  // ── Analyze ─────────────────────────────────────────────────────
  const analyzeDrawing = async (drawing) => {
    setIsProcessing(true);
    setProcessingMsg("Gemini 2.5 is reading the drawing…");
    updateDrawing(drawing.id, { status: "analyzing", error: null });
    try {
      const prompt = buildSystemPrompt(formulas);
      const result = await callGemini([
        { text: prompt + "\n\nAnalyze this construction drawing and return your JSON response:" },
        { inlineData: { mimeType: drawing.mime || "image/jpeg", data: drawing.imageData } }
      ]);
      const initAnswers = {};
      (result.questions || []).forEach(q => { initAnswers[q.id] = q.suggested || ""; });
      const hasQ = (result.questions || []).length > 0;
      updateDrawing(drawing.id, {
        status: hasQ ? "questions" : "complete",
        analysis: result,
        answers: initAnswers
      });
      if (!hasQ) {
        const allItems = result.qtoItems || [];
        updateDrawing(drawing.id, { results: allItems });
        pushToTable({ ...drawing, analysis: result }, allItems);
      }
    } catch (err) {
      updateDrawing(drawing.id, { status: "error", error: err.message });
    } finally {
      setIsProcessing(false);
      setProcessingMsg("");
    }
  };

  // ── Submit Answers ───────────────────────────────────────────────
  const submitAnswers = async (drawing) => {
    setIsProcessing(true);
    setProcessingMsg("Calculating quantities with your inputs…");
    updateDrawing(drawing.id, { status: "calculating" });
    try {
      const result = await callGemini([
        { text: buildCalcPrompt(drawing.analysis, drawing.answers, formulas) },
        { inlineData: { mimeType: drawing.mime || "image/jpeg", data: drawing.imageData } }
      ]);
      const readyItems = (drawing.analysis?.qtoItems || []).filter(i => i.canCalculate && i.totalQty !== null);
      const allItems = [...readyItems, ...(result.completedItems || [])];
      updateDrawing(drawing.id, { status: "complete", results: allItems });
      pushToTable({ ...drawing, analysis: drawing.analysis }, allItems);
    } catch (err) {
      updateDrawing(drawing.id, { status: "error", error: err.message });
    } finally {
      setIsProcessing(false);
      setProcessingMsg("");
    }
  };

  // ── Export CSV ───────────────────────────────────────────────────
  const exportCSV = () => {
    const hdrs = ["Drawing", "Dwg No.", "Type", "Discipline", "Item Code", "Description", "Unit", "Quantity"];
    const rows = qtoTable.map(r => [r.drawingName, r.drawingNum, r.drawingType, r.discipline, r.itemCode, r.description, r.unit, r.qty ?? ""]);
    const csv = [hdrs, ...rows].map(r => r.map(c => `"${String(c ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = "QTO_Export.csv";
    a.click();
  };

  // ── Config ───────────────────────────────────────────────────────
  const statusCfg = {
    uploaded:    { color: "#38bdf8", bg: "rgba(56,189,248,0.08)",  label: "READY" },
    analyzing:   { color: "#fbbf24", bg: "rgba(251,191,36,0.08)",  label: "ANALYZING…" },
    questions:   { color: "#fb923c", bg: "rgba(251,146,60,0.08)",  label: "NEEDS INPUT" },
    calculating: { color: "#fbbf24", bg: "rgba(251,191,36,0.08)",  label: "CALCULATING…" },
    complete:    { color: "#4ade80", bg: "rgba(74,222,128,0.08)",  label: "COMPLETE" },
    error:       { color: "#f87171", bg: "rgba(248,113,113,0.08)", label: "ERROR" }
  };

  const discColor = { STR: "#38bdf8", ARCH: "#a78bfa", FINISHING: "#fb923c", CIVIL: "#4ade80", MEP: "#f472b6" };

  const inp = {
    background: "rgba(0,0,0,0.4)", border: "1px solid rgba(100,116,139,0.3)",
    borderRadius: "2px", padding: "8px 12px", color: "#e2e8f0",
    fontSize: "12px", fontFamily: "'IBM Plex Mono', monospace", outline: "none",
    boxSizing: "border-box"
  };

  // ════════════════════════════════════════════════════════════════════
  // SETUP SCREEN
  // ════════════════════════════════════════════════════════════════════
  if (!isReady) {
    return (
      <div style={{
        minHeight: "100vh",
        background: "radial-gradient(ellipse at 20% 50%, #0f1e3a 0%, #080d1a 60%)",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontFamily: "'IBM Plex Mono', 'Courier New', monospace", padding: "24px"
      }}>
        <div style={{
          background: "rgba(12,20,40,0.97)", border: "1px solid rgba(251,191,36,0.25)",
          borderRadius: "4px", padding: "48px 52px", maxWidth: "540px", width: "100%",
          boxShadow: "0 0 80px rgba(251,191,36,0.06), 0 32px 64px rgba(0,0,0,0.6)"
        }}>
          {/* Brand */}
          <div style={{ marginBottom: "40px" }}>
            <div style={{ fontSize: "9px", letterSpacing: "5px", color: "#fbbf24", marginBottom: "10px", opacity: 0.8 }}>
              POWERED BY GEMINI 2.5
            </div>
            <div style={{ fontSize: "36px", fontWeight: 900, color: "#f1f5f9", letterSpacing: "-2px", lineHeight: 1 }}>
              QTO<span style={{ color: "#fbbf24" }}>.AI</span>
            </div>
            <div style={{ fontSize: "12px", color: "#475569", marginTop: "12px", lineHeight: 1.7 }}>
              Quantity Take-Off System<br />
              STR · ARCH · FINISHING · CIVIL
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "22px" }}>
            <div>
              <label style={{ fontSize: "9px", letterSpacing: "3px", color: "#fbbf24", display: "block", marginBottom: "8px" }}>
                GEMINI API KEY <span style={{ color: "#f87171" }}>*</span>
              </label>
              <input
                type="password" value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                onKeyDown={e => e.key === "Enter" && apiKey.trim() && setIsReady(true)}
                placeholder="AIzaSy…"
                style={{ ...inp, width: "100%", padding: "12px 16px", fontSize: "13px" }}
              />
              <div style={{ fontSize: "10px", color: "#334155", marginTop: "6px" }}>
                aistudio.google.com/app/apikey
              </div>
            </div>

            <div>
              <label style={{ fontSize: "9px", letterSpacing: "3px", color: "#fbbf24", display: "block", marginBottom: "8px" }}>
                MODEL
              </label>
              <select
                value={geminiModel} onChange={e => setGeminiModel(e.target.value)}
                style={{ ...inp, width: "100%", padding: "12px 16px", fontSize: "13px", cursor: "pointer" }}
              >
                <option value="gemini-2.5-pro">gemini-2.5-pro — Best accuracy (recommended)</option>
                <option value="gemini-2.5-flash">gemini-2.5-flash — Faster, slightly lower accuracy</option>
                <option value="gemini-2.0-flash">gemini-2.0-flash — Legacy fallback</option>
                <option value="gemini-1.5-pro">gemini-1.5-pro — Legacy fallback</option>
              </select>
            </div>

            <button
              onClick={() => apiKey.trim() && setIsReady(true)}
              disabled={!apiKey.trim()}
              style={{
                background: apiKey.trim() ? "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)" : "#1e293b",
                border: "none", borderRadius: "2px", padding: "15px",
                color: apiKey.trim() ? "#080d1a" : "#475569",
                fontSize: "10px", letterSpacing: "4px", fontWeight: 800,
                cursor: apiKey.trim() ? "pointer" : "not-allowed",
                fontFamily: "'IBM Plex Mono', monospace", transition: "all 0.2s",
                boxShadow: apiKey.trim() ? "0 4px 20px rgba(251,191,36,0.25)" : "none"
              }}
            >
              LAUNCH QTO SYSTEM →
            </button>
          </div>

          <div style={{
            marginTop: "36px", padding: "20px", borderRadius: "2px",
            background: "rgba(251,191,36,0.04)", border: "1px solid rgba(251,191,36,0.1)"
          }}>
            <div style={{ fontSize: "9px", color: "#64748b", lineHeight: 2.0, letterSpacing: "0.5px" }}>
              <span style={{ color: "#fbbf24" }}>◈</span>  Upload drawings page by page (JPG · PNG · WEBP)<br/>
              <span style={{ color: "#fbbf24" }}>◈</span>  AI identifies drawing type &amp; all QTO items automatically<br/>
              <span style={{ color: "#fbbf24" }}>◈</span>  Agent asks only for data not visible in drawing<br/>
              <span style={{ color: "#fbbf24" }}>◈</span>  Customize formulas per your project standards<br/>
              <span style={{ color: "#fbbf24" }}>◈</span>  Export master BOQ table to CSV
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ════════════════════════════════════════════════════════════════════
  // MAIN APP
  // ════════════════════════════════════════════════════════════════════
  return (
    <div style={{
      display: "flex", flexDirection: "column", height: "100vh",
      background: "#080d1a", color: "#cbd5e1",
      fontFamily: "'IBM Plex Mono', 'Courier New', monospace", overflow: "hidden"
    }}>
      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.3} }
        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-track { background: #080d1a; }
        ::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 2px; }
        input::placeholder, textarea::placeholder { color: #334155 !important; }
        select option { background: #0d1625; color: #cbd5e1; }
        input[type=number]::-webkit-inner-spin-button { opacity: 0.3; }
      `}</style>

      {/* ── TOPBAR ───────────────────────────────────────────── */}
      <div style={{
        height: "50px", flexShrink: 0, borderBottom: "1px solid rgba(251,191,36,0.12)",
        background: "rgba(8,13,26,0.99)", display: "flex", alignItems: "center",
        padding: "0 20px", gap: "20px", zIndex: 20
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span style={{ fontSize: "16px", fontWeight: 900, color: "#f1f5f9", letterSpacing: "-1px" }}>
            QTO<span style={{ color: "#fbbf24" }}>.AI</span>
          </span>
          <span style={{
            fontSize: "8px", letterSpacing: "2px", color: "#334155",
            background: "rgba(251,191,36,0.08)", border: "1px solid rgba(251,191,36,0.12)",
            padding: "2px 8px", borderRadius: "1px"
          }}>GEMINI 2.5</span>
        </div>

        <div style={{ display: "flex", gap: "2px" }}>
          {[
            { id: "drawings", label: `DRAWINGS (${drawings.length})` },
            { id: "formulas", label: `FORMULAS (${Object.keys(formulas).length})` },
            { id: "results",  label: `QTO TABLE (${qtoTable.length})` }
          ].map(t => (
            <button key={t.id} onClick={() => setActiveTab(t.id)} style={{
              background: activeTab === t.id ? "rgba(251,191,36,0.12)" : "transparent",
              border: activeTab === t.id ? "1px solid rgba(251,191,36,0.25)" : "1px solid transparent",
              color: activeTab === t.id ? "#fbbf24" : "#475569",
              padding: "6px 14px", borderRadius: "2px", cursor: "pointer",
              fontSize: "9px", letterSpacing: "1.5px", fontFamily: "inherit",
              fontWeight: activeTab === t.id ? 700 : 400, transition: "all 0.15s"
            }}>{t.label}</button>
          ))}
        </div>

        {isProcessing && (
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ animation: "spin 1s linear infinite", display: "inline-block", fontSize: "12px", color: "#fbbf24" }}>◌</span>
            <span style={{ fontSize: "10px", color: "#fbbf24", animation: "blink 1.5s ease infinite" }}>{processingMsg}</span>
          </div>
        )}
        <div style={{ marginLeft: isProcessing ? "0" : "auto", fontSize: "8px", color: "#1e293b" }}>{geminiModel}</div>
      </div>

      {/* ════════════════════════════════════════════════════════
          DRAWINGS TAB
      ════════════════════════════════════════════════════════ */}
      {activeTab === "drawings" && (
        <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>

          {/* ── Sidebar: Drawing List ── */}
          <div style={{ width: "220px", flexShrink: 0, borderRight: "1px solid rgba(255,255,255,0.05)", display: "flex", flexDirection: "column" }}>
            <div style={{ padding: "12px", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
              <button
                onClick={() => fileInputRef.current?.click()}
                style={{
                  width: "100%", background: "transparent",
                  border: "1px dashed rgba(251,191,36,0.35)", borderRadius: "2px",
                  padding: "10px", color: "#fbbf24", fontSize: "9px",
                  letterSpacing: "2px", cursor: "pointer", fontFamily: "inherit",
                  transition: "all 0.15s"
                }}
                onMouseOver={e => e.currentTarget.style.background = "rgba(251,191,36,0.06)"}
                onMouseOut={e => e.currentTarget.style.background = "transparent"}
              >+ UPLOAD DRAWING</button>
              <input ref={fileInputRef} type="file" multiple hidden accept="image/*" onChange={handleUpload} />
            </div>

            <div style={{ flex: 1, overflowY: "auto", padding: "8px 6px" }}>
              {drawings.length === 0 ? (
                <div style={{ padding: "20px 12px", color: "#1e293b", fontSize: "10px", textAlign: "center", lineHeight: 2 }}>
                  Upload drawing files<br/>to begin
                </div>
              ) : drawings.map(d => {
                const sc = statusCfg[d.status] || statusCfg.uploaded;
                const isSelected = selectedId === d.id;
                return (
                  <div
                    key={d.id}
                    onClick={() => setSelectedId(d.id)}
                    style={{
                      padding: "10px 10px", borderRadius: "2px", cursor: "pointer", marginBottom: "3px",
                      background: isSelected ? "rgba(251,191,36,0.08)" : "transparent",
                      border: isSelected ? "1px solid rgba(251,191,36,0.2)" : "1px solid transparent",
                      transition: "all 0.15s"
                    }}
                  >
                    <div style={{ fontSize: "9px", color: isSelected ? "#e2e8f0" : "#64748b", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {d.name.replace(/\.[^.]+$/, "")}
                    </div>
                    <div style={{ fontSize: "8px", color: sc.color, marginTop: "5px", letterSpacing: "1px" }}>
                      ● {sc.label}
                    </div>
                    {d.analysis?.drawingInfo?.type && (
                      <div style={{ fontSize: "8px", color: "#334155", marginTop: "2px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {d.analysis.drawingInfo.type}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {drawings.length > 0 && (
              <div style={{ padding: "10px 12px", borderTop: "1px solid rgba(255,255,255,0.05)", fontSize: "8px", color: "#1e293b" }}>
                {drawings.filter(d => d.status === "complete").length} / {drawings.length} complete
              </div>
            )}
          </div>

          {/* ── Center: Preview ── */}
          <div style={{ width: "320px", flexShrink: 0, borderRight: "1px solid rgba(255,255,255,0.05)", display: "flex", flexDirection: "column" }}>
            <div style={{ padding: "10px 14px", borderBottom: "1px solid rgba(255,255,255,0.05)", fontSize: "8px", color: "#334155", letterSpacing: "2px" }}>
              DRAWING PREVIEW
            </div>

            {selectedDrawing ? (
              <div style={{ flex: 1, overflowY: "auto", padding: "12px", display: "flex", flexDirection: "column", gap: "10px" }}>
                <img src={selectedDrawing.imageUrl} alt={selectedDrawing.name} style={{ width: "100%", borderRadius: "2px", border: "1px solid rgba(255,255,255,0.06)" }} />

                {/* Drawing Info Card */}
                {selectedDrawing.analysis?.drawingInfo && (
                  <div style={{ background: "rgba(10,18,36,0.9)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "2px", padding: "12px" }}>
                    {Object.entries(selectedDrawing.analysis.drawingInfo).filter(([, v]) => v && v !== "Not visible" && v !== "not visible").map(([k, v]) => (
                      <div key={k} style={{ display: "flex", gap: "8px", marginBottom: "5px", alignItems: "baseline" }}>
                        <span style={{ fontSize: "8px", color: "#334155", minWidth: "72px", textTransform: "uppercase", letterSpacing: "1px", flexShrink: 0 }}>{k}</span>
                        <span style={{ fontSize: "10px", color: "#94a3b8", lineHeight: 1.4 }}>{v}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Action: Analyze */}
                {selectedDrawing.status === "uploaded" && (
                  <button
                    onClick={() => analyzeDrawing(selectedDrawing)}
                    disabled={isProcessing}
                    style={{
                      background: isProcessing ? "#1e293b" : "linear-gradient(135deg, #f59e0b, #d97706)",
                      border: "none", borderRadius: "2px", padding: "12px",
                      color: isProcessing ? "#475569" : "#080d1a",
                      fontSize: "9px", letterSpacing: "3px", fontWeight: 800,
                      cursor: isProcessing ? "not-allowed" : "pointer", fontFamily: "inherit"
                    }}
                  >
                    ANALYZE WITH GEMINI →
                  </button>
                )}

                {/* Error */}
                {selectedDrawing.status === "error" && (
                  <div style={{ background: "rgba(248,113,113,0.06)", border: "1px solid rgba(248,113,113,0.25)", borderRadius: "2px", padding: "12px" }}>
                    <div style={{ fontSize: "9px", color: "#f87171", letterSpacing: "1px", marginBottom: "6px" }}>ERROR</div>
                    <div style={{ fontSize: "10px", color: "#fca5a5", lineHeight: 1.7 }}>{selectedDrawing.error}</div>
                    <button
                      onClick={() => updateDrawing(selectedDrawing.id, { status: "uploaded", error: null })}
                      style={{ marginTop: "10px", background: "transparent", border: "1px solid rgba(248,113,113,0.3)", borderRadius: "2px", padding: "6px 14px", color: "#f87171", fontSize: "8px", cursor: "pointer", fontFamily: "inherit", letterSpacing: "1px" }}
                    >RETRY</button>
                  </div>
                )}

                {/* Complete badge */}
                {selectedDrawing.status === "complete" && (
                  <div style={{ background: "rgba(74,222,128,0.05)", border: "1px solid rgba(74,222,128,0.2)", borderRadius: "2px", padding: "10px 12px" }}>
                    <div style={{ fontSize: "9px", color: "#4ade80", letterSpacing: "1px" }}>
                      ✓ {selectedDrawing.results?.filter(r => r.totalQty !== null).length || 0} items added to QTO table
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <div style={{ color: "#1e293b", fontSize: "9px", letterSpacing: "2px", textAlign: "center" }}>
                  SELECT A DRAWING
                </div>
              </div>
            )}
          </div>

          {/* ── Right: Analysis Panel ── */}
          <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", minWidth: 0 }}>
            <div style={{
              padding: "10px 20px", borderBottom: "1px solid rgba(255,255,255,0.05)",
              display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0
            }}>
              <span style={{ fontSize: "8px", color: "#334155", letterSpacing: "2px" }}>AI ANALYSIS PANEL</span>
              {selectedDrawing && (
                <span style={{
                  fontSize: "8px", letterSpacing: "1px",
                  color: statusCfg[selectedDrawing.status]?.color || "#64748b"
                }}>● {statusCfg[selectedDrawing.status]?.label}</span>
              )}
            </div>

            <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px" }}>
              {!selectedDrawing?.analysis ? (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", color: "#1e293b" }}>
                  <div style={{ fontSize: "48px", marginBottom: "16px", opacity: 0.3 }}>⬡</div>
                  <div style={{ fontSize: "9px", letterSpacing: "3px" }}>
                    {selectedDrawing ? "CLICK ANALYZE TO START" : "UPLOAD & SELECT A DRAWING"}
                  </div>
                </div>
              ) : (
                <>
                  {/* Summary */}
                  {selectedDrawing.analysis.summary && (
                    <div style={{
                      background: "rgba(251,191,36,0.04)", border: "1px solid rgba(251,191,36,0.12)",
                      borderRadius: "2px", padding: "14px 16px", marginBottom: "16px"
                    }}>
                      <div style={{ fontSize: "8px", color: "#fbbf24", letterSpacing: "2px", marginBottom: "8px" }}>AI SUMMARY</div>
                      <div style={{ fontSize: "11px", color: "#94a3b8", lineHeight: 1.8 }}>{selectedDrawing.analysis.summary}</div>
                    </div>
                  )}

                  {/* Warnings */}
                  {selectedDrawing.analysis.warnings?.filter(Boolean).length > 0 && (
                    <div style={{
                      background: "rgba(251,146,60,0.04)", border: "1px solid rgba(251,146,60,0.18)",
                      borderRadius: "2px", padding: "12px 16px", marginBottom: "16px"
                    }}>
                      <div style={{ fontSize: "8px", color: "#fb923c", letterSpacing: "2px", marginBottom: "8px" }}>⚠ QS FLAGS</div>
                      {selectedDrawing.analysis.warnings.map((w, i) => (
                        <div key={i} style={{ fontSize: "10px", color: "#fdba74", lineHeight: 1.8 }}>• {w}</div>
                      ))}
                    </div>
                  )}

                  {/* QTO Items */}
                  <div style={{ marginBottom: "20px" }}>
                    <div style={{ fontSize: "8px", color: "#334155", letterSpacing: "2px", marginBottom: "12px", display: "flex", alignItems: "center", gap: "10px" }}>
                      <span>QTO ITEMS ({selectedDrawing.analysis.qtoItems?.length || 0})</span>
                      <span style={{ color: "#4ade80" }}>✓ {(selectedDrawing.analysis.qtoItems || []).filter(i => i.canCalculate).length} calculated</span>
                      <span style={{ color: "#fb923c" }}>⏳ {(selectedDrawing.analysis.qtoItems || []).filter(i => !i.canCalculate).length} pending</span>
                    </div>

                    {(selectedDrawing.analysis.qtoItems || []).map(item => (
                      <div key={item.id} style={{
                        background: "rgba(12,20,42,0.9)",
                        border: `1px solid ${item.canCalculate && item.totalQty !== null ? "rgba(74,222,128,0.12)" : "rgba(251,146,60,0.12)"}`,
                        borderRadius: "2px", padding: "12px 14px", marginBottom: "6px"
                      }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" }}>
                          <span style={{ fontSize: "8px", color: discColor[item.discipline] || "#64748b", letterSpacing: "1px", fontWeight: 700 }}>{item.discipline}</span>
                          <span style={{ fontSize: "9px", color: "#fbbf24", fontWeight: 700 }}>{item.id}</span>
                          <span style={{ marginLeft: "auto", fontSize: "8px", letterSpacing: "1px", color: item.canCalculate && item.totalQty !== null ? "#4ade80" : "#fb923c" }}>
                            {item.canCalculate && item.totalQty !== null ? "✓ READY" : "⏳ PENDING"}
                          </span>
                        </div>
                        <div style={{ fontSize: "11px", color: "#94a3b8", marginBottom: item.canCalculate && item.totalQty !== null ? "8px" : "0" }}>
                          {item.description}
                        </div>
                        {item.canCalculate && item.totalQty !== null && (
                          <>
                            <div style={{ display: "flex", alignItems: "baseline", gap: "8px" }}>
                              <span style={{ fontSize: "20px", fontWeight: 900, color: "#e2e8f0", letterSpacing: "-1px" }}>
                                {Number(item.totalQty).toFixed(2)}
                              </span>
                              <span style={{ fontSize: "11px", color: "#475569" }}>{item.unit}</span>
                            </div>
                            {item.breakdown && (
                              <div style={{
                                fontSize: "10px", color: "#334155", marginTop: "8px",
                                paddingTop: "8px", borderTop: "1px solid rgba(255,255,255,0.04)",
                                lineHeight: 1.7, whiteSpace: "pre-wrap"
                              }}>{item.breakdown}</div>
                            )}
                          </>
                        )}
                        {!item.canCalculate && item.missingInputs?.length > 0 && (
                          <div style={{ fontSize: "9px", color: "#475569", marginTop: "4px" }}>
                            Waiting for: {item.missingInputs.join(", ")}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>

                  {/* QUESTIONS FORM */}
                  {selectedDrawing.status === "questions" && selectedDrawing.analysis.questions?.length > 0 && (
                    <div style={{
                      background: "rgba(12,24,50,0.95)", border: "1px solid rgba(251,191,36,0.2)",
                      borderRadius: "2px", padding: "20px", marginBottom: "16px"
                    }}>
                      <div style={{ fontSize: "8px", color: "#fbbf24", letterSpacing: "3px", marginBottom: "20px" }}>
                        AGENT REQUIRES THE FOLLOWING DATA
                      </div>

                      {selectedDrawing.analysis.questions.map((q, qi) => (
                        <div key={q.id} style={{ marginBottom: qi < selectedDrawing.analysis.questions.length - 1 ? "22px" : "0" }}>
                          <div style={{ fontSize: "11px", color: "#e2e8f0", lineHeight: 1.7, marginBottom: "4px" }}>
                            <span style={{ color: "#fbbf24", marginRight: "6px" }}>Q{qi + 1}.</span>
                            {q.text}
                          </div>
                          <div style={{ fontSize: "9px", color: "#334155", marginBottom: "8px", lineHeight: 1.6 }}>
                            Typical: {q.typicalRange}
                            {q.affectsItems?.length > 0 && (
                              <span style={{ color: "#1e3a5f", marginLeft: "8px" }}>→ {q.affectsItems.join(", ")}</span>
                            )}
                          </div>
                          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                            <input
                              type="text"
                              value={selectedDrawing.answers[q.id] ?? ""}
                              onChange={e => updateDrawing(selectedDrawing.id, {
                                answers: { ...selectedDrawing.answers, [q.id]: e.target.value }
                              })}
                              placeholder={q.suggested || "Enter value"}
                              style={{
                                ...inp,
                                flex: 1, borderColor: "rgba(251,191,36,0.25)",
                                color: "#fbbf24", fontSize: "14px", padding: "10px 14px"
                              }}
                            />
                            {q.unit && (
                              <span style={{
                                fontSize: "10px", color: "#475569",
                                background: "rgba(0,0,0,0.3)", padding: "10px 12px",
                                border: "1px solid rgba(100,116,139,0.2)", borderRadius: "2px"
                              }}>{q.unit}</span>
                            )}
                          </div>
                        </div>
                      ))}

                      <button
                        onClick={() => submitAnswers(selectedDrawing)}
                        disabled={isProcessing}
                        style={{
                          width: "100%", marginTop: "24px",
                          background: isProcessing ? "#1e293b" : "linear-gradient(135deg, #f59e0b, #d97706)",
                          border: "none", borderRadius: "2px", padding: "13px",
                          color: isProcessing ? "#475569" : "#080d1a",
                          fontSize: "9px", letterSpacing: "4px", fontWeight: 800,
                          cursor: isProcessing ? "not-allowed" : "pointer", fontFamily: "inherit"
                        }}
                      >
                        {isProcessing ? "CALCULATING…" : "CALCULATE ALL QUANTITIES →"}
                      </button>
                    </div>
                  )}

                  {/* Observed Elements */}
                  {selectedDrawing.analysis.observedElements?.length > 0 && (
                    <div>
                      <div style={{ fontSize: "8px", color: "#334155", letterSpacing: "2px", marginBottom: "10px" }}>ELEMENTS EXTRACTED FROM DRAWING</div>
                      <div style={{ background: "rgba(10,18,36,0.8)", border: "1px solid rgba(255,255,255,0.05)", borderRadius: "2px", overflow: "hidden" }}>
                        {selectedDrawing.analysis.observedElements.map((el, i) => (
                          <div key={i} style={{
                            display: "flex", alignItems: "center", gap: "10px",
                            padding: "9px 14px", fontSize: "10px",
                            borderBottom: i < selectedDrawing.analysis.observedElements.length - 1 ? "1px solid rgba(255,255,255,0.03)" : "none"
                          }}>
                            <span style={{ color: "#fbbf24", minWidth: "32px", fontWeight: 700 }}>{el.mark || "—"}</span>
                            <span style={{ color: "#64748b", minWidth: "24px" }}>×{el.count}</span>
                            <span style={{ color: "#94a3b8", flex: 1 }}>{el.type}</span>
                            {el.dims && (
                              <span style={{ color: "#334155", fontSize: "9px" }}>
                                {el.dims.L}×{el.dims.W}×{el.dims.H} {el.dims.unit}
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ════════════════════════════════════════════════════════
          FORMULAS TAB
      ════════════════════════════════════════════════════════ */}
      {activeTab === "formulas" && (
        <div style={{ flex: 1, overflowY: "auto", padding: "24px 32px" }}>
          <div style={{ maxWidth: "860px", margin: "0 auto" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "28px" }}>
              <div>
                <div style={{ fontSize: "8px", color: "#fbbf24", letterSpacing: "4px", marginBottom: "8px" }}>FORMULA LIBRARY</div>
                <div style={{ fontSize: "11px", color: "#475569", lineHeight: 1.7 }}>
                  These formulas are injected into the Gemini prompt and applied during calculations.<br/>
                  Edit any formula to match your project standards or client requirements.
                </div>
              </div>
              <button
                onClick={() => { setFormulas(DEFAULT_FORMULAS); setEditingKey(null); }}
                style={{ background: "transparent", border: "1px solid rgba(100,116,139,0.25)", borderRadius: "2px", padding: "8px 16px", color: "#475569", fontSize: "8px", letterSpacing: "2px", cursor: "pointer", fontFamily: "inherit", flexShrink: 0 }}
              >RESET ALL</button>
            </div>

            {["CIVIL", "STR", "ARCH", "FINISHING"].map(cat => {
              const items = Object.entries(formulas).filter(([, f]) => f.category === cat);
              if (!items.length) return null;
              return (
                <div key={cat} style={{ marginBottom: "32px" }}>
                  <div style={{
                    fontSize: "8px", letterSpacing: "4px", color: discColor[cat] || "#64748b",
                    marginBottom: "12px", paddingBottom: "8px",
                    borderBottom: `1px solid ${discColor[cat] ? discColor[cat] + "20" : "rgba(255,255,255,0.05)"}`
                  }}>{cat}</div>

                  {items.map(([key, formula]) => (
                    <div key={key} style={{
                      background: "rgba(12,20,42,0.9)", border: "1px solid rgba(255,255,255,0.05)",
                      borderRadius: "2px", padding: "14px 16px", marginBottom: "6px"
                    }}>
                      {editingKey === key ? (
                        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                          <div style={{ display: "flex", gap: "10px" }}>
                            <input value={formula.name} onChange={e => setFormulas(p => ({ ...p, [key]: { ...p[key], name: e.target.value } }))}
                              style={{ ...inp, flex: 1 }} />
                            <input value={formula.unit} onChange={e => setFormulas(p => ({ ...p, [key]: { ...p[key], unit: e.target.value } }))}
                              style={{ ...inp, width: "60px" }} />
                          </div>
                          <textarea value={formula.formula} rows={2}
                            onChange={e => setFormulas(p => ({ ...p, [key]: { ...p[key], formula: e.target.value } }))}
                            style={{ ...inp, color: "#fbbf24", resize: "vertical", lineHeight: 1.6 }} />
                          <textarea value={formula.description} rows={2}
                            onChange={e => setFormulas(p => ({ ...p, [key]: { ...p[key], description: e.target.value } }))}
                            style={{ ...inp, color: "#94a3b8", fontSize: "11px", resize: "vertical", lineHeight: 1.6 }} />
                          <div style={{ display: "flex", gap: "8px" }}>
                            <button onClick={() => setEditingKey(null)} style={{ background: "rgba(74,222,128,0.1)", border: "1px solid rgba(74,222,128,0.25)", borderRadius: "2px", padding: "6px 18px", color: "#4ade80", fontSize: "8px", cursor: "pointer", fontFamily: "inherit", letterSpacing: "2px" }}>SAVE</button>
                            <button onClick={() => { setFormulas(p => ({ ...p, [key]: DEFAULT_FORMULAS[key] })); setEditingKey(null); }} style={{ background: "transparent", border: "1px solid rgba(100,116,139,0.2)", borderRadius: "2px", padding: "6px 18px", color: "#64748b", fontSize: "8px", cursor: "pointer", fontFamily: "inherit", letterSpacing: "2px" }}>RESET</button>
                            <button onClick={() => setEditingKey(null)} style={{ background: "transparent", border: "none", padding: "6px 10px", color: "#475569", fontSize: "8px", cursor: "pointer", fontFamily: "inherit" }}>✕</button>
                          </div>
                        </div>
                      ) : (
                        <div style={{ display: "flex", gap: "14px", alignItems: "flex-start" }}>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ display: "flex", gap: "10px", alignItems: "center", marginBottom: "6px" }}>
                              <span style={{ fontSize: "10px", color: "#e2e8f0", fontWeight: 700 }}>{formula.name}</span>
                              <span style={{ fontSize: "8px", color: "#334155" }}>[{key}]</span>
                              <span style={{ marginLeft: "auto", fontSize: "9px", color: "#475569", flexShrink: 0 }}>{formula.unit}</span>
                            </div>
                            <div style={{ fontSize: "11px", color: "#fbbf24", marginBottom: "5px", wordBreak: "break-all" }}>{formula.formula}</div>
                            <div style={{ fontSize: "10px", color: "#475569", lineHeight: 1.6 }}>{formula.description}</div>
                            {Object.keys(formula.defaults).length > 0 && (
                              <div style={{ fontSize: "9px", color: "#1e3a5f", marginTop: "4px" }}>
                                defaults: {Object.entries(formula.defaults).map(([k, v]) => `${k}=${v}`).join("  ·  ")}
                              </div>
                            )}
                          </div>
                          <button
                            onClick={() => setEditingKey(key)}
                            style={{ background: "transparent", border: "1px solid rgba(100,116,139,0.18)", borderRadius: "2px", padding: "5px 12px", color: "#475569", fontSize: "8px", cursor: "pointer", fontFamily: "inherit", letterSpacing: "1px", flexShrink: 0 }}
                          >EDIT</button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ════════════════════════════════════════════════════════
          QTO RESULTS TAB
      ════════════════════════════════════════════════════════ */}
      {activeTab === "results" && (
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div style={{
            padding: "10px 20px", borderBottom: "1px solid rgba(255,255,255,0.05)",
            display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0
          }}>
            <div style={{ fontSize: "8px", color: "#334155", letterSpacing: "2px" }}>
              MASTER QTO TABLE — {qtoTable.length} LINE ITEMS
            </div>
            {qtoTable.length > 0 && (
              <button
                onClick={exportCSV}
                style={{ background: "rgba(74,222,128,0.08)", border: "1px solid rgba(74,222,128,0.25)", borderRadius: "2px", padding: "6px 16px", color: "#4ade80", fontSize: "8px", letterSpacing: "2px", cursor: "pointer", fontFamily: "inherit" }}
              >EXPORT CSV ↓</button>
            )}
          </div>

          {qtoTable.length === 0 ? (
            <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: "10px" }}>
              <div style={{ fontSize: "32px", opacity: 0.1 }}>⊞</div>
              <div style={{ fontSize: "9px", color: "#1e293b", letterSpacing: "2px" }}>COMPLETE DRAWINGS ANALYSIS TO POPULATE TABLE</div>
            </div>
          ) : (
            <div style={{ flex: 1, overflow: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", minWidth: "760px" }}>
                <thead>
                  <tr style={{ position: "sticky", top: 0, background: "#080d1a", zIndex: 5 }}>
                    {["DRAWING", "TYPE", "DISC", "ITEM CODE", "DESCRIPTION", "UNIT", "QUANTITY"].map((h, i) => (
                      <th key={h} style={{
                        padding: "9px 14px", fontSize: "8px", letterSpacing: "2px",
                        color: "#334155", fontWeight: 700,
                        textAlign: i === 6 ? "right" : "left",
                        borderBottom: "1px solid rgba(251,191,36,0.12)"
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Array.from(new Set(qtoTable.map(r => r.drawingId))).flatMap(drawingId => {
                    const rows = qtoTable.filter(r => r.drawingId === drawingId);
                    return rows.map((row, i) => (
                      <tr key={row.rowId} style={{ borderBottom: "1px solid rgba(255,255,255,0.025)" }}>
                        <td style={{ padding: "9px 14px", fontSize: "9px", color: "#475569", maxWidth: "140px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {i === 0 ? row.drawingName.replace(/\.[^.]+$/, "") : ""}
                        </td>
                        <td style={{ padding: "9px 14px", fontSize: "9px", color: "#334155" }}>{row.drawingType}</td>
                        <td style={{ padding: "9px 14px" }}>
                          <span style={{ fontSize: "8px", color: discColor[row.discipline] || "#475569", letterSpacing: "1px", fontWeight: 700 }}>
                            {row.discipline}
                          </span>
                        </td>
                        <td style={{ padding: "9px 14px", fontSize: "9px", color: "#fbbf24", fontWeight: 700 }}>{row.itemCode}</td>
                        <td style={{ padding: "9px 14px", fontSize: "11px", color: "#94a3b8", maxWidth: "280px" }}>{row.description}</td>
                        <td style={{ padding: "9px 14px", fontSize: "10px", color: "#475569" }}>{row.unit}</td>
                        <td style={{ padding: "9px 14px", textAlign: "right" }}>
                          <span style={{ fontSize: "15px", fontWeight: 900, color: "#e2e8f0", letterSpacing: "-0.5px" }}>
                            {row.qty !== null && row.qty !== undefined ? Number(row.qty).toFixed(2) : "—"}
                          </span>
                        </td>
                      </tr>
                    ));
                  })}
                </tbody>
                <tfoot>
                  <tr>
                    <td colSpan={7} style={{ borderTop: "1px solid rgba(251,191,36,0.12)", padding: "12px 14px" }}>
                      <div style={{ display: "flex", gap: "28px", flexWrap: "wrap", alignItems: "center" }}>
                        <span style={{ fontSize: "8px", color: "#334155", letterSpacing: "2px" }}>UNIT TOTALS:</span>
                        {Array.from(new Set(qtoTable.map(r => r.unit))).map(unit => {
                          const total = qtoTable.filter(r => r.unit === unit && r.qty !== null).reduce((s, r) => s + Number(r.qty || 0), 0);
                          return (
                            <div key={unit} style={{ fontSize: "10px" }}>
                              <span style={{ color: "#475569" }}>{unit} </span>
                              <span style={{ color: "#fbbf24", fontWeight: 700 }}>{total.toFixed(2)}</span>
                            </div>
                          );
                        })}
                      </div>
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
