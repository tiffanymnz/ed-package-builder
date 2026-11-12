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

**Current source: v56 card-review and recovery fixes.** Incoming card readings update the open form while preserving your edits. The pending queue excludes confirmed cards, suggested stages require an explicit choice, and failed reading batches can be retried without repeating successful work. Cancelled case dialogs resume background work. All 476 local source/desktop tests passed; the distributed executable must match a successful Windows run and its delivery validation record.

The broad classifier is unchanged. Reinspection corrected one mislabeled exterior photo in the 90-photo v54 selection: the corrected result is 65 correct suggestions and 23 withheld across 88 scored photos. This is a reference correction, not a new sorting gain. Additional crop, angle, tape-focus and detector experiments were rejected when they added mistakes, processing cost or unrelated review work.

Suggestions still need review. Container recognition and physical-trip assignment remain separate; unresolved trips remain unresolved. See RELEASE_VALIDATION.md for the test scope and retained limitations. The planned work-laptop trial measures actual staff efficiency.
