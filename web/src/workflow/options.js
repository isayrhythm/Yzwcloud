export function nextAnalysisOptions(node, detail) {
  if (node.status !== "completed") return [];
  if (node.id === "upload_expression") {
    const hasQcGate = detail?.graph.edges.some(
      (edge) => edge.source === "upload_expression" && edge.target.startsWith("qc__"),
    );
    const profile = dataProfile(node.output?.meta);
    return hasQcGate ? [] : [{ type: "qc", label: `${profile.shortLabel} QC` }];
  }
  if (node.id.startsWith("qc__")) {
    const uploadNode = detail?.graph.nodes.find((item) => item.id === "upload_expression");
    const profile = dataProfile(uploadNode?.output?.meta);
    if (profile.qcProfile === "metabolomics") {
      const created = (matcher) => detail?.graph.edges.some((edge) => edge.source === node.id && matcher(edge.target));
      const options = [];
      if (!created((target) => target.startsWith("pca__"))) options.push({ type: "pca", label: "PCA sample map" });
      if (!created((target) => target.startsWith("correlation__"))) {
        options.push({ type: "sample_correlation", label: "Sample correlation" });
      }
      if (!created((target) => target.startsWith("expression_heatmap__"))) {
        options.push({ type: "expression_heatmap", label: `Top variable ${profile.featureLabel} heatmap` });
      }
      if (!created((target) => target.startsWith("gene_expression__"))) {
        options.push({ type: "gene_expression", label: `Single ${profile.featureSingular} abundance` });
      }
      if (!created((target) => target.startsWith("metabolomics_differential__"))) {
        options.push({ type: "metabolomics_differential", label: `Differential ${profile.featureLabel}` });
      }
      return options;
    }
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
    if (capabilities.has("metabolomics_statistics")) {
      capabilities.add("metabolomics_differential");
    }
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
    const hasMetabolomicsDifferential = createdFromQc("metabolomics_differential", (target) =>
      target.startsWith("metabolomics_differential__") || target.startsWith("metabolomics_statistics__"),
    );
    const options = [];
    if (!hasPca) options.push({ type: "pca", label: "PCA sample map" });
    if (!hasCorrelation) options.push({ type: "sample_correlation", label: "Sample correlation" });
    if (!hasExpressionHeatmap) options.push({ type: "expression_heatmap", label: `Top variable ${profile.featureLabel} heatmap` });
    if (capabilities.has("gene_expression")) {
      const label = profile.qcProfile === "metabolomics" ? `Single ${profile.featureSingular} abundance` : "Single gene expression";
      options.push({ type: "gene_expression", label });
    }
    if (!hasSelector) options.push({ type: "diff_analysis", label: "Pairwise differential analysis" });
    if (!hasMultigroup) options.push({ type: "multigroup_differential", label: "Multi-group differential plan" });
    if (!hasWgcna) options.push({ type: "wgcna", label: "WGCNA modules" });
    if (!hasMetabolomicsDifferential) {
      options.push({ type: "metabolomics_differential", label: `${profile.shortLabel} differential analysis` });
    }
    return options;
  }
  if (node.id.startsWith("metabolomics_normalization__")) {
    const uploadNode = detail?.graph.nodes.find((item) => item.id === "upload_expression");
    const profile = dataProfile(uploadNode?.output?.meta);
    const created = (matcher) => detail?.graph.edges.some((edge) => edge.source === node.id && matcher(edge.target));
    const options = [];
    if (!created((target) => target.startsWith("pca__"))) options.push({ type: "pca", label: "PCA sample map" });
    if (!created((target) => target.startsWith("correlation__"))) {
      options.push({ type: "sample_correlation", label: "Sample correlation" });
    }
    if (!created((target) => target.startsWith("expression_heatmap__"))) {
      options.push({ type: "expression_heatmap", label: `Top variable ${profile.featureLabel} heatmap` });
    }
    if (!created((target) => target.startsWith("gene_expression__"))) {
      options.push({ type: "gene_expression", label: `Single ${profile.featureSingular} abundance` });
    }
    if (!created((target) => target.startsWith("metabolomics_differential__"))) {
      options.push({ type: "metabolomics_differential", label: `Differential ${profile.featureLabel}` });
    }
    return options;
  }
  if (node.id.startsWith("diff_analysis__") || node.id.startsWith("metabolomics_differential__")) {
    const isMetabolomics = node.id.startsWith("metabolomics_differential__");
    const profile = dataProfile(node.output?.meta);
    return [
      { type: "heatmap", label: isMetabolomics ? `Diff ${profile.featureSingular} heatmap` : "DE genes heatmap" },
      { type: "volcano", label: "Volcano plot" },
      { type: "enrichment", label: isMetabolomics ? "Pathway analysis" : "Enrichment analysis" },
    ];
  }
  return [];
}

export function summarizeOutput(output) {
  if (!output) return "None";
  const meta = output.meta || {};
  if (output.type === "expression_matrix" && meta.analysis_family === "metabolomics_normalization") {
    const profile = dataProfile(meta);
    const featureCount = meta.metabolite_count || meta.gene_count || 0;
    const steps = [meta.impute_method, meta.normalization_method, meta.transform, meta.scaling]
      .filter(Boolean)
      .join(" / ");
    return `${steps || "normalized"} / ${featureCount} ${profile.featureLabel} / ${meta.sample_count || 0} samples`;
  }
  if (output.type === "expression_matrix" && meta.data_type) {
    const profile = dataProfile(meta);
    const featureCount = meta.metabolite_count || meta.gene_count || 0;
    return `${profile.fullLabel}${featureCount ? ` / ${featureCount} ${profile.featureLabel}` : ""} / ${meta.sample_count || 0} samples`;
  }
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
      const suffix = meta.normalization_applied ? " + normalized" : "";
      return `${meta.passed_sample_count}/${meta.sample_count} samples passed QC${suffix}`;
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
  if (
    (output.type === "metabolomics_statistics_result" || output.type === "metabolomics_differential_result")
    && meta.metabolite_count
  ) {
    if (typeof meta.significant_metabolite_count === "number") {
      const profile = dataProfile(meta);
      return `${meta.significant_metabolite_count}/${meta.metabolite_count} significant ${profile.featureLabel}`;
    }
    const profile = dataProfile(meta);
    return `${meta.metabolite_count} ${profile.featureLabel} / ${meta.sample_count || 0} samples`;
  }
  if (output.type === "diff_export" && meta.row_count) {
    return `${meta.row_count} result rows`;
  }
  if (output.type === "planned_analysis" && meta.analysis_family) {
    return `${meta.analysis_family} planned`;
  }
  return output.type;
}

export function dataProfile(meta = {}) {
  if (meta.data_type === "metabolomics_matrix") {
    if (meta.assay_profile === "feature_intensity") {
      return {
        shortLabel: "Feature",
        fullLabel: "Feature intensity matrix",
        featureLabel: "features",
        featureSingular: "feature",
        qcProfile: "metabolomics",
        analyses: ["PCA", "Sample correlation", "Heatmap", "Feature abundance", "Differential analysis"],
      };
    }
    return {
      shortLabel: "Metabolomics",
      fullLabel: "Metabolomics matrix",
      featureLabel: "metabolites",
      featureSingular: "metabolite",
      qcProfile: "metabolomics",
      analyses: ["PCA", "Sample correlation", "Heatmap", "Metabolite abundance", "Differential analysis"],
    };
  }
  return {
    shortLabel: "Expression",
    fullLabel: "Expression matrix",
    featureLabel: "genes",
    featureSingular: "gene",
    qcProfile: "expression",
    analyses: ["PCA", "Sample correlation", "Heatmap", "Differential analysis", "WGCNA"],
  };
}
