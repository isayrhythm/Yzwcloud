args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 8) {
  stop("Usage: metabolomics_statistics.R <matrix.csv> <metadata.csv> <output_dir> <prefix> <case> <control> <p_value> <log2fc>")
}

matrix_file <- args[[1]]
metadata_file <- args[[2]]
output_dir <- args[[3]]
prefix <- args[[4]]
case_condition <- args[[5]]
control_condition <- args[[6]]
p_threshold <- as.numeric(args[[7]])
log2fc_threshold <- as.numeric(args[[8]])

dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

matrix <- read.csv(matrix_file, check.names = FALSE, stringsAsFactors = FALSE)
metadata <- read.csv(metadata_file, check.names = FALSE, stringsAsFactors = FALSE)
required_meta <- c("sample", "condition")
if (!all(required_meta %in% names(metadata))) {
  stop("metadata must contain sample and condition columns")
}
if (!all(c("feature_id", "feature_name") %in% names(matrix))) {
  stop("matrix must contain feature_id and feature_name columns")
}

sample_cols <- intersect(metadata$sample, names(matrix))
if (length(sample_cols) < 2) {
  stop("metabolomics statistics requires at least 2 matched samples")
}
metadata <- metadata[match(sample_cols, metadata$sample), , drop = FALSE]
values <- as.matrix(matrix[, sample_cols, drop = FALSE])
mode(values) <- "numeric"

keep <- rowSums(!is.na(values)) >= 2
values <- values[keep, , drop = FALSE]
features <- matrix[keep, c("feature_id", "feature_name"), drop = FALSE]
if (nrow(values) < 2) {
  stop("metabolomics statistics requires at least 2 usable metabolites")
}

for (i in seq_len(nrow(values))) {
  row <- values[i, ]
  present <- row[is.finite(row)]
  if (length(present) == 0) {
    values[i, ] <- 0
    next
  }
  positive <- present[present > 0]
  fill <- if (length(positive) > 0) min(positive) / 2 else median(present, na.rm = TRUE)
  row[!is.finite(row)] <- fill
  values[i, ] <- row
}

sample_totals <- colSums(values, na.rm = TRUE)
median_total <- median(sample_totals[sample_totals > 0])
if (is.finite(median_total) && median_total > 0) {
  values <- sweep(values, 2, ifelse(sample_totals > 0, sample_totals, median_total), "/") * median_total
}
normalized <- log2(values + 1)

write.csv(
  data.frame(feature_id = features$feature_id, feature_name = features$feature_name, normalized, check.names = FALSE),
  file.path(output_dir, paste0(prefix, "_normalized_matrix.csv")),
  row.names = FALSE
)

rsd <- function(x) {
  mean_x <- mean(x, na.rm = TRUE)
  if (!is.finite(mean_x) || mean_x == 0) {
    return(NA_real_)
  }
  sd(x, na.rm = TRUE) / abs(mean_x) * 100
}
qc <- data.frame(
  sample = sample_cols,
  condition = metadata$condition,
  total_signal = sample_totals,
  detected_metabolites = colSums(values > 0, na.rm = TRUE),
  median_log2 = apply(normalized, 2, median, na.rm = TRUE),
  stringsAsFactors = FALSE
)
write.csv(qc, file.path(output_dir, paste0(prefix, "_qc.csv")), row.names = FALSE)

scaled <- t(scale(t(normalized)))
scaled[!is.finite(scaled)] <- 0
pca <- prcomp(t(scaled), center = TRUE, scale. = FALSE)
explained <- (pca$sdev^2) / sum(pca$sdev^2)
pca_scores <- data.frame(
  sample = rownames(pca$x),
  condition = metadata$condition,
  pc1 = pca$x[, 1],
  pc2 = if (ncol(pca$x) >= 2) pca$x[, 2] else 0,
  pc1_variance = explained[[1]] * 100,
  pc2_variance = if (length(explained) >= 2) explained[[2]] * 100 else 0,
  stringsAsFactors = FALSE
)
write.csv(pca_scores, file.path(output_dir, paste0(prefix, "_pca_scores.csv")), row.names = FALSE)

correlation <- cor(normalized, use = "pairwise.complete.obs", method = "pearson")
correlation_out <- data.frame(sample = rownames(correlation), correlation, check.names = FALSE)
write.csv(correlation_out, file.path(output_dir, paste0(prefix, "_sample_correlation.csv")), row.names = FALSE)

case_samples <- metadata$sample[metadata$condition == case_condition]
control_samples <- metadata$sample[metadata$condition == control_condition]
has_comparison <- length(case_samples) >= 2 && length(control_samples) >= 2 && case_condition != control_condition
diff_rows <- vector("list", nrow(normalized))
for (i in seq_len(nrow(normalized))) {
  row <- normalized[i, ]
  case_values <- as.numeric(row[case_samples])
  control_values <- as.numeric(row[control_samples])
  case_mean <- if (length(case_values) > 0) mean(case_values, na.rm = TRUE) else NA_real_
  control_mean <- if (length(control_values) > 0) mean(control_values, na.rm = TRUE) else NA_real_
  log2fc <- case_mean - control_mean
  p_t <- NA_real_
  p_w <- NA_real_
  if (has_comparison) {
    p_t <- tryCatch(t.test(case_values, control_values)$p.value, error = function(e) NA_real_)
    p_w <- tryCatch(wilcox.test(case_values, control_values, exact = FALSE)$p.value, error = function(e) NA_real_)
  }
  diff_rows[[i]] <- data.frame(
    feature_id = features$feature_id[[i]],
    metabolite = features$feature_name[[i]],
    case_condition = case_condition,
    control_condition = control_condition,
    case_mean = case_mean,
    control_mean = control_mean,
    log2fc = log2fc,
    p_value = p_t,
    wilcox_p_value = p_w,
    stringsAsFactors = FALSE
  )
}
differential <- do.call(rbind, diff_rows)
differential$p_adjust <- p.adjust(differential$p_value, method = "BH")
differential$significant <- !is.na(differential$p_value) &
  differential$p_value <= p_threshold &
  abs(differential$log2fc) >= log2fc_threshold
differential <- differential[order(ifelse(is.na(differential$p_value), Inf, differential$p_value)), ]
write.csv(differential, file.path(output_dir, paste0(prefix, "_differential.csv")), row.names = FALSE)

summary <- list(
  metabolite_count = nrow(normalized),
  sample_count = length(sample_cols),
  condition_count = length(unique(metadata$condition)),
  case_condition = case_condition,
  control_condition = control_condition,
  significant_metabolite_count = sum(differential$significant, na.rm = TRUE),
  normalization = "total signal median scaling + log2(x + 1)",
  missing_value_imputation = "row half-minimum positive value",
  p_value_threshold = p_threshold,
  log2fc_threshold = log2fc_threshold,
  vip_available = FALSE,
  enrichment_available = FALSE
)
json_value <- function(value) {
  if (is.logical(value)) {
    return(ifelse(value, "true", "false"))
  }
  if (is.numeric(value)) {
    if (!is.finite(value)) {
      return("null")
    }
    return(as.character(value))
  }
  escaped <- gsub('\\\\', '\\\\\\\\', as.character(value))
  escaped <- gsub('"', '\\\\"', escaped)
  paste0('"', escaped, '"')
}
json_lines <- c(
  "{",
  paste0(
    "  \"",
    names(summary),
    "\": ",
    vapply(summary, json_value, character(1)),
    c(rep(",", length(summary) - 1), "")
  ),
  "}"
)
writeLines(json_lines, file.path(output_dir, paste0(prefix, "_summary.json")))
