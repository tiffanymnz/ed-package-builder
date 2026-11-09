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

**Current source: v53 acceptance update.** All 449 local source and desktop tests passed without skips. The v52 baseline passed 445 Windows tests and frozen application checks. Match any distributed executable to its successful Windows workflow and included validation record.

All 14 supplied ZIP submissions passed import, duplicate-handling, decoded-image and source-hash checks: 6,776 unique file imports within their submissions. Four reference-directed packages again preserved 309 selected source images and 13 financial pages.

The final broad-category check scored 294 of 303 visually labeled photos across 14 submissions: 147 correct suggestions, 3 incorrect suggestions and 144 withheld. Of 150 suggestions, 98% matched the checked references; coverage was 51%. A separate seven-positive real-card check returned two correct load numbers and withheld five, with no wrong load numbers. Three of four positive card-stage references were read correctly; one was withheld. Suggestions need review, and appearance alone never establishes a trip.

These are supplied-data acceptance results, including development checks, not a universal or untouched-property accuracy claim. The work-laptop trial is the user's next planned step after software checks. The only deferred policy decision is the exact $2,500 boundary and gross/net basis. See RELEASE_VALIDATION.md.
