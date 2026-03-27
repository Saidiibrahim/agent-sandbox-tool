# Frontend

This repository does not currently ship a first-party frontend.

If a demo UI, docs site, or interactive inspector is added later:

- treat it as subordinate to the Python library, not the product center of gravity
- document it under `docs/design-docs/` and the `docs/product-specs` directory
- keep execution authority on the host or backend service, not in a browser-only client
- add clear testing and security notes before expanding scope

Until then, frontend guidance here is intentionally minimal.
