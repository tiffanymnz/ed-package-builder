# ED Package Builder

Build an Excessive Debris package from vendor photos, bids, invoice and RBB documents. Start with the case number and vendor, review loads and costs, then save one combined PDF.

- Import folders and ZIPs; accept invoice and bid images or PDFs.
- Review source-checked photo groups and load cards, then select evidence for each load.
- See each load's next required action and open that load directly.
- Confirm measurements and the cubic yard calculation; reconcile the rate-based first-10-CYD HUD allowance.
- Save and reopen a portable `.edcase` project with originals and progress.
- Open and export large projects with progress and cancellation.
- Open the saved PDF or folder directly from the completion screen.

Read START_HERE.md for the workflow.

**Current source: v57 developer workflow acceptance.** Adds responsive cancellable vendor import, keeps document confirmation reachable in short windows, and fixes interruption recovery, repeated scrolling callbacks, missing-invoice page loading and optional-cache save failures. The first-run instructions match the import-first workflow. Recognition models and financial rules are unchanged. The release validation identifies the matching Windows build and scope.

The broad classifier is unchanged. Reinspection corrected one mislabeled exterior photo in the 90-photo v54 selection: the corrected result is 65 correct suggestions and 23 withheld across 88 scored photos. This is a reference correction, not a new sorting gain. Additional crop, angle, tape-focus and detector experiments were rejected when they added mistakes, processing cost or unrelated review work.

Suggestions still need review. Container recognition and physical-trip assignment remain separate; unresolved trips remain unresolved. See RELEASE_VALIDATION.md for the test scope and retained limitations. The planned work-laptop trial measures actual staff efficiency.
