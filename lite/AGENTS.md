# Publication workflow

The user requested on 2026-11-04 that the AstroForge Site be updated alongside future completed AstroForge Lite changes, so they can inspect progress in the browser. Treat deployment as part of delivery unless the user requests local-only work or saving without publication.

After appropriate checks and a successful build, publish the exact tested Lite source through the Sites skill to the existing project in `.openai/hosting.json`. Preserve its current audience. Keep GitHub as the source of truth and synchronize the Site from this checkout using an isolated Sites source checkout; do not turn the GitHub checkout into the hosting repository.

Update the visible version and the short changes summary in Help when functionality changes. Verify deployment reaches success and return the live URL. If deployment is blocked, report that explicitly rather than describing the Site as current. This workflow does not establish an unattended watcher for changes made outside the current work.
