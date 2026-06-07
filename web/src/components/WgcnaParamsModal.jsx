import { useState } from "react";

import { Button, Dialog } from "tdesign-react";

const NETWORK_TYPE_HELP = {
  signed: "signed：区分正负相关，负相关连接会被弱化；通常更适合表达共表达模块。",
  unsigned: "unsigned：只看相关强度，正相关和负相关都会形成连接；适合探索反向表达关系。",
  "signed hybrid": "signed hybrid：保留 signed 对正相关模块的偏好，同时比 signed 更宽松。",
};

export function WgcnaParamsModal({ node, onClose, onSubmit }) {
  const defaults = {
    gene_selection_mode: "fixed",
    max_genes: 2000,
    top_gene_percent: 25,
    min_module_size: 20,
    soft_power: 0,
    merge_cut_height: 0.25,
    network_type: "signed",
    ...(node.default_params || {}),
    ...(node.params || {}),
  };
  const [selectionMode, setSelectionMode] = useState(defaults.gene_selection_mode || "fixed");
  const [maxGenes, setMaxGenes] = useState(String(defaults.max_genes || 2000));
  const [topGenePercent, setTopGenePercent] = useState(String(defaults.top_gene_percent || 25));
  const [minModuleSize, setMinModuleSize] = useState(String(defaults.min_module_size || 20));
  const [softPower, setSoftPower] = useState(String(defaults.soft_power || 0));
  const [mergeCutHeight, setMergeCutHeight] = useState(String(defaults.merge_cut_height || 0.25));
  const [networkType, setNetworkType] = useState(defaults.network_type || "signed");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event) => {
    event.preventDefault();
    setRunning(true);
    setError("");
    try {
      await onSubmit({
        gene_selection_mode: selectionMode,
        max_genes: Number.parseInt(maxGenes, 10),
        top_gene_percent: Number(topGenePercent),
        min_module_size: Number.parseInt(minModuleSize, 10),
        soft_power: Number.parseInt(softPower, 10),
        merge_cut_height: Number(mergeCutHeight),
        network_type: networkType,
      });
    } catch (err) {
      setError(err.message);
      setRunning(false);
    }
  };

  return (
    <Dialog
      visible
      header="WGCNA parameters"
      width={720}
      placement="center"
      closeOnOverlayClick
      destroyOnClose
      footer={false}
      dialogClassName="td-workflow-dialog td-param-dialog"
      onClose={onClose}
      onCancel={onClose}
    >
      <form className="modal wgcna-param-modal" onSubmit={submit}>
        <p>选择进入共表达网络的高变基因数量。演示默认使用方差最大的前 2000 个基因，速度更稳定。</p>
        <div className="qc-preset-grid">
          <button
            type="button"
            className={`qc-preset ${selectionMode === "top_percent" ? "active" : ""}`}
            onClick={() => setSelectionMode("top_percent")}
          >
            <strong>Top variance percent</strong>
            <span>按方差排序后取前百分比，适合正式分析但更慢。</span>
          </button>
          <button
            type="button"
            className={`qc-preset ${selectionMode === "fixed" ? "active" : ""}`}
            onClick={() => setSelectionMode("fixed")}
          >
            <strong>Fixed gene count</strong>
            <span>取固定数量的高变基因，适合调试和演示。</span>
          </button>
        </div>
        {selectionMode === "top_percent" ? (
          <label>
            Top variable gene percent
            <small className="param-help">例如 25 表示使用方差最大的前 25% 基因。</small>
            <input
              type="number"
              min="1"
              max="100"
              step="1"
              value={topGenePercent}
              onChange={(event) => setTopGenePercent(event.target.value)}
            />
          </label>
        ) : (
          <label>
            Top variable genes
            <small className="param-help">演示建议 2000；正式分析可尝试 5000-10000。</small>
            <input
              type="number"
              min="50"
              max="10000"
              step="1"
              value={maxGenes}
              onChange={(event) => setMaxGenes(event.target.value)}
            />
          </label>
        )}
        <div className="advanced-params">
          <label>
            Minimum module size
            <small className="param-help">模块最少基因数；越大模块越少，越小越容易产生碎片模块。</small>
            <input
              type="number"
              min="4"
              max="200"
              step="1"
              value={minModuleSize}
              onChange={(event) => setMinModuleSize(event.target.value)}
            />
          </label>
          <label>
            Soft power
            <small className="param-help">0 表示自动选择；手动值会直接用于构建邻接网络。</small>
            <input
              type="number"
              min="0"
              max="30"
              step="1"
              value={softPower}
              onChange={(event) => setSoftPower(event.target.value)}
            />
          </label>
          <label>
            Merge cut height
            <small className="param-help">模块合并阈值；越小合并越少，越大相似模块越容易合并。</small>
            <input
              type="number"
              min="0.05"
              max="0.75"
              step="0.05"
              value={mergeCutHeight}
              onChange={(event) => setMergeCutHeight(event.target.value)}
            />
          </label>
          <label>
            Network type
            <small className="param-help">{NETWORK_TYPE_HELP[networkType] || NETWORK_TYPE_HELP.signed}</small>
            <select value={networkType} onChange={(event) => setNetworkType(event.target.value)}>
              <option value="signed">signed</option>
              <option value="unsigned">unsigned</option>
              <option value="signed hybrid">signed hybrid</option>
            </select>
          </label>
        </div>
        {error ? <p className="modal-error">{error}</p> : null}
        <div className="modal-actions">
          <Button type="button" variant="outline" shape="round" onClick={onClose}>
            Cancel
          </Button>
          <Button theme="primary" shape="round" type="submit" loading={running} disabled={running}>
            {running ? "Running..." : "Run WGCNA"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
