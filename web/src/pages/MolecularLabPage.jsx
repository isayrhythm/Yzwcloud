import { useMemo, useState } from "react";

const NN_PARAMS = {
  AA: { dh: -7.9, ds: -22.2 },
  TT: { dh: -7.9, ds: -22.2 },
  AT: { dh: -7.2, ds: -20.4 },
  TA: { dh: -7.2, ds: -21.3 },
  CA: { dh: -8.5, ds: -22.7 },
  TG: { dh: -8.5, ds: -22.7 },
  GT: { dh: -8.4, ds: -22.4 },
  AC: { dh: -8.4, ds: -22.4 },
  CT: { dh: -7.8, ds: -21.0 },
  AG: { dh: -7.8, ds: -21.0 },
  GA: { dh: -8.2, ds: -22.2 },
  TC: { dh: -8.2, ds: -22.2 },
  CG: { dh: -10.6, ds: -27.2 },
  GC: { dh: -9.8, ds: -24.4 },
  GG: { dh: -8.0, ds: -19.9 },
  CC: { dh: -8.0, ds: -19.9 },
};

const DNA_COMPLEMENT = { A: "T", T: "A", C: "G", G: "C", N: "N" };

function normalizeSequence(value) {
  return String(value || "")
    .toUpperCase()
    .replace(/U/g, "T")
    .replace(/[^ATCGN]/g, "");
}

function gcContent(sequence) {
  if (!sequence.length) return 0;
  const gcCount = [...sequence].filter((base) => base === "G" || base === "C").length;
  return (gcCount / sequence.length) * 100;
}

function reverseSequence(sequence) {
  return [...sequence].reverse().join("");
}

function complementSequence(sequence) {
  return [...sequence].map((base) => DNA_COMPLEMENT[base] || "N").join("");
}

function reverseComplementSequence(sequence) {
  return reverseSequence(complementSequence(sequence));
}

function estimateTm(sequence, primerConcentrationNm = 250, saltConcentrationMm = 50) {
  const normalized = normalizeSequence(sequence);
  if (normalized.length < 2) {
    return { normalized, error: "Sequence must contain at least 2 DNA bases." };
  }

  let dh = 0.2;
  let ds = -5.7;
  for (let index = 0; index < normalized.length - 1; index += 1) {
    const pair = normalized.slice(index, index + 2);
    const params = NN_PARAMS[pair];
    if (!params) {
      return { normalized, error: `Unsupported dinucleotide: ${pair}` };
    }
    dh += params.dh;
    ds += params.ds;
  }

  const aCount = [...normalized].filter((base) => base === "A").length;
  const tCount = [...normalized].filter((base) => base === "T").length;
  const gCount = [...normalized].filter((base) => base === "G").length;
  const cCount = [...normalized].filter((base) => base === "C").length;
  const concentrationM = Math.max(primerConcentrationNm, 1) * 1e-9;
  const sodiumM = Math.max(saltConcentrationMm, 1) * 1e-3;
  const gasConstant = 1.987;
  const tmNearestNeighbor =
    (1000 * dh) / (ds + gasConstant * Math.log(concentrationM / 4)) - 273.15 + 16.6 * Math.log10(sodiumM);

  return {
    normalized,
    length: normalized.length,
    gcPercent: gcContent(normalized),
    tmNearestNeighbor,
    tmWallace: 2 * (aCount + tCount) + 4 * (gCount + cCount),
    recommendedAnnealing: tmNearestNeighbor - 5,
  };
}

async function copyToClipboard(value) {
  if (!navigator.clipboard) return false;
  await navigator.clipboard.writeText(value);
  return true;
}

const CODON_TABLE = {
  TTT: "F", TTC: "F", TTA: "L", TTG: "L",
  TCT: "S", TCC: "S", TCA: "S", TCG: "S",
  TAT: "Y", TAC: "Y", TAA: "*", TAG: "*",
  TGT: "C", TGC: "C", TGA: "*", TGG: "W",
  CTT: "L", CTC: "L", CTA: "L", CTG: "L",
  CCT: "P", CCC: "P", CCA: "P", CCG: "P",
  CAT: "H", CAC: "H", CAA: "Q", CAG: "Q",
  CGT: "R", CGC: "R", CGA: "R", CGG: "R",
  ATT: "I", ATC: "I", ATA: "I", ATG: "M",
  ACT: "T", ACC: "T", ACA: "T", ACG: "T",
  AAT: "N", AAC: "N", AAA: "K", AAG: "K",
  AGT: "S", AGC: "S", AGA: "R", AGG: "R",
  GTT: "V", GTC: "V", GTA: "V", GTG: "V",
  GCT: "A", GCC: "A", GCA: "A", GCG: "A",
  GAT: "D", GAC: "D", GAA: "E", GAG: "E",
  GGT: "G", GGC: "G", GGA: "G", GGG: "G",
};

const RESTRICTION_ENZYMES = [
  { name: "EcoRI", site: "GAATTC" },
  { name: "BamHI", site: "GGATCC" },
  { name: "HindIII", site: "AAGCTT" },
  { name: "NotI", site: "GCGGCCGC" },
  { name: "XhoI", site: "CTCGAG" },
  { name: "NheI", site: "GCTAGC" },
  { name: "XbaI", site: "TCTAGA" },
  { name: "SpeI", site: "ACTAGT" },
  { name: "KpnI", site: "GGTACC" },
  { name: "SacI", site: "GAGCTC" },
  { name: "PstI", site: "CTGCAG" },
  { name: "SalI", site: "GTCGAC" },
];

const LAB_MODULES = [
  {
    id: "primer_tm",
    group: "Primer",
    title: "Primer Tm",
    summary: "Single-primer Tm, GC, and annealing estimate.",
  },
  {
    id: "primer_pair",
    group: "Primer",
    title: "Primer Pair",
    summary: "Forward/reverse comparison and Tm balance.",
  },
  {
    id: "oligo_screen",
    group: "Primer",
    title: "Hairpin/Dimer",
    summary: "Rough self- and cross-dimer screening.",
  },
  {
    id: "dna_tools",
    group: "Sequence",
    title: "DNA Tools",
    summary: "Reverse, complement, reverse-complement, and copy helpers.",
  },
  {
    id: "transcription",
    group: "Sequence",
    title: "DNA/RNA Convert",
    summary: "DNA<->RNA conversion for coding strand workflows.",
  },
  {
    id: "translation",
    group: "Sequence",
    title: "ORF/Translation",
    summary: "Translate frames and enumerate ORFs.",
  },
  {
    id: "restriction_scan",
    group: "Cloning",
    title: "Restriction Scan",
    summary: "Scan common enzyme sites and cut positions.",
  },
];

function normalizeRnaSequence(value) {
  return String(value || "")
    .toUpperCase()
    .replace(/T/g, "U")
    .replace(/[^AUCGN]/g, "");
}

function dnaToRna(sequence) {
  return normalizeSequence(sequence).replace(/T/g, "U");
}

function rnaToDna(sequence) {
  return normalizeRnaSequence(sequence).replace(/U/g, "T");
}

function longestCommonSubstring(first, second) {
  if (!first || !second) return "";
  const matrix = Array.from({ length: first.length + 1 }, () => Array(second.length + 1).fill(0));
  let maxLength = 0;
  let endIndex = 0;
  for (let row = 1; row <= first.length; row += 1) {
    for (let col = 1; col <= second.length; col += 1) {
      if (first[row - 1] === second[col - 1]) {
        matrix[row][col] = matrix[row - 1][col - 1] + 1;
        if (matrix[row][col] > maxLength) {
          maxLength = matrix[row][col];
          endIndex = row;
        }
      }
    }
  }
  return first.slice(endIndex - maxLength, endIndex);
}

function scoreComplementRisk(matchLength, threePrimeMatch) {
  if (matchLength >= 6 || threePrimeMatch >= 4) return "High";
  if (matchLength >= 4 || threePrimeMatch >= 3) return "Medium";
  return "Low";
}

function countThreePrimeComplement(first, second) {
  let count = 0;
  const limit = Math.min(first.length, second.length);
  for (let index = 0; index < limit; index += 1) {
    const leftBase = first[first.length - 1 - index];
    const rightBase = second[second.length - 1 - index];
    if ((DNA_COMPLEMENT[leftBase] || "N") !== rightBase) break;
    count += 1;
  }
  return count;
}

function screenOligos(primerA, primerB = "") {
  const first = normalizeSequence(primerA);
  const second = normalizeSequence(primerB || primerA);
  const firstRc = reverseComplementSequence(first);
  const secondRc = reverseComplementSequence(second);
  const hairpinSeed = longestCommonSubstring(first, firstRc);
  const selfDimerSeed = longestCommonSubstring(first, firstRc);
  const crossDimerSeed = longestCommonSubstring(first, secondRc);
  const self3Prime = countThreePrimeComplement(first, firstRc);
  const cross3Prime = countThreePrimeComplement(first, secondRc);

  return {
    first,
    second,
    hairpin: {
      seed: hairpinSeed,
      matchLength: hairpinSeed.length,
      risk: scoreComplementRisk(hairpinSeed.length, self3Prime),
      threePrimeMatch: self3Prime,
    },
    selfDimer: {
      seed: selfDimerSeed,
      matchLength: selfDimerSeed.length,
      risk: scoreComplementRisk(selfDimerSeed.length, self3Prime),
      threePrimeMatch: self3Prime,
    },
    crossDimer: {
      seed: crossDimerSeed,
      matchLength: crossDimerSeed.length,
      risk: scoreComplementRisk(crossDimerSeed.length, cross3Prime),
      threePrimeMatch: cross3Prime,
    },
  };
}

function translateSequence(sequence, frame = 1) {
  const normalized = normalizeSequence(sequence);
  let peptide = "";
  for (let index = frame - 1; index + 2 < normalized.length; index += 3) {
    peptide += CODON_TABLE[normalized.slice(index, index + 3)] || "X";
  }
  return peptide;
}

function findOrfs(sequence, strand = "forward") {
  const normalized = strand === "reverse" ? reverseComplementSequence(sequence) : normalizeSequence(sequence);
  const orfs = [];
  for (let frame = 0; frame < 3; frame += 1) {
    for (let index = frame; index + 2 < normalized.length; index += 3) {
      if (normalized.slice(index, index + 3) !== "ATG") continue;
      let peptide = "M";
      let stopIndex = -1;
      for (let cursor = index + 3; cursor + 2 < normalized.length; cursor += 3) {
        const codon = normalized.slice(cursor, cursor + 3);
        const aa = CODON_TABLE[codon] || "X";
        if (aa === "*") {
          stopIndex = cursor + 3;
          break;
        }
        peptide += aa;
      }
      if (stopIndex > 0) {
        orfs.push({
          strand,
          frame: frame + 1,
          start: index + 1,
          end: stopIndex,
          lengthNt: stopIndex - index,
          peptide,
        });
      }
    }
  }
  return orfs.sort((left, right) => right.lengthNt - left.lengthNt);
}

function scanRestrictionSites(sequence) {
  const normalized = normalizeSequence(sequence);
  return RESTRICTION_ENZYMES.map((enzyme) => {
    const positions = [];
    let startIndex = 0;
    while (startIndex < normalized.length) {
      const matchIndex = normalized.indexOf(enzyme.site, startIndex);
      if (matchIndex < 0) break;
      positions.push(matchIndex + 1);
      startIndex = matchIndex + 1;
    }
    return {
      ...enzyme,
      positions,
      count: positions.length,
      ranges: positions.map((position) => ({
        start: position - 1,
        end: position - 1 + enzyme.site.length,
      })),
    };
  }).filter((enzyme) => enzyme.count > 0);
}

export function MolecularLabPage() {
  const [activeModule, setActiveModule] = useState("primer_tm");
  const activeModuleMeta = LAB_MODULES.find((item) => item.id === activeModule) || LAB_MODULES[0];

  return (
    <main className="lab-page">
      <section className="lab-hero">
        <div>
          <p className="eyebrow">Molecular Biology</p>
          <h1>Molecular Lab</h1>
          <p className="summary">
            Experiment design utilities organized as selectable units. Invalid characters stay visible and are
            highlighted instead of being hard-blocked.
          </p>
        </div>
      </section>
      <section className="lab-module-picker">
        {LAB_MODULES.map((module) => (
          <button
            key={module.id}
            type="button"
            className={`lab-module-tile ${activeModule === module.id ? "active" : ""}`}
            onClick={() => setActiveModule(module.id)}
          >
            <span>{module.group}</span>
            <strong>{module.title}</strong>
            <small>{module.summary}</small>
          </button>
        ))}
      </section>
      <section className="lab-workspace">
        <div className="lab-workspace-head">
          <div>
            <span className="lab-chip">{activeModuleMeta.group}</span>
            <h2>{activeModuleMeta.title}</h2>
          </div>
          <p>{activeModuleMeta.summary}</p>
        </div>
        <MolecularLabModule moduleId={activeModule} />
      </section>
    </main>
  );
}

function PrimerTmCard() {
  const [sequence, setSequence] = useState("");
  const [primerConcentration, setPrimerConcentration] = useState("250");
  const [saltConcentration, setSaltConcentration] = useState("50");
  const result = useMemo(
    () => estimateTm(sequence, Number(primerConcentration), Number(saltConcentration)),
    [primerConcentration, saltConcentration, sequence],
  );

  return (
    <section className="lab-card">
      <div className="lab-card-header">
        <div>
          <span className="lab-chip">Primer</span>
          <h2>Primer Tm Calculator</h2>
        </div>
      </div>
      <label className="lab-field">
        <span>Primer sequence</span>
        <textarea
          rows="8"
          value={sequence}
          onChange={(event) => setSequence(event.target.value)}
          placeholder="Paste a primer sequence. Non-DNA characters are ignored."
        />
      </label>
      <div className="lab-form-grid">
        <label className="lab-field">
          <span>Primer concentration (nM)</span>
          <input
            type="number"
            min="1"
            step="1"
            value={primerConcentration}
            onChange={(event) => setPrimerConcentration(event.target.value)}
          />
        </label>
        <label className="lab-field">
          <span>Salt concentration (mM)</span>
          <input
            type="number"
            min="1"
            step="1"
            value={saltConcentration}
            onChange={(event) => setSaltConcentration(event.target.value)}
          />
        </label>
      </div>
      {result.error ? (
        <p className="lab-error">{result.error}</p>
      ) : (
        <>
          <div className="lab-sequence-box">
            <strong>Normalized</strong>
            <code>{result.normalized || "-"}</code>
          </div>
          <div className="lab-metric-grid">
            <Metric label="Length" value={result.length ? `${result.length} nt` : "-"} />
            <Metric label="GC%" value={result.length ? `${result.gcPercent.toFixed(1)}%` : "-"} />
            <Metric label="Tm (NN)" value={result.length ? `${result.tmNearestNeighbor.toFixed(2)} °C` : "-"} />
            <Metric label="Tm (Wallace)" value={result.length ? `${result.tmWallace.toFixed(2)} °C` : "-"} />
            <Metric
              label="Suggested annealing"
              value={result.length ? `${result.recommendedAnnealing.toFixed(2)} °C` : "-"}
            />
          </div>
        </>
      )}
    </section>
  );
}

function DnaSequenceCard() {
  const [sequence, setSequence] = useState("");
  const [copiedLabel, setCopiedLabel] = useState("");
  const normalized = useMemo(() => normalizeSequence(sequence), [sequence]);
  const reversed = useMemo(() => reverseSequence(normalized), [normalized]);
  const complemented = useMemo(() => complementSequence(normalized), [normalized]);
  const reverseComplemented = useMemo(() => reverseComplementSequence(normalized), [normalized]);

  async function handleCopy(label, value) {
    if (!value) return;
    try {
      await copyToClipboard(value);
      setCopiedLabel(label);
      window.setTimeout(() => setCopiedLabel(""), 1400);
    } catch {
      setCopiedLabel("");
    }
  }

  return (
    <section className="lab-card">
      <div className="lab-card-header">
        <div>
          <span className="lab-chip">Sequence</span>
          <h2>DNA Sequence Tools</h2>
        </div>
      </div>
      <label className="lab-field">
        <span>DNA sequence</span>
        <textarea
          rows="8"
          value={sequence}
          onChange={(event) => setSequence(event.target.value)}
          placeholder="Paste a DNA sequence to generate normalized, reverse, complement, and reverse-complement forms."
        />
      </label>
      <div className="lab-metric-grid compact">
        <Metric label="Length" value={normalized ? `${normalized.length} nt` : "-"} />
        <Metric label="GC%" value={normalized ? `${gcContent(normalized).toFixed(1)}%` : "-"} />
      </div>
      <SequenceResult
        label="Normalized"
        value={normalized}
        copied={copiedLabel === "Normalized"}
        onCopy={() => handleCopy("Normalized", normalized)}
      />
      <SequenceResult
        label="Reverse"
        value={reversed}
        copied={copiedLabel === "Reverse"}
        onCopy={() => handleCopy("Reverse", reversed)}
      />
      <SequenceResult
        label="Complement"
        value={complemented}
        copied={copiedLabel === "Complement"}
        onCopy={() => handleCopy("Complement", complemented)}
      />
      <SequenceResult
        label="Reverse complement"
        value={reverseComplemented}
        copied={copiedLabel === "Reverse complement"}
        onCopy={() => handleCopy("Reverse complement", reverseComplemented)}
      />
    </section>
  );
}

function Metric({ label, value }) {
  return (
    <div className="lab-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SequenceResult({ label, value, onCopy, copied }) {
  return (
    <div className="sequence-result">
      <div className="sequence-result-top">
        <strong>{label}</strong>
        <button type="button" className="ghost" onClick={onCopy} disabled={!value}>
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <code>{value || "-"}</code>
    </div>
  );
}

function MolecularLabModule({ moduleId }) {
  if (moduleId === "primer_tm") return <PrimerTmWorkbench />;
  if (moduleId === "primer_pair") return <PrimerPairWorkbench />;
  if (moduleId === "oligo_screen") return <OligoScreenWorkbench />;
  if (moduleId === "dna_tools") return <DnaToolsWorkbench />;
  if (moduleId === "transcription") return <TranscriptionWorkbench />;
  if (moduleId === "translation") return <TranslationWorkbench />;
  if (moduleId === "restriction_scan") return <RestrictionScanWorkbench />;
  return null;
}

function HighlightedSequenceInput({ value, onChange, placeholder, rows = 8, mode = "dna" }) {
  return (
    <div className={`sequence-editor ${mode === "rna" ? "rna" : "dna"}`}>
      <textarea rows={rows} value={value} onChange={onChange} placeholder={placeholder} spellCheck="false" />
      <div className="sequence-editor-preview">
        <span>Invalid character preview</span>
        <pre aria-hidden="true" className="sequence-editor-highlight">
          {renderHighlightedSequence(value, mode)}
        </pre>
      </div>
    </div>
  );
}

function renderHighlightedSequence(value, mode) {
  const source = String(value || "");
  return source.split("").map((char, index) => {
    const upper = char.toUpperCase();
    const valid = /\s/.test(char) || (mode === "rna" ? /[AUCGN]/.test(upper) : /[ATCGUN]/.test(upper));
    return (
      <span key={`${char}-${index}`} className={valid ? "" : "invalid"}>
        {char}
      </span>
    );
  });
}

function PrimerTmWorkbench() {
  const [sequence, setSequence] = useState("");
  const [primerConcentration, setPrimerConcentration] = useState("250");
  const [saltConcentration, setSaltConcentration] = useState("50");
  const result = useMemo(
    () => estimateTm(sequence, Number(primerConcentration), Number(saltConcentration)),
    [primerConcentration, saltConcentration, sequence],
  );

  return (
    <section className="lab-card">
      <label className="lab-field">
        <span>Primer sequence</span>
        <HighlightedSequenceInput
          rows={8}
          value={sequence}
          onChange={(event) => setSequence(event.target.value)}
          placeholder="Paste a primer sequence. Invalid symbols are highlighted."
        />
      </label>
      <div className="lab-form-grid">
        <label className="lab-field">
          <span>Primer concentration (nM)</span>
          <input type="number" min="1" step="1" value={primerConcentration} onChange={(event) => setPrimerConcentration(event.target.value)} />
        </label>
        <label className="lab-field">
          <span>Salt concentration (mM)</span>
          <input type="number" min="1" step="1" value={saltConcentration} onChange={(event) => setSaltConcentration(event.target.value)} />
        </label>
      </div>
      {result.error ? <p className="lab-error">{result.error}</p> : (
        <>
          <div className="lab-sequence-box">
            <strong>Normalized</strong>
            <code>{result.normalized || "-"}</code>
          </div>
          <div className="lab-metric-grid">
            <Metric label="Length" value={result.length ? `${result.length} nt` : "-"} />
            <Metric label="GC%" value={result.length ? `${result.gcPercent.toFixed(1)}%` : "-"} />
            <Metric label="Tm (NN)" value={result.length ? `${result.tmNearestNeighbor.toFixed(2)} degC` : "-"} />
            <Metric label="Tm (Wallace)" value={result.length ? `${result.tmWallace.toFixed(2)} degC` : "-"} />
            <Metric label="Suggested annealing" value={result.length ? `${result.recommendedAnnealing.toFixed(2)} degC` : "-"} />
          </div>
        </>
      )}
    </section>
  );
}

function PrimerPairWorkbench() {
  const [forward, setForward] = useState("");
  const [reverse, setReverse] = useState("");
  const [primerConcentration, setPrimerConcentration] = useState("250");
  const [saltConcentration, setSaltConcentration] = useState("50");
  const left = useMemo(() => estimateTm(forward, Number(primerConcentration), Number(saltConcentration)), [forward, primerConcentration, saltConcentration]);
  const right = useMemo(() => estimateTm(reverse, Number(primerConcentration), Number(saltConcentration)), [reverse, primerConcentration, saltConcentration]);
  const tmGap = !left.error && !right.error && left.length && right.length ? Math.abs(left.tmNearestNeighbor - right.tmNearestNeighbor) : null;

  return (
    <section className="lab-card">
      <div className="lab-form-grid">
        <label className="lab-field">
          <span>Forward primer</span>
          <HighlightedSequenceInput rows={6} value={forward} onChange={(event) => setForward(event.target.value)} placeholder="Forward primer" />
        </label>
        <label className="lab-field">
          <span>Reverse primer</span>
          <HighlightedSequenceInput rows={6} value={reverse} onChange={(event) => setReverse(event.target.value)} placeholder="Reverse primer" />
        </label>
      </div>
      <div className="lab-form-grid">
        <label className="lab-field">
          <span>Primer concentration (nM)</span>
          <input value={primerConcentration} onChange={(event) => setPrimerConcentration(event.target.value)} />
        </label>
        <label className="lab-field">
          <span>Salt concentration (mM)</span>
          <input value={saltConcentration} onChange={(event) => setSaltConcentration(event.target.value)} />
        </label>
      </div>
      <div className="lab-metric-grid">
        <Metric label="Forward Tm" value={!left.error && left.length ? `${left.tmNearestNeighbor.toFixed(2)} degC` : "-"} />
        <Metric label="Reverse Tm" value={!right.error && right.length ? `${right.tmNearestNeighbor.toFixed(2)} degC` : "-"} />
        <Metric label="Tm gap" value={tmGap !== null ? `${tmGap.toFixed(2)} degC` : "-"} />
        <Metric label="Forward GC%" value={!left.error && left.length ? `${left.gcPercent.toFixed(1)}%` : "-"} />
        <Metric label="Reverse GC%" value={!right.error && right.length ? `${right.gcPercent.toFixed(1)}%` : "-"} />
        <Metric label="Pair balance" value={tmGap === null ? "-" : tmGap <= 2 ? "Tight" : tmGap <= 5 ? "Usable" : "Poor"} />
      </div>
    </section>
  );
}

function OligoScreenWorkbench() {
  const [primerA, setPrimerA] = useState("");
  const [primerB, setPrimerB] = useState("");
  const result = useMemo(() => screenOligos(primerA, primerB), [primerA, primerB]);

  return (
    <section className="lab-card">
      <div className="lab-form-grid">
        <label className="lab-field">
          <span>Primer A</span>
          <HighlightedSequenceInput rows={6} value={primerA} onChange={(event) => setPrimerA(event.target.value)} placeholder="Primer A" />
        </label>
        <label className="lab-field">
          <span>Primer B (optional)</span>
          <HighlightedSequenceInput rows={6} value={primerB} onChange={(event) => setPrimerB(event.target.value)} placeholder="Leave blank to reuse primer A" />
        </label>
      </div>
      <div className="lab-risk-grid">
        <RiskCard title="Hairpin" data={result.hairpin} />
        <RiskCard title="Self-dimer" data={result.selfDimer} />
        <RiskCard title="Cross-dimer" data={result.crossDimer} />
      </div>
    </section>
  );
}

function DnaToolsWorkbench() {
  const [sequence, setSequence] = useState("");
  const [copiedLabel, setCopiedLabel] = useState("");
  const normalized = useMemo(() => normalizeSequence(sequence), [sequence]);
  const reversed = useMemo(() => reverseSequence(normalized), [normalized]);
  const complemented = useMemo(() => complementSequence(normalized), [normalized]);
  const reverseComplemented = useMemo(() => reverseComplementSequence(normalized), [normalized]);

  async function handleCopy(label, value) {
    if (!value) return;
    try {
      await copyToClipboard(value);
      setCopiedLabel(label);
      window.setTimeout(() => setCopiedLabel(""), 1400);
    } catch {
      setCopiedLabel("");
    }
  }

  return (
    <section className="lab-card">
      <label className="lab-field">
        <span>DNA sequence</span>
        <HighlightedSequenceInput rows={8} value={sequence} onChange={(event) => setSequence(event.target.value)} placeholder="Paste a DNA sequence." />
      </label>
      <div className="lab-metric-grid compact">
        <Metric label="Length" value={normalized ? `${normalized.length} nt` : "-"} />
        <Metric label="GC%" value={normalized ? `${gcContent(normalized).toFixed(1)}%` : "-"} />
      </div>
      <SequenceResult label="Normalized" value={normalized} copied={copiedLabel === "Normalized"} onCopy={() => handleCopy("Normalized", normalized)} />
      <SequenceResult label="Reverse" value={reversed} copied={copiedLabel === "Reverse"} onCopy={() => handleCopy("Reverse", reversed)} />
      <SequenceResult label="Complement" value={complemented} copied={copiedLabel === "Complement"} onCopy={() => handleCopy("Complement", complemented)} />
      <SequenceResult label="Reverse complement" value={reverseComplemented} copied={copiedLabel === "Reverse complement"} onCopy={() => handleCopy("Reverse complement", reverseComplemented)} />
    </section>
  );
}

function TranscriptionWorkbench() {
  const [dna, setDna] = useState("");
  const [rna, setRna] = useState("");
  const dnaNormalized = useMemo(() => normalizeSequence(dna), [dna]);
  const rnaNormalized = useMemo(() => normalizeRnaSequence(rna), [rna]);

  return (
    <section className="lab-card">
      <div className="lab-form-grid">
        <label className="lab-field">
          <span>DNA sequence</span>
          <HighlightedSequenceInput rows={7} value={dna} onChange={(event) => setDna(event.target.value)} placeholder="Coding strand DNA" />
        </label>
        <label className="lab-field">
          <span>RNA sequence</span>
          <HighlightedSequenceInput rows={7} mode="rna" value={rna} onChange={(event) => setRna(event.target.value)} placeholder="mRNA sequence" />
        </label>
      </div>
      <SequenceResult label="DNA -> RNA" value={dnaNormalized ? dnaToRna(dnaNormalized) : ""} onCopy={() => copyToClipboard(dnaToRna(dnaNormalized))} copied={false} />
      <SequenceResult label="RNA -> DNA" value={rnaNormalized ? rnaToDna(rnaNormalized) : ""} onCopy={() => copyToClipboard(rnaToDna(rnaNormalized))} copied={false} />
    </section>
  );
}

function TranslationWorkbench() {
  const [sequence, setSequence] = useState("");
  const [frame, setFrame] = useState("1");
  const [strand, setStrand] = useState("forward");
  const source = useMemo(() => {
    const normalized = normalizeSequence(sequence);
    return strand === "reverse" ? reverseComplementSequence(normalized) : normalized;
  }, [sequence, strand]);
  const translated = useMemo(() => translateSequence(source, Number(frame)), [source, frame]);
  const orfs = useMemo(() => [...findOrfs(sequence, "forward"), ...findOrfs(sequence, "reverse")].slice(0, 12), [sequence]);

  return (
    <section className="lab-card">
      <label className="lab-field">
        <span>DNA/RNA sequence</span>
        <HighlightedSequenceInput rows={8} value={sequence} onChange={(event) => setSequence(event.target.value)} placeholder="Paste DNA or RNA. U is accepted." />
      </label>
      <div className="lab-form-grid">
        <label className="lab-field">
          <span>Frame</span>
          <select value={frame} onChange={(event) => setFrame(event.target.value)}>
            <option value="1">Frame 1</option>
            <option value="2">Frame 2</option>
            <option value="3">Frame 3</option>
          </select>
        </label>
        <label className="lab-field">
          <span>Strand</span>
          <select value={strand} onChange={(event) => setStrand(event.target.value)}>
            <option value="forward">Forward</option>
            <option value="reverse">Reverse complement</option>
          </select>
        </label>
      </div>
      <SequenceResult label="Translated peptide" value={translated} onCopy={() => copyToClipboard(translated)} copied={false} />
      <div className="orf-list">
        {orfs.length ? orfs.map((orf, index) => (
          <div key={`${orf.strand}-${orf.frame}-${orf.start}-${index}`} className="orf-row">
            <strong>{orf.strand} / frame {orf.frame}</strong>
            <span>{orf.start}-{orf.end} ({orf.lengthNt} nt)</span>
            <code>{orf.peptide}</code>
          </div>
        )) : <p className="muted">No complete ORF found yet.</p>}
      </div>
    </section>
  );
}

function RestrictionScanWorkbench() {
  const [sequence, setSequence] = useState("");
  const hits = useMemo(() => scanRestrictionSites(sequence), [sequence]);

  return (
    <section className="lab-card">
      <label className="lab-field">
        <span>DNA sequence</span>
        <HighlightedSequenceInput rows={8} value={sequence} onChange={(event) => setSequence(event.target.value)} placeholder="Paste a DNA sequence to scan common restriction sites." />
      </label>
      <div className="restriction-table">
        {hits.length ? hits.map((hit) => (
          <div key={hit.name} className="restriction-row">
            <strong>{hit.name}</strong>
            <span>{hit.site}</span>
            <span>{hit.count} site(s)</span>
            <code>{hit.positions.join(", ")}</code>
          </div>
        )) : <p className="muted">No common sites detected in the current panel.</p>}
      </div>
    </section>
  );
}

function RiskCard({ title, data }) {
  return (
    <div className={`risk-card risk-${String(data.risk || "").toLowerCase()}`}>
      <div className="sequence-result-top">
        <strong>{title}</strong>
        <span className="risk-badge">{data.risk}</span>
      </div>
      <div className="lab-metric-grid compact">
        <Metric label="Longest seed" value={data.matchLength ? `${data.matchLength} bp` : "-"} />
        <Metric label="3' match" value={data.threePrimeMatch ? `${data.threePrimeMatch} bp` : "-"} />
      </div>
      <code>{data.seed || "-"}</code>
    </div>
  );
}

