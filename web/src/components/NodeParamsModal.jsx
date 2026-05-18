import { useState } from "react";

import { Modal } from "./Modal.jsx";

const QC_PRESET_VALUES = {
  loose: {
    min_total_ratio: 0.15,
    max_zero_ratio: 0.7,
    min_detected_genes: 500,
    max_distribution_mad: 5,
    max_value_iqr_multiplier: 3,
  },
  normal: {
    min_total_ratio: 0.25,
    max_zero_ratio: 0.5,
    min_detected_genes: 1000,
    max_distribution_mad: 3.5,
    max_value_iqr_multiplier: 1.5,
  },
  strict: {
    min_total_ratio: 0.4,
    max_zero_ratio: 0.35,
    min_detected_genes: 1500,
    max_distribution_mad: 2.5,
    max_value_iqr_multiplier: 1,
  },
};

const QC_PRESETS = [
  { id: "loose", title: "Loose", text: "Only obvious failures" },
  { id: "normal", title: "Normal", text: "Balanced default" },
  { id: "strict", title: "Strict", text: "More outlier removal" },
];

function toFormValues(values) {
  return {
    min_total_ratio: String(values.min_total_ratio),
    max_zero_ratio: String(values.max_zero_ratio),
    min_detected_genes: String(values.min_detected_genes),
    max_distribution_mad: String(values.max_distribution_mad),
    max_value_iqr_multiplier: String(values.max_value_iqr_multiplier),
  };
}

export function NodeParamsModal({ node, onClose, onSubmit }) {
  const defaults = {
    qc_preset: "normal",
    ...QC_PRESET_VALUES.normal,
    ...(node.default_params || {}),
    ...(node.params || {}),
  };
  const [preset, setPreset] = useState(defaults.qc_preset || "normal");
  const [values, setValues] = useState(toFormValues(defaults));
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  const applyPreset = (nextPreset) => {
    setPreset(nextPreset);
    setValues(toFormValues(QC_PRESET_VALUES[nextPreset] || QC_PRESET_VALUES.normal));
  };

  const submit = async (event) => {
    event.preventDefault();
    setRunning(true);
    setError("");
    try {
      await onSubmit({
        qc_preset: preset,
        min_total_ratio: Number(values.min_total_ratio),
        max_zero_ratio: Number(values.max_zero_ratio),
        min_detected_genes: Number.parseInt(values.min_detected_genes, 10),
        max_distribution_mad: Number(values.max_distribution_mad),
        max_value_iqr_multiplier: Number(values.max_value_iqr_multiplier),
      });
    } catch (err) {
      setError(err.message);
      setRunning(false);
    }
  };

  return (
    <Modal onClose={onClose}>
      <form className="modal node-param-modal" onSubmit={submit}>
        <h2>QC parameters</h2>
        <p>Choose a QC strictness preset. Advanced thresholds are optional and should be reviewed by dataset.</p>
        <div className="qc-preset-grid">
          {QC_PRESETS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`qc-preset ${preset === item.id ? "active" : ""}`}
              onClick={() => applyPreset(item.id)}
            >
              <strong>{item.title}</strong>
              <span>{item.text}</span>
            </button>
          ))}
        </div>
        <button type="button" className="advanced-toggle" onClick={() => setShowAdvanced((value) => !value)}>
          {showAdvanced ? "Hide advanced parameters" : "Show advanced parameters"}
        </button>
        {showAdvanced ? (
          <div className="advanced-params">
            <label>
              Minimum total expression ratio
              <input
                type="number"
                min="0"
                max="1"
                step="0.05"
                value={values.min_total_ratio}
                onChange={(event) => setValues((current) => ({ ...current, min_total_ratio: event.target.value }))}
              />
            </label>
            <label>
              Maximum zero ratio
              <input
                type="number"
                min="0"
                max="1"
                step="0.05"
                value={values.max_zero_ratio}
                onChange={(event) => setValues((current) => ({ ...current, max_zero_ratio: event.target.value }))}
              />
            </label>
            <label>
              Maximum distribution outlier score
              <input
                type="number"
                min="0"
                step="0.5"
                value={values.max_distribution_mad}
                onChange={(event) => setValues((current) => ({ ...current, max_distribution_mad: event.target.value }))}
              />
            </label>
            <label>
              Max value IQR multiplier
              <input
                type="number"
                min="0"
                step="0.25"
                value={values.max_value_iqr_multiplier}
                onChange={(event) =>
                  setValues((current) => ({ ...current, max_value_iqr_multiplier: event.target.value }))
                }
              />
            </label>
            <label>
              Minimum detected genes
              <input
                type="number"
                min="0"
                step="100"
                value={values.min_detected_genes}
                onChange={(event) => setValues((current) => ({ ...current, min_detected_genes: event.target.value }))}
              />
            </label>
          </div>
        ) : null}
        {error ? <p className="modal-error">{error}</p> : null}
        <div className="modal-actions">
          <button type="button" className="ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="primary compact" disabled={running}>
            {running ? "Running..." : "Run QC"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
