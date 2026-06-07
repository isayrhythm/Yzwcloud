cran_mirror <- "https://mirrors.tuna.tsinghua.edu.cn/CRAN/"
options(repos = c(CRAN = cran_mirror))
options(timeout = 600)

user_library <- Sys.getenv("R_LIBS_USER")
if (!nzchar(user_library)) {
  user_library <- file.path(Sys.getenv("LOCALAPPDATA"), "R", "win-library", paste(R.version$major, R.version$minor, sep = "."))
}
dir.create(user_library, recursive = TRUE, showWarnings = FALSE)
.libPaths(c(user_library, .libPaths()))

install_if_missing <- function(package) {
  if (!requireNamespace(package, quietly = TRUE)) {
    install.packages(package, repos = cran_mirror, lib = user_library)
  }
}

install_if_missing("BiocManager")

bioc_packages <- c("DESeq2", "impute", "preprocessCore", "AnnotationDbi")
for (package in bioc_packages) {
  if (!requireNamespace(package, quietly = TRUE)) {
    BiocManager::install(package, ask = FALSE, update = FALSE, lib = user_library)
  }
}

cran_packages <- c("WGCNA", "jsonlite")
for (package in cran_packages) {
  install_if_missing(package)
}

cat("R differential and WGCNA dependencies are ready. Library:", user_library, "\n")
