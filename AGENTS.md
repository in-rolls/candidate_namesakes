# Working on this data repository

This is a point-in-time data collection. Follow the [data-repository policy](https://github.com/soodoku/data-repos#maintenance-policy).

- The input is pinned by commit and SHA-256 in `data/source.json`. Do not edit it; fetch it with `make fetch`.
- Run the tests once when code changes. When outputs change, check row counts, keys and hashes in `MANIFEST.json`.
- Muse Spark calls are metered. Keep them explicit, capped, and committed as lookup tables with model and prompt hash.
- Do not add blanket CI, pre-commit, version matrices or package-release scaffolding.
