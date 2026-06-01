import { Handle, Position } from "@xyflow/react";

import { formatBytes, formatDateTime, outputUrl } from "../workflow/format.js";
import { dataProfile, nextAnalysisOptions, summarizeOutput } from "../workflow/options.js";
import { statusLabel } from "../workflow/status.js";

export function AnalysisNode({ data }) {
  const node = data.node;
  const output = summarizeOutput(node.output);
  const options = nextAnalysisOptions(node, data.detail);
  const canRun = node.id === "diff_analysis" || node.status === "ready" || node.status === "failed";
  const previewUrl = node.output?.meta?.preview_file
    ? outputUrl(data.detail.task.task_id, node.output.meta.preview_file)
    : null;
  const canOpenResult = Boolean(node.output?.meta?.html_file);
  const recognizedMeta = node.output?.meta?.data_type ? node.output.meta : null;
  const recognizedProfile = recognizedMeta ? dataProfile(recognizedMeta) : null;
  const recognizedFeatureCount = recognizedMeta?.metabolite_count || recognizedMeta?.gene_count || 0;
  const uploadedInputs = node.params?.uploaded_inputs || {};
  const uploadedInput = uploadedInputs.expression_matrix;
  const uploadBatch = uploadedInputs.upload_batch;
  const uploadedFileCount = uploadBatch?.files?.length || (uploadedInput ? 1 : 0);
  const dataFileCount = uploadBatch?.data_files?.length || (uploadedInput ? 1 : 0);
  const metadataFileCount = uploadBatch?.metadata_files?.length || (uploadedInputs.sample_metadata ? 1 : 0);
  const ignoredFiles = uploadBatch?.ignored_files || [];
  const supportFileCount = ignoredFiles.filter((item) => item.reason?.startsWith("metabolights_")).length;
  const ignoredFileCount = Math.max(0, ignoredFiles.length - supportFileCount);
  const extraDataCount = uploadBatch?.extra_data_files?.length || 0;
  const uploadBatchFiles = uploadBatch?.files
    ? uploadBatch.files.map((file) => {
        const filename = file.filename || "";
        let role = "已上传";
        const ignoredFile = ignoredFiles.find((item) => item.filename === filename);
        if (filename === uploadBatch.selected_data_file) {
          role = "主数据";
        } else if (uploadBatch.metadata_files?.includes(filename)) {
          role = "metadata";
        } else if (uploadBatch.extra_data_files?.some((item) => item.filename === filename)) {
          role = "备用数据";
        } else if (ignoredFile?.reason?.startsWith("metabolights_")) {
          role = "辅助文件";
        } else if (ignoredFile) {
          role = "未识别";
        } else if (uploadBatch.data_files?.includes(filename)) {
          role = "数据表";
        }
        return { filename, role, size: file.size };
      })
    : [];
  const uploadStateLabel = recognizedMeta
    ? "数据已识别"
    : uploadedInput
    ? uploadedFileCount > 1
      ? `已上传 ${uploadedFileCount} 个文件`
      : "数据已识别："
    : "等待上传";

  return (
    <article className={`analysis-node ${node.status} ${uploadedInput ? "has-uploaded-input" : ""}`}>
      <Handle type="target" position={Position.Left} />
      <div className="node-topline">
        <span className="status-dot" />
        <span className="status">{statusLabel[node.status] || node.status}</span>
        <button className="node-delete" onClick={() => data.onDelete(node.id)} title="删除节点">
          x
        </button>
      </div>
      <h3 title={node.description}>{node.name}</h3>
      <small>输出：{output}</small>
      {node.id === "upload_expression" ? (
        <div className="upload-controls nodrag">
          {uploadedInput ? (
            <label className="uploaded-file-card upload-file-picker">
              <span>{uploadStateLabel}</span>
              {recognizedMeta ? (
                <>
                  <strong>{recognizedProfile.fullLabel}</strong>
                  <small>
                    {recognizedFeatureCount ? `${recognizedFeatureCount} ${recognizedProfile.featureLabel} / ` : ""}
                    {recognizedMeta.sample_count || 0} samples
                  </small>
                </>
              ) : (
                <>
                  <strong title={uploadedInput.filename}>主数据：{uploadedInput.filename}</strong>
                  <small>
                    {formatBytes(uploadedInput.size)}
                    {uploadedInput.uploaded_at ? ` 上传于 ${formatDateTime(uploadedInput.uploaded_at)}` : ""}
                  </small>
                  <div className="upload-batch-summary">
                    <span>数据表 {dataFileCount}</span>
                    <span>metadata {metadataFileCount}</span>
                    {extraDataCount ? <span>备用数据 {extraDataCount}</span> : null}
                    {supportFileCount ? <span>辅助文件 {supportFileCount}</span> : null}
                    {ignoredFileCount ? <span>未识别 {ignoredFileCount}</span> : null}
                  </div>
                  <div className="upload-batch-files">
                    {uploadBatchFiles.map((file) => (
                      <span className={`upload-file-role ${file.role === "未识别" ? "ignored" : ""}`} key={file.filename} title={file.filename}>
                        <em>{file.role}</em>
                        <strong>{file.filename}</strong>
                      </span>
                    ))}
                  </div>
                </>
              )}
              <input
                type="file"
                accept=".csv,.tsv,.txt,.xlsx,.xlsm,.zip,.tar,.tgz,.gz,.tar.gz"
                multiple
                onChange={(event) => {
                  data.onUploadInput("expression_matrix", event.target.files);
                  event.target.value = "";
                }}
              />
            </label>
          ) : (
            <label className="upload-empty-picker">
              上传数据
              <input
                type="file"
                accept=".csv,.tsv,.txt,.xlsx,.xlsm,.zip,.tar,.tgz,.gz,.tar.gz"
                multiple
                onChange={(event) => {
                  data.onUploadInput("expression_matrix", event.target.files);
                  event.target.value = "";
                }}
              />
            </label>
          )}
          {node.output?.meta?.sample_metadata_file ? (
            <button type="button" onClick={() => data.onEditGroups()}>
              编辑分组
            </button>
          ) : null}
        </div>
      ) : null}
      {node.id === "upload_expression" && (node.status === "running" || node.status === "failed") ? (
        <AgentProgress
          progress={node.params?.agent_progress}
          failed={node.status === "failed"}
          onOpenReport={() => data.onOpenAgentReport(node)}
        />
      ) : null}
      {previewUrl ? (
        <div className="result-preview nodrag">
          <button className="result-preview-main" type="button" onClick={() => data.onOpenResult(node)}>
            <img src={previewUrl} alt={`${node.name} 预览`} />
          </button>
          <div className="result-preview-footer">
            {canOpenResult ? <button type="button" onClick={() => data.onOpenResult(node)}>点击查看结果</button> : <span />}
          </div>
        </div>
      ) : null}
      <div className="node-actions">
        <button className="run" disabled={!canRun} onClick={() => data.onRun(node.id)}>
          {node.id === "diff_analysis" ? "创建下游分析" : node.status === "failed" ? "重新运行" : "运行节点"}
        </button>
        {options.length ? (
          <button className="add-next" onClick={() => data.onAddNext(node.id)} title="添加下游节点">
            +
          </button>
        ) : null}
      </div>
      <Handle type="source" position={Position.Right} />
    </article>
  );
}

function AgentProgress({ progress, failed, onOpenReport }) {
  const history = progress?.history || [];
  const currentStep = progress?.step || "queued";
  const steps = [
    { step: "inspect_file", label: "读取数据" },
    { step: "classify_data", label: "识别类型" },
    { step: "standardize_data", label: "标准化数据" },
    { step: "validate_output", label: "验证输出" },
  ];
  const activeIndex = steps.findIndex((item) => item.step === currentStep);
  const completedCount = history.filter((item) => item.status === "completed").length;
  const stepCount =
    progress?.status === "completed"
      ? steps.length
      : activeIndex >= 0
        ? activeIndex + 1
        : Math.min(completedCount + 1, steps.length);
  const lastDone = [...history].reverse().find((item) => item.status === "completed");
  return (
    <div className={`agent-progress compact ${failed ? "failed" : progress?.status || "running"}`}>
      <span className="agent-pulse" />
      <div className="agent-copy">
        <strong key={progress?.label || "Agent 正在运行"}>{progress?.label || "Agent 正在运行"}</strong>
        {lastDone && progress?.status !== "completed" ? <small>上一步：{lastDone.label}</small> : null}
      </div>
      <span className="agent-step-count">
        {stepCount}/{steps.length}
      </span>
      {failed ? (
        <button className="agent-report-link nodrag" type="button" onClick={onOpenReport}>
          查看报告
        </button>
      ) : null}
    </div>
  );
}
