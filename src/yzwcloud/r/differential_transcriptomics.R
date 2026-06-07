args <- commandArgs(trailingOnly = TRUE)
matrix_file <- args[[1]]
metadata_file <- args[[2]]
comparisons_file <- args[[3]]
output_dir <- args[[4]]
padj_cutoff <- as.numeric(args[[5]])
log2_fc_cutoff <- as.numeric(args[[6]])

matrix <- read.csv(matrix_file, check.names = FALSE, stringsAsFactors = FALSE)
metadata <- read.csv(metadata_file, check.names = FALSE, stringsAsFactors = FALSE)
comparisons <- read.csv(comparisons_file, check.names = FALSE, stringsAsFactors = FALSE)

safe_num <- function(x) suppressWarnings(as.numeric(gsub(",", "", as.character(x))))
feature_name <- if ("feature_name" %in% colnames(matrix)) matrix$feature_name else matrix$feature_id
description <- if ("description" %in% colnames(matrix)) matrix$description else rep("", nrow(matrix))

write_comparison_tables <- function(result, slug) {
  result <- result[!is.na(result$pvalue) & !is.na(result$log2FoldChange), , drop = FALSE]
  result$padj <- p.adjust(result$pvalue, method = "BH")
  result$regulation <- "not_significant"
  result$regulation[result$padj < padj_cutoff & result$log2FoldChange >= log2_fc_cutoff] <- "up"
  result$regulation[result$padj < padj_cutoff & result$log2FoldChange <= -log2_fc_cutoff] <- "down"
  result <- result[order(result$padj, -abs(result$log2FoldChange)), , drop = FALSE]
  significant <- result[result$regulation != "not_significant", , drop = FALSE]
  write.csv(result, file.path(output_dir, paste0(slug, "_all_genes.csv")), row.names = FALSE, na = "")
  write.csv(significant, file.path(output_dir, paste0(slug, "_significant_genes.csv")), row.names = FALSE, na = "")
  write.csv(significant[significant$regulation == "up", , drop = FALSE], file.path(output_dir, paste0(slug, "_up_genes.csv")), row.names = FALSE, na = "")
  write.csv(significant[significant$regulation == "down", , drop = FALSE], file.path(output_dir, paste0(slug, "_down_genes.csv")), row.names = FALSE, na = "")
}

run_base_comparison <- function(numerator, denominator) {
  samples_numerator <- metadata$sample[metadata$condition == numerator]
  samples_denominator <- metadata$sample[metadata$condition == denominator]
  if (length(samples_numerator) < 2 || length(samples_denominator) < 2) {
    stop(paste("Each comparison group needs at least two samples:", numerator, denominator))
  }

  rows <- vector("list", nrow(matrix))
  for (i in seq_len(nrow(matrix))) {
    values_numerator <- safe_num(unlist(matrix[i, samples_numerator, drop = FALSE]))
    values_denominator <- safe_num(unlist(matrix[i, samples_denominator, drop = FALSE]))
    values_numerator <- values_numerator[is.finite(values_numerator)]
    values_denominator <- values_denominator[is.finite(values_denominator)]
    mean_numerator <- if (length(values_numerator) > 0) mean(values_numerator) else NA
    mean_denominator <- if (length(values_denominator) > 0) mean(values_denominator) else NA
    log2_fc <- mean_numerator - mean_denominator
    pvalue <- NA
    if (length(values_numerator) >= 2 && length(values_denominator) >= 2) {
      pvalue <- tryCatch(t.test(values_numerator, values_denominator)$p.value, error = function(e) NA)
    }
    rows[[i]] <- data.frame(
      gene_id = matrix$feature_id[[i]],
      feature_name = feature_name[[i]],
      description = description[[i]],
      baseMean = mean(c(values_numerator, values_denominator), na.rm = TRUE),
      log2FoldChange = log2_fc,
      pvalue = pvalue,
      stringsAsFactors = FALSE
    )
  }
  do.call(rbind, rows)
}

run_deseq2 <- function() {
  suppressPackageStartupMessages(library(DESeq2))
  samples <- metadata$sample[metadata$sample %in% colnames(matrix)]
  metadata <- metadata[match(samples, metadata$sample), , drop = FALSE]
  rownames(metadata) <- metadata$sample
  metadata$condition <- factor(metadata$condition)

  raw_counts <- matrix[, samples, drop = FALSE]
  raw_counts[] <- lapply(raw_counts, function(x) round(safe_num(x)))
  counts_matrix <- as.matrix(raw_counts)
  rownames(counts_matrix) <- make.unique(as.character(matrix$feature_id))
  storage.mode(counts_matrix) <- "integer"

  dds <- DESeqDataSetFromMatrix(
    countData = counts_matrix,
    colData = metadata,
    design = ~ condition
  )
  keep <- rowSums(counts(dds) >= 10) >= min(3, ncol(dds))
  dds <- dds[keep, ]
  if (nrow(dds) == 0) {
    stop("No genes remain after the low-count filter.")
  }
  dds <- DESeq(dds, fitType = "mean", minReplicatesForReplace = 7, parallel = FALSE)

  normalized <- as.data.frame(counts(dds, normalized = TRUE))
  normalized$gene_id <- rownames(normalized)
  normalized <- normalized[, c("gene_id", samples), drop = FALSE]
  write.csv(normalized, file.path(output_dir, "normalized_counts.csv"), row.names = FALSE, na = "")

  for (i in seq_len(nrow(comparisons))) {
    numerator <- comparisons$numerator[[i]]
    denominator <- comparisons$denominator[[i]]
    slug <- comparisons$slug[[i]]
    if (!(numerator %in% levels(metadata$condition)) || !(denominator %in% levels(metadata$condition))) {
      stop(paste("Unknown comparison groups:", numerator, denominator))
    }
    res <- results(dds, contrast = c("condition", numerator, denominator), alpha = padj_cutoff, independentFiltering = TRUE)
    res_df <- as.data.frame(res)
    res_df$gene_id <- rownames(res_df)
    name_map <- data.frame(gene_id = matrix$feature_id, feature_name = feature_name, description = description, stringsAsFactors = FALSE)
    res_df <- merge(name_map, res_df, by = "gene_id", all.y = TRUE, sort = FALSE)
    write_comparison_tables(res_df, slug)
  }
}

is_count_like_matrix <- function() {
  samples <- metadata$sample[metadata$sample %in% colnames(matrix)]
  if (length(samples) < 2) {
    return(FALSE)
  }
  values <- safe_num(unlist(matrix[, samples, drop = FALSE]))
  values <- values[is.finite(values)]
  if (length(values) == 0) {
    return(FALSE)
  }
  all(values >= 0 & abs(values - round(values)) < 1e-6)
}

if (requireNamespace("DESeq2", quietly = TRUE) && is_count_like_matrix()) {
  run_deseq2()
} else {
  for (i in seq_len(nrow(comparisons))) {
    numerator <- comparisons$numerator[[i]]
    denominator <- comparisons$denominator[[i]]
    slug <- comparisons$slug[[i]]
    if (!(numerator %in% metadata$condition) || !(denominator %in% metadata$condition)) {
      stop(paste("Unknown comparison groups:", numerator, denominator))
    }
    write_comparison_tables(run_base_comparison(numerator, denominator), slug)
  }
}
