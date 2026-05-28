export function nextAnalysisOptions(node, detail) {
  if (node.status !== "completed") return [];
  if (node.id === "upload_expression") {
    const hasQcGate = detail?.graph.edges.some(
      (edge) => edge.source === "upload_expression" && edge.target.startsWith("qc__"),
    );
    return hasQcGate ? [] : [{ type: "qc", label: "Multi-sample QC" }];
  }
  if (node.id.startsWith("qc__")) {
    const uploadNode = detail?.graph.nodes.find((item) => item.id === "upload_expression");
    const capabilities = new Set(
      uploadNode?.output?.meta?.capabilities || [
        "sample_correlation",
        "expression_heatmap",
        "gene_expression",
        "pca",
        "diff_analysis",
        "multigroup_differential",
        "wgcna",
      ],
    );
    const qcPassedSampleCount = Number(node.output?.meta?.passed_sample_count || node.output?.meta?.sample_count || 0);
    if (qcPassedSampleCount > 20) {
      capabilities.add("wgcna");
    } else {
      capabilities.delete("wgcna");
    }
    const createdFromQc = (type, matcher) => {
      if (!capabilities.has(type)) return true;
      return detail?.graph.edges.some((edge) => edge.source === node.id && matcher(edge.target));
    };
    const hasPca = createdFromQc("pca", (target) => target.startsWith("pca__"));
    const hasCorrelation = createdFromQc("sample_correlation", (target) => target.startsWith("correlation__"));
    const hasExpressionHeatmap = createdFromQc("expression_heatmap", (target) =>
      target.startsWith("expression_heatmap__"),
    );
    const hasSelector = createdFromQc("diff_analysis", (target) => target === "diff_analysis");
    const hasMultigroup = createdFromQc("multigroup_differential", (target) =>
      target.startsWith("multigroup_differential__"),
    );
    const hasWgcna = createdFromQc("wgcna", (target) => target.startsWith("wgcna__"));
    const hasMetabolomicsStats = createdFromQc("metabolomics_statistics", (target) =>
      target.startsWith("metabolomics_statistics__"),
    );
    const options = [];
    if (!hasPca) options.push({ type: "pca", label: "PCA sample map" });
    if (!hasCorrelation) options.push({ type: "sample_correlation", label: "Sample correlation" });
    if (!hasExpressionHeatmap) options.push({ type: "expression_heatmap", label: "Top variable genes heatmap" });
    if (capabilities.has("gene_expression")) options.push({ type: "gene_expression", label: "Single gene expression" });
    if (!hasSelector) options.push({ type: "diff_analysis", label: "Pairwise differential analysis" });
    if (!hasMultigroup) options.push({ type: "multigroup_differential", label: "Multi-group differential plan" });
    if (!hasWgcna) options.push({ type: "wgcna", label: "WGCNA modules" });
    if (!hasMetabolomicsStats) options.push({ type: "metabolomics_statistics", label: "Metabolomics statistics" });
    return options;
  }
  if (node.id.startsWith("diff_analysis__")) {
    return [
      { type: "heatmap", label: "DE genes heatmap" },
      { type: "volcano", label: "Volcano plot" },
      { type: "diff_export", label: "Result export" },
      { type: "enrichment", label: "Enrichment analysis" },
    ];
  }
  return [];
}

export function summarizeOutput(output) {
  if (!output) return "None";
  const meta = output.meta || {};
  if (output.type === "expression_matrix" && meta.gene_count && meta.sample_count) {
    return `${meta.gene_count} genes / ${meta.sample_count} samples`;
  }
  if (output.type === "diff_result" && meta.comparison_label) {
    return meta.comparison_label;
  }
  if (output.type === "pca_plot" && meta.sample_count) {
    return `${meta.sample_count} samples PCA`;
  }
  if (output.type === "qc_report" && meta.sample_count) {
    if (typeof meta.passed_sample_count === "number") {
      return `${meta.passed_sample_count}/${meta.sample_count} samples passed QC`;
    }
    return `${meta.sample_count} samples QC`;
  }
  if (output.type === "sample_correlation_plot" && meta.sample_count) {
    return `${meta.sample_count} sample correlation`;
  }
  if (output.type === "expression_heatmap_plot" && meta.gene_count) {
    return `${meta.gene_count} gene heatmap`;
  }
  if (output.type === "gene_expression_plot" && meta.gene) {
    return meta.gene;
  }
  if (output.type === "wgcna_result" && meta.module_count) {
    return `${meta.module_count} modules / ${meta.gene_count || 0} genes`;
  }
  if (output.type === "metabolomics_statistics_result" && meta.metabolite_count) {
    return `${meta.metabolite_count} metabolites / ${meta.sample_count || 0} samples`;
  }
  if (output.type === "diff_export" && meta.row_count) {
    return `${meta.row_count} result rows`;
  }
  if (output.type === "planned_analysis" && meta.analysis_family) {
    return `${meta.analysis_family} planned`;
  }
  return output.type;
}
