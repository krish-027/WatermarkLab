# Pinned DeepMind frequentist core

Minimal unchanged source from google-deepmind/synthid-text commit
9c055d932e042b75197e337371448a120bbc65bb. Apache-2.0 license/copyright headers
retained. SHA256SUMS.json records original bytes. No upstream math changes.

Only hashing_function, logits_processing and detector_frequentist are runtime
dependencies. No mix-in, model generation, Bayesian/JAX code or full package
installation is exposed. The full package's Transformers >=5.16 requirement
does not describe this independently tested subset. Keep KGW's verified pins.
UPSTREAM_README.md describes the broader repository, not WatermarkLab features.
