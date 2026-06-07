import { useState } from "react";

import { Button, Dialog } from "tdesign-react";

const QC_PRESET_VALUES = {
  expression: {
    loose: {
      min_total_ratio: 0.15,
      max_zero_ratio: 0.7,
      min_detected_features: 500,
      max_distribution_mad: 5,
      max_value_iqr_multiplier: 3,
    },
    normal: {
      min_total_ratio: 0.25,
      max_zero_ratio: 0.5,
      min_detected_features: 1000,
      max_distribution_mad: 3.5,
      max_value_iqr_multiplier: 1.5,
    },
    strict: {
      min_total_ratio: 0.4,
      max_zero_ratio: 0.35,
      min_detected_features: 1500,
      max_distribution_mad: 2.5,
      max_value_iqr_multiplier: 1,
    },
  },
  metabolomics: {
    loose: {
      min_total_ratio: 0.1,
      max_zero_ratio: 0.75,
      min_detected_features: 80,
      max_distribution_mad: 6,
      max_value_iqr_multiplier: 5,
    },
    normal: {
      min_total_ratio: 0.2,
      max_zero_ratio: 0.6,
      min_detected_features: 110,
      max_distribution_mad: 4.5,
      max_value_iqr_multiplier: 3,
    },
    strict: {
      min_total_ratio: 0.3,
      max_zero_ratio: 0.45,
      min_detected_features: 145,
      max_distribution_mad: 3,
      max_value_iqr_multiplier: 2,
    },
  },
};

const QC_PRESETS = [
  { id: "loose", title: "Loose", text: "Only obvious failures" },
  { id: "normal", title: "Normal", text: "Balanced default" },
  { id: "strict", title: "Strict", text: "More outlier removal" },
];

const METABOLOMICS_PROCESSING_DEFAULTS = {
  normalize_after_qc: true,
  impute_method: "half_min",
  normalization_method: "tic_median",
  transform: "log2",
  scaling: "pareto",
  treat_zero_as_missing: true,
};

function toFormValues(values) {
  return {
    min_total_ratio: String(values.min_total_ratio),
    max_zero_ratio: String(values.max_zero_ratio),
    min_detected_features: String(values.min_detected_features ?? values.min_detected_genes),
    max_distribution_mad: String(values.max_distribution_mad),
    max_value_iqr_multiplier: String(values.max_value_iqr_multiplier),
  };
}

function qcProfileFromDetail(detail) {
  const uploadNode = detail?.graph?.nodes?.find((item) => item.id === "upload_expression");
  return ["metabolomics_matrix", "proteomics_matrix"].includes(uploadNode?.output?.meta?.data_type)
    ? "metabolomics"
    : "expression";
}

export function NodeParamsModal({ node, detail, onClose, onSubmit }) {
  const qcProfile = node.default_params?.qc_profile || node.params?.qc_profile || qcProfileFromDetail(detail);
  const profilePresets = QC_PRESET_VALUES[qcProfile] || QC_PRESET_VALUES.expression;
  const defaults = {
    qc_preset: "normal",
    ...profilePresets.normal,
    ...(node.default_params || {}),
    ...(node.params || {}),
  };
  const [preset, setPreset] = useState(defaults.qc_preset || "normal");
  const [values, setValues] = useState(toFormValues(defaults));
  const [normalizeAfterQc, setNormalizeAfterQc] = useState(
    qcProfile === "metabolomics"
      ? Boolean(defaults.normalize_after_qc ?? METABOLOMICS_PROCESSING_DEFAULTS.normalize_after_qc)
      : false,
  );
  const [processing, setProcessing] = useState({
    ...METABOLOMICS_PROCESSING_DEFAULTS,
    ...defaults,
  });
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  const applyPreset = (nextPreset) => {
    setPreset(nextPreset);
    setValues(toFormValues(profilePresets[nextPreset] || profilePresets.normal));
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
        min_detected_features: Number.parseInt(values.min_detected_features, 10),
        min_detected_genes: Number.parseInt(values.min_detected_features, 10),
        max_distribution_mad: Number(values.max_distribution_mad),
        max_value_iqr_multiplier: Number(values.max_value_iqr_multiplier),
        normalize_after_qc: qcProfile === "metabolomics" ? normalizeAfterQc : false,
        impute_method: processing.impute_method,
        normalization_method: processing.normalization_method,
        transform: processing.transform,
        scaling: processing.scaling,
        treat_zero_as_missing: Boolean(processing.treat_zero_as_missing),
      });
    } catch (err) {
      setError(err.message);
      setRunning(false);
    }
  };

  return (
    <Dialog
      visible
      header="QC parameters"
      width={720}
      placement="center"
      closeOnOverlayClick
      destroyOnClose
      footer={false}
      dialogClassName="td-workflow-dialog td-param-dialog"
      onClose={onClose}
      onCancel={onClose}
    >
      <form className="modal node-param-modal" onSubmit={submit}>
        <p>Choose a QC strictness preset. Defaults are selected for the current {qcProfile} data profile.</p>
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
        <Button type="button" variant="text" className="advanced-toggle" onClick={() => setShowAdvanced((value) => !value)}>
          {showAdvanced ? "Hide advanced parameters" : "Show advanced parameters"}
        </Button>
        {qcProfile === "metabolomics" ? (
          <section className="metabolomics-processing">
            <label className="checkbox-line">
              <input
                type="checkbox"
                checked={normalizeAfterQc}
                onChange={(event) => setNormalizeAfterQc(event.target.checked)}
              />
              <span>
                <strong>Normalize / impute / scale after QC</strong>
                <small>Passed samples become the matrix used by PCA, heatmap, abundance, and differential nodes.</small>
              </span>
            </label>
            {normalizeAfterQc ? (
              <div className="processing-grid">
                <label>
                  Imputation
                  <select
                    value={processing.impute_method}
                    onChange={(event) => setProcessing((current) => ({ ...current, impute_method: event.target.value }))}
                  >
                    <option value="half_min">Half minimum</option>
                    <option value="median">Feature median</option>
                    <option value="zero">Zero</option>
                  </select>
                </label>
                <label>
                  Normalization
                  <select
                    value={processing.normalization_method}
                    onChange={(event) =>
                      setProcessing((current) => ({ ...current, normalization_method: event.target.value }))
                    }
                  >
                    <option value="tic_median">TIC median</option>
                    <option value="median">Median</option>
                    <option value="none">None</option>
                  </select>
                </label>
                <label>
                  Transform
                  <select
                    value={processing.transform}
                    onChange={(event) => setProcessing((current) => ({ ...current, transform: event.target.value }))}
                  >
                    <option value="log2">Log2</option>
                    <option value="log10">Log10</option>
                    <option value="none">None</option>
                  </select>
                </label>
                <label>
                  Scaling
                  <select
                    value={processing.scaling}
                    onChange={(event) => setProcessing((current) => ({ ...current, scaling: event.target.value }))}
                  >
                    <option value="pareto">Pareto</option>
                    <option value="auto">Auto</option>
                    <option value="none">None</option>
                  </select>
                </label>
                <label className="checkbox-line compact">
                  <input
                    type="checkbox"
                    checked={Boolean(processing.treat_zero_as_missing)}
                    onChange={(event) =>
                      setProcessing((current) => ({ ...current, treat_zero_as_missing: event.target.checked }))
                    }
                  />
                  <span>Treat zero as missing</span>
                </label>
              </div>
            ) : null}
          </section>
        ) : null}
        {showAdvanced ? (
          <div className="advanced-params">
            <label>
              Minimum total signal ratio
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
              Minimum detected features
              <input
                type="number"
                min="0"
                step={qcProfile === "metabolomics" ? "10" : "100"}
                value={values.min_detected_features}
                onChange={(event) => setValues((current) => ({ ...current, min_detected_features: event.target.value }))}
              />
            </label>
          </div>
        ) : null}
        {error ? <p className="modal-error">{error}</p> : null}
        <div className="modal-actions">
          <Button type="button" variant="outline" shape="round" onClick={onClose}>
            Cancel
          </Button>
          <Button theme="primary" shape="round" type="submit" loading={running} disabled={running}>
            {running ? "Running..." : "Run QC"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
