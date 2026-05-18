import { useMemo, useState } from "react";

import { Modal } from "./Modal.jsx";

function conditionEntries(detail) {
  const uploadNode = detail?.graph?.nodes?.find((node) => node.id === "upload_expression");
  const counts = uploadNode?.output?.meta?.conditions || {};
  return Object.entries(counts).map(([condition, count]) => ({ condition, count }));
}

export function HeatmapParamsModal({ node, detail, onClose, onSubmit }) {
  const conditions = useMemo(() => conditionEntries(detail), [detail]);
  const defaultSelected = node.params?.selected_conditions?.length
    ? node.params.selected_conditions
    : conditions.map((item) => item.condition);
  const [selected, setSelected] = useState(defaultSelected);
  const [topGenes, setTopGenes] = useState(String(node.params?.top_genes || node.default_params?.top_genes || 40));
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  const toggleCondition = (condition) => {
    setSelected((current) =>
      current.includes(condition) ? current.filter((item) => item !== condition) : [...current, condition],
    );
  };

  const submit = async (event) => {
    event.preventDefault();
    if (selected.length === 0) {
      setError("Select at least one condition.");
      return;
    }
    setRunning(true);
    setError("");
    try {
      await onSubmit({
        selected_conditions: selected,
        top_genes: Number.parseInt(topGenes, 10),
      });
    } catch (err) {
      setError(err.message);
      setRunning(false);
    }
  };

  return (
    <Modal onClose={onClose}>
      <form className="modal heatmap-param-modal" onSubmit={submit}>
        <h2>Heatmap samples</h2>
        <p>Select which sample groups enter the top-variable-gene clustering heatmap.</p>
        <div className="condition-choice-grid">
          {conditions.map((item) => (
            <label key={item.condition} className="condition-choice">
              <input
                type="checkbox"
                checked={selected.includes(item.condition)}
                onChange={() => toggleCondition(item.condition)}
              />
              <span>{item.condition}</span>
              <strong>{item.count}</strong>
            </label>
          ))}
        </div>
        <label>
          Top variable genes
          <input
            type="number"
            min="5"
            max="200"
            step="5"
            value={topGenes}
            onChange={(event) => setTopGenes(event.target.value)}
          />
        </label>
        {error ? <p className="modal-error">{error}</p> : null}
        <div className="modal-actions">
          <button type="button" className="ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="primary compact" disabled={running}>
            {running ? "Running..." : "Run heatmap"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
