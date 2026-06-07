args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 8) {
  stop("Usage: metabolomics_statistics.R <matrix.csv> <metadata.csv> <output_dir> <prefix> <case> <control> <p_value> <log2fc> [t_test|wilcox] [vip_threshold]")
}

matrix_file <- args[[1]]
metadata_file <- args[[2]]
output_dir <- args[[3]]
prefix <- args[[4]]
case_condition <- args[[5]]
control_condition <- args[[6]]
p_threshold <- as.numeric(args[[7]])
log2fc_threshold <- as.numeric(args[[8]])
univariate_method <- if (length(args) >= 9) tolower(args[[9]]) else "t_test"
vip_threshold <- if (length(args) >= 10) as.numeric(args[[10]]) else 1
if (!univariate_method %in% c("t_test", "wilcox")) {
  stop("univariate method must be t_test or wilcox")
}
if (!is.finite(vip_threshold) || vip_threshold <= 0) {
  vip_threshold <- 1
}

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

fit_plsda <- function(x, y, ncomp = 2) {
  x <- scale(x, center = TRUE, scale = TRUE)
  x[!is.finite(x)] <- 0
  y <- as.numeric(scale(y, center = TRUE, scale = FALSE))
  ncomp <- min(ncomp, nrow(x) - 1, ncol(x))
  if (ncomp < 1 || sum(abs(y), na.rm = TRUE) == 0) {
    return(NULL)
  }
  weights <- matrix(0, nrow = ncol(x), ncol = ncomp)
  scores <- matrix(0, nrow = nrow(x), ncol = ncomp)
  y_ss <- rep(0, ncomp)
  residual_x <- x
  residual_y <- y
  used <- 0
  for (component in seq_len(ncomp)) {
    weight <- as.vector(crossprod(residual_x, residual_y))
    norm_weight <- sqrt(sum(weight^2))
    if (!is.finite(norm_weight) || norm_weight <= 0) {
      break
    }
    weight <- weight / norm_weight
    score <- as.vector(residual_x %*% weight)
    score_ss <- sum(score^2)
    if (!is.finite(score_ss) || score_ss <= 0) {
      break
    }
    loading <- as.vector(crossprod(residual_x, score) / score_ss)
    y_loading <- sum(residual_y * score) / score_ss
    residual_x <- residual_x - tcrossprod(score, loading)
    residual_y <- residual_y - score * y_loading
    weights[, component] <- weight
    scores[, component] <- score
    y_ss[[component]] <- y_loading^2 * score_ss
    used <- component
  }
  if (used < 1 || sum(y_ss[seq_len(used)]) <= 0) {
    return(NULL)
  }
  weights <- weights[, seq_len(used), drop = FALSE]
  scores <- scores[, seq_len(used), drop = FALSE]
  y_ss <- y_ss[seq_len(used)]
  vip_weights <- sweep(weights^2, 2, y_ss, "*")
  vip <- sqrt(ncol(x) * rowSums(vip_weights) / sum(y_ss))
  list(scores = scores, vip = vip, y_ss = y_ss)
}

model_samples <- metadata$sample[metadata$condition %in% c(case_condition, control_condition)]
model_metadata <- metadata[metadata$sample %in% model_samples, , drop = FALSE]
model_samples <- model_metadata$sample
vip_values <- rep(NA_real_, nrow(normalized))
plsda_available <- FALSE
plsda_message <- "PLS-DA requires two conditions with at least two samples per group."
plsda_scores <- data.frame(
  sample = character(),
  condition = character(),
  plsda1 = numeric(),
  plsda2 = numeric(),
  stringsAsFactors = FALSE
)
if (has_comparison && length(model_samples) >= 4 && nrow(scaled) >= 2) {
  model_x <- t(scaled[, model_samples, drop = FALSE])
  colnames(model_x) <- make.unique(as.character(features$feature_id))
  model_y <- ifelse(model_metadata$condition == case_condition, 1, 0)
  pls_fit <- tryCatch(fit_plsda(model_x, model_y, ncomp = 2), error = function(e) NULL)
  if (!is.null(pls_fit)) {
    plsda_available <- TRUE
    plsda_message <- "PLS-DA fitted with in-script PLS1/NIPALS fallback."
    vip_values <- as.numeric(pls_fit$vip)
    score_matrix <- pls_fit$scores
    plsda_scores <- data.frame(
      sample = model_metadata$sample,
      condition = model_metadata$condition,
      plsda1 = score_matrix[, 1],
      plsda2 = if (ncol(score_matrix) >= 2) score_matrix[, 2] else 0,
      stringsAsFactors = FALSE
    )
  } else {
    plsda_message <- "PLS-DA fitting failed because the comparison matrix has insufficient supervised signal."
  }
}
vip_table <- data.frame(
  feature_id = features$feature_id,
  metabolite = features$feature_name,
  vip = vip_values,
  vip_gt_1 = !is.na(vip_values) & vip_values > vip_threshold,
  stringsAsFactors = FALSE
)
write.csv(plsda_scores, file.path(output_dir, paste0(prefix, "_plsda_scores.csv")), row.names = FALSE)
write.csv(vip_table, file.path(output_dir, paste0(prefix, "_vip.csv")), row.names = FALSE)

oplsda_available <- FALSE
oplsda_message <- "ropls package is not installed; OPLS-DA was skipped."
if (has_comparison && requireNamespace("ropls", quietly = TRUE) && length(model_samples) >= 4 && nrow(scaled) >= 2) {
  oplsda_result <- tryCatch({
    model_x <- t(scaled[, model_samples, drop = FALSE])
    colnames(model_x) <- make.unique(as.character(features$feature_id))
    model_y <- factor(model_metadata$condition, levels = c(control_condition, case_condition))
    model <- ropls::opls(model_x, model_y, predI = 1, orthoI = 1, permI = 0, fig.pdfC = "none")
    score <- ropls::getScoreMN(model)
    ortho_score <- slot(model, "orthoScoreMN")
    data.frame(
      sample = model_metadata$sample,
      condition = model_metadata$condition,
      predictive_score = score[, 1],
      orthogonal_score = if (!is.null(ortho_score) && ncol(ortho_score) >= 1) ortho_score[, 1] else 0,
      stringsAsFactors = FALSE
    )
  }, error = function(e) {
    oplsda_message <<- paste("ropls OPLS-DA failed:", conditionMessage(e))
    NULL
  })
  if (!is.null(oplsda_result)) {
    oplsda_available <- TRUE
    oplsda_message <- "OPLS-DA fitted with ropls."
    write.csv(oplsda_result, file.path(output_dir, paste0(prefix, "_oplsda_scores.csv")), row.names = FALSE)
  }
}

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
  primary_p <- if (univariate_method == "wilcox") p_w else p_t
  diff_rows[[i]] <- data.frame(
    feature_id = features$feature_id[[i]],
    metabolite = features$feature_name[[i]],
    case_condition = case_condition,
    control_condition = control_condition,
    case_mean = case_mean,
    control_mean = control_mean,
    log2fc = log2fc,
    p_value = primary_p,
    t_p_value = p_t,
    wilcox_p_value = p_w,
    vip = vip_values[[i]],
    vip_gt_1 = !is.na(vip_values[[i]]) && vip_values[[i]] > vip_threshold,
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
  univariate_method = univariate_method,
  p_value_threshold = p_threshold,
  log2fc_threshold = log2fc_threshold,
  vip_threshold = vip_threshold,
  plsda_available = plsda_available,
  plsda_message = plsda_message,
  vip_available = plsda_available,
  vip_feature_count = sum(vip_table$vip_gt_1, na.rm = TRUE),
  oplsda_available = oplsda_available,
  oplsda_message = oplsda_message,
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
