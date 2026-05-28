suppressPackageStartupMessages({
  library(WGCNA)
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 8) {
  stop("Usage: run_wgcna.R <matrix.csv> <metadata.csv> <output_prefix> <max_genes> <min_module_size> <soft_power> <merge_cut_height> <network_type> [gene_selection_mode] [gene_selection_value]")
}

matrix_path <- args[[1]]
metadata_path <- args[[2]]
output_prefix <- args[[3]]
max_genes <- as.integer(args[[4]])
min_module_size <- as.integer(args[[5]])
requested_power <- as.integer(args[[6]])
merge_cut_height <- as.numeric(args[[7]])
network_type <- args[[8]]
gene_selection_mode <- if (length(args) >= 9) args[[9]] else "fixed"
gene_selection_value <- if (length(args) >= 10) as.numeric(args[[10]]) else max_genes
if (!gene_selection_mode %in% c("fixed", "top_percent")) {
  gene_selection_mode <- "top_percent"
}
if (!is.finite(gene_selection_value) || gene_selection_value <= 0) {
  gene_selection_value <- if (gene_selection_mode == "top_percent") 25 else max_genes
}

options(stringsAsFactors = FALSE)
allowWGCNAThreads()

matrix_df <- read.csv(matrix_path, check.names = FALSE)
metadata <- read.csv(metadata_path, check.names = FALSE)
required_meta <- c("sample", "condition")
if (!all(required_meta %in% names(metadata))) {
  stop("sample metadata must contain sample and condition columns")
}

sample_names <- intersect(metadata$sample, names(matrix_df))
if (length(sample_names) <= 20) {
  stop("WGCNA requires more than 20 matching samples")
}
metadata <- metadata[match(sample_names, metadata$sample), , drop = FALSE]

gene_col <- if ("gene" %in% names(matrix_df)) "gene" else names(matrix_df)[[1]]
gene_id_col <- if ("gene_id" %in% names(matrix_df)) "gene_id" else gene_col
expr_raw <- as.matrix(matrix_df[, sample_names, drop = FALSE])
storage.mode(expr_raw) <- "numeric"

gene_variance <- apply(expr_raw, 1, var, na.rm = TRUE)
keep <- which(is.finite(gene_variance) & gene_variance > 0)
if (length(keep) < min_module_size) {
  stop("not enough variable genes for WGCNA")
}
keep <- keep[order(gene_variance[keep], decreasing = TRUE)]
variable_gene_count <- length(keep)
if (gene_selection_mode == "top_percent") {
  top_gene_percent <- min(max(gene_selection_value, 1), 100)
  selected_gene_limit <- ceiling(variable_gene_count * top_gene_percent / 100)
} else {
  top_gene_percent <- NA_real_
  selected_gene_limit <- max_genes
}
selected_gene_limit <- min(variable_gene_count, max(min_module_size, selected_gene_limit))
keep <- keep[seq_len(selected_gene_limit)]
expr_raw <- expr_raw[keep, , drop = FALSE]
gene_names <- make.unique(as.character(matrix_df[[gene_col]][keep]))
gene_ids <- as.character(matrix_df[[gene_id_col]][keep])
rownames(expr_raw) <- gene_names

datExpr <- as.data.frame(t(expr_raw))
names(datExpr) <- gene_names
rownames(datExpr) <- sample_names

gsg <- goodSamplesGenes(datExpr, verbose = 0)
if (!gsg$allOK) {
  datExpr <- datExpr[gsg$goodSamples, gsg$goodGenes, drop = FALSE]
  metadata <- metadata[match(rownames(datExpr), metadata$sample), , drop = FALSE]
  gene_names <- names(datExpr)
  gene_ids <- gene_ids[gsg$goodGenes]
}
if (ncol(datExpr) < min_module_size) {
  stop("not enough good genes after WGCNA quality filtering")
}

powers <- c(seq(1, 10), seq(12, 20, 2))
sft <- pickSoftThreshold(
  datExpr,
  powerVector = powers,
  networkType = network_type,
  verbose = 0
)
fit <- as.data.frame(sft$fitIndices)
scale_col <- grep("SFT.R.sq", names(fit), value = TRUE)[[1]]
soft_threshold_rows <- lapply(seq_len(nrow(fit)), function(i) {
  list(
    power = as.integer(fit$Power[[i]]),
    scale_free_fit = as.numeric(fit[[scale_col]][[i]]),
    mean_connectivity = as.numeric(fit$mean.k.[[i]])
  )
})

if (!is.na(requested_power) && requested_power > 0) {
  soft_power <- requested_power
} else {
  candidates <- fit$Power[which(fit[[scale_col]] >= 0.8)]
  soft_power <- if (length(candidates)) candidates[[1]] else 6
}

adjacency_matrix <- adjacency(datExpr, power = soft_power, type = network_type)
tom <- TOMsimilarity(adjacency_matrix, TOMType = network_type, verbose = 0)
diss_tom <- 1 - tom
gene_tree <- hclust(as.dist(diss_tom), method = "average")
dynamic_modules <- cutreeDynamic(
  dendro = gene_tree,
  distM = diss_tom,
  deepSplit = 2,
  pamRespectsDendro = FALSE,
  minClusterSize = min_module_size
)
dynamic_colors <- labels2colors(dynamic_modules)
if (length(unique(dynamic_colors[dynamic_colors != "grey"])) == 0) {
  stop("WGCNA did not detect non-grey modules")
}

merged <- mergeCloseModules(
  datExpr,
  dynamic_colors,
  cutHeight = merge_cut_height,
  verbose = 0
)
module_colors <- merged$colors
module_eigengenes <- orderMEs(merged$newMEs)
module_names <- names(module_eigengenes)
module_color_names <- sub("^ME", "", module_names)
module_color_names <- module_color_names[module_color_names != "grey"]
module_names <- paste0("ME", module_color_names)
if (length(module_names) == 0) {
  stop("WGCNA module merge left only grey genes")
}

condition <- factor(metadata$condition)
traits <- model.matrix(~ 0 + condition)
colnames(traits) <- sub("^condition", "", colnames(traits))
conditions <- colnames(traits)
module_trait_cor <- cor(module_eigengenes[, module_names, drop = FALSE], traits, use = "p")
module_trait_p <- corPvalueStudent(module_trait_cor, nrow(datExpr))

color_hex <- function(color_name) {
  rgb <- as.integer(tryCatch(col2rgb(color_name), error = function(e) col2rgb("grey60")))
  sprintf("#%02X%02X%02X", rgb[[1]], rgb[[2]], rgb[[3]])
}

gene_table <- data.frame(
  gene = names(datExpr),
  gene_id = gene_ids[match(names(datExpr), gene_names)],
  module_color = module_colors,
  stringsAsFactors = FALSE
)
module_trait_rows <- list()
modules <- list()
hub_rows <- list()

for (module_color in module_color_names) {
  module_name <- paste0("ME", module_color)
  module_genes <- which(gene_table$module_color == module_color)
  cor_values <- module_trait_cor[module_name, , drop = TRUE]
  p_values <- module_trait_p[module_name, , drop = TRUE]
  top_condition <- names(which.max(abs(cor_values)))
  kme <- cor(datExpr[, module_genes, drop = FALSE], module_eigengenes[, module_name], use = "p")
  kme <- as.numeric(kme)
  ordered <- order(abs(kme), decreasing = TRUE)
  module_hubs <- lapply(seq_len(min(10, length(ordered))), function(rank_index) {
    gene_index <- module_genes[ordered[[rank_index]]]
    row <- list(
      module = module_name,
      module_color = module_color,
      gene = gene_table$gene[[gene_index]],
      gene_id = gene_table$gene_id[[gene_index]],
      kME = as.numeric(kme[[ordered[[rank_index]]]])
    )
    hub_rows[[length(hub_rows) + 1]] <<- row
    row
  })
  modules[[length(modules) + 1]] <- list(
    module = module_name,
    color = module_color,
    color_hex = color_hex(module_color),
    gene_count = length(module_genes),
    top_condition = top_condition,
    top_correlation = as.numeric(cor_values[[top_condition]]),
    top_p_value = as.numeric(p_values[[top_condition]]),
    top_hubs = module_hubs
  )
  for (condition_name in conditions) {
    module_trait_rows[[length(module_trait_rows) + 1]] <- list(
      module = module_name,
      module_color = module_color,
      condition = condition_name,
      correlation = as.numeric(cor_values[[condition_name]]),
      p_value = as.numeric(p_values[[condition_name]])
    )
  }
}

gene_table$module <- paste0("ME", gene_table$module_color)
gene_table$module_color_hex <- vapply(gene_table$module_color, color_hex, character(1))
module_gene_table <- gene_table[gene_table$module_color != "grey", , drop = FALSE]
eigengene_table <- data.frame(sample = rownames(module_eigengenes), module_eigengenes, check.names = FALSE)
dendrogram_table <- data.frame(
  order = seq_along(gene_tree$order),
  gene = names(datExpr)[gene_tree$order],
  module = paste0("ME", module_colors[gene_tree$order]),
  module_color = module_colors[gene_tree$order],
  stringsAsFactors = FALSE
)
module_trait_table <- do.call(rbind, lapply(module_trait_rows, as.data.frame))
hub_table <- if (length(hub_rows)) do.call(rbind, lapply(hub_rows, as.data.frame)) else data.frame()
soft_threshold_table <- do.call(rbind, lapply(soft_threshold_rows, as.data.frame))

modules_path <- paste0(output_prefix, "_modules.csv")
module_trait_path <- paste0(output_prefix, "_module_trait.csv")
hub_path <- paste0(output_prefix, "_hub_genes.csv")
soft_threshold_path <- paste0(output_prefix, "_soft_threshold.csv")
eigengene_path <- paste0(output_prefix, "_eigengenes.csv")
dendrogram_path <- paste0(output_prefix, "_dendrogram.csv")
payload_path <- paste0(output_prefix, "_r_payload.json")

write.csv(module_gene_table, modules_path, row.names = FALSE, fileEncoding = "UTF-8")
write.csv(module_trait_table, module_trait_path, row.names = FALSE, fileEncoding = "UTF-8")
write.csv(hub_table, hub_path, row.names = FALSE, fileEncoding = "UTF-8")
write.csv(soft_threshold_table, soft_threshold_path, row.names = FALSE, fileEncoding = "UTF-8")
write.csv(eigengene_table, eigengene_path, row.names = FALSE, fileEncoding = "UTF-8")
write.csv(dendrogram_table, dendrogram_path, row.names = FALSE, fileEncoding = "UTF-8")

payload <- list(
  summary = list(
    method = "R_WGCNA",
    sample_count = nrow(datExpr),
    input_gene_count = nrow(matrix_df),
    variable_gene_count = variable_gene_count,
    selected_gene_count = ncol(datExpr),
    assigned_gene_count = nrow(module_gene_table),
    module_count = length(modules),
    soft_power = soft_power,
    min_module_size = min_module_size,
    merge_cut_height = merge_cut_height,
    network_type = network_type,
    gene_selection_mode = gene_selection_mode,
    top_gene_percent = if (is.na(top_gene_percent)) NULL else top_gene_percent,
    requested_max_genes = max_genes
  ),
  samples = lapply(seq_len(nrow(metadata)), function(i) {
    group_value <- if ("group" %in% names(metadata)) metadata$group[[i]] else metadata$condition[[i]]
    list(sample = metadata$sample[[i]], condition = as.character(metadata$condition[[i]]), group = as.character(group_value))
  }),
  conditions = as.list(conditions),
  modules = modules,
  module_trait = module_trait_rows,
  soft_threshold = soft_threshold_rows,
  dendrogram = lapply(seq_len(nrow(dendrogram_table)), function(i) as.list(dendrogram_table[i, ])),
  files = list(
    modules = normalizePath(modules_path, winslash = "\\", mustWork = FALSE),
    module_trait = normalizePath(module_trait_path, winslash = "\\", mustWork = FALSE),
    hub_genes = normalizePath(hub_path, winslash = "\\", mustWork = FALSE),
    soft_threshold = normalizePath(soft_threshold_path, winslash = "\\", mustWork = FALSE),
    eigengenes = normalizePath(eigengene_path, winslash = "\\", mustWork = FALSE),
    dendrogram = normalizePath(dendrogram_path, winslash = "\\", mustWork = FALSE)
  )
)

write_json(payload, payload_path, auto_unbox = TRUE, pretty = TRUE)
