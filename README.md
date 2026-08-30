# TZURIUM XP — EBTA engine

This repository is the generated public mirror of the `ebta_engine` core from
the EBTA (Evidence-Based Technical Analysis) project. Its editable sources are
governed in the private EBTA repository; neither this repository nor one of its
paths is an editing authority. It contains the standard-library statistical and
governance engine that mechanically enforces the published Python contracts.
Private strategies, adapters, calibrations, data, results, protocol documents,
and agent governance are not part of this repository.

Licensed under the Apache License, Version 2.0 — see `LICENSE` and
`NOTICE`.

The import package is `ebta_engine`; the distribution name is
`tzurium-xp-ebta-engine`. External consumers that install from Git should pin a
verified full commit SHA rather than install a branch or mutable tag:

```text
python -m pip install "tzurium-xp-ebta-engine @ git+https://github.com/LucBrice/tzurium-xp.git@<full-commit-sha>"
```

The private EBTA repository does not consume this mirror through that VCS pin;
it edits and validates its governed private source before publishing a
candidate pull request here. The explicit distribution version is `0.0.0`:
identity and reproducibility are provided by the pinned Git commit, not by a
release claim. A versioned, hashed wheel can replace the VCS pin only after a
reproducible release pipeline is governed separately.

`public_export_report.json` is the historical attestation of the initial
allowlisted snapshot used to create this repository. It is not a live manifest
of the current mirror. Current candidates are composed from a closed manifest
kept with the private editable sources and are reviewed through public CI before
merge.
