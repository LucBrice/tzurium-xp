# TZURIUM XP — EBTA engine

This repository is the canonical editable source of the public `ebta_engine`
core from the EBTA (Evidence-Based Technical Analysis) project. It contains the
standard-library statistical and governance engine that mechanically enforces
the published Python contracts. Private strategies, adapters, calibrations,
data, results, protocol documents, and agent governance are not part of this
repository.

Licensed under the Apache License, Version 2.0 — see `LICENSE` and
`NOTICE`.

The import package is `ebta_engine`; the distribution name is
`tzurium-xp-ebta-engine`. Until a release pipeline exists, consumers must pin a
verified full Git commit SHA rather than install a branch or mutable tag:

```text
python -m pip install "tzurium-xp-ebta-engine @ git+https://github.com/LucBrice/tzurium-xp.git@<full-commit-sha>"
```

The explicit distribution version is `0.0.0`: identity and reproducibility are
provided by the pinned Git commit, not by a release claim. A versioned, hashed
wheel can replace the VCS pin only after a reproducible release pipeline is
governed separately.
