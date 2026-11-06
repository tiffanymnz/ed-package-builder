# ED Package Builder v50 — Upgrade Validation

## What changed

| Area | Upgrade |
|---|---|
| Photo review | Scrollable 6/12/24-photo grids, responsive columns, readable previews, retained multi-selection and work-area-aware window sizing |
| Batch correction | Undo the last load, property-stage, category or trip-group action; reject undo after conflicting reviews or changed source files |
| Repeated containers | Explicitly checked trip endpoints create bounded photo review groups; overlapping/interleaved clocks and date-only clues do not establish a trip |
| Card reading | Split-line load labels and printed fraction symbols; no new OCR engine or model asset |
| Measurements | Tape Detail navigates to a possible tape region, without inventing tape readings or dimensions |
| Invoices | Select the final invoice version, keep superseded originals, or explicitly confirm a combined final bill; approval survives portable project reopening |
| Export reliability | Durable journal and previous-file recovery after a process interruption |
| Work-computer checks | Local aggregate storage and cached photo-review preparation timings; no telemetry |

The existing combined PDF, rate-based HUD deduction, bid comparison, source-bound evidence choices and portable .edcase workflow remain available.

## Tests

Windows run #27 passed all 417 tests with no skips. The actual frozen CPU photo reader, CPU card reader (version 5), all four workflow pages, 6/12/24-photo layouts, taskbar-boundary check and executable export smoke checks passed. Tested application code: 81bbbf90cb407c0a87c75be05cc97ccb14013d3b. Run ID: 42307807615. Download SHA-256: de8c6c226b4ea9e8a89776d9f77b5ab66232575ec1811030e0b17e8f84471842.

Local source suite: 417 checks, 345 passed and 72 graphical checks skipped on this display-less host. The actual CPU photo-model smoke check passed. Focused corrected regression fixtures: 22 passed, two graphical checks deferred to Windows.

The initial Windows pass caught a staged-file flushing incompatibility. It was corrected to use writable handles. Follow-up tests corrected two test-fixture errors: Windows path aliases and a mutable expected-selection set. Those errors were not ignored or converted to skips.

## Photo replay: benefit and unresolved accuracy

The existing example contained 336 photos. Eight manually checked endpoint photos seeded four trip windows. Sixty otherwise uncertain photos entered trip review groups.

Of 26 non-seed package-reference photos, the program proposed three correct loads, zero wrong loads and left 23 unresolved. The sixty review-window photos are not sixty verified assignments. No template box is populated merely because a photo falls inside a time window.

Seventy historical OCR readings showed no changed outcomes under the split-line parser. New layout support is regression-tested, but no new general recognition-accuracy percentage is demonstrated.

Cached review preparation took about 0.21 seconds and 0.242 seconds on this host. This excludes inference and human review. The reference comes from an existing package and is imperfect; this is not an independent unseen-property evaluation.

## Storage

Application plus existing models total approximately 649 MB (619 MiB), before project files. Keeping the download ZIP adds approximately 116 MB; it can be removed after extraction.

No additional model assets. Existing card-reader and photo-model assets total 366,587,180 bytes (349.6 MiB). Windows download: 116,296,146 bytes. Unpacked application: 282,701,325 bytes; editable projects are additional.

## What is still unproven or intrinsically limited

- Sorting accuracy on new properties and handwriting styles needs independently checked reference photos. Existing-case replay cannot establish that result.
- Blurred, occluded or missing card/tape evidence may remain unreadable. Similar-looking reused containers cannot establish which physical trip occurred.
- Date-only timestamps and conflicting/interleaved trip times require a manual decision. Property stages require visible property condition; timestamps and filenames are insufficient.
- The first-time staff experience and actual end-to-end time saved on the work laptop have not been measured. Use the app's local performance check for its cached review-preparation speed; that does not measure staff efficiency.
- Export recovery is validated for process interruption. Separate files are not simultaneously visible as one atomic change; damaged backups or hardware that does not honor durable writes remain outside the guarantee.
- The exact $2,500 bid boundary, whether the threshold uses the gross or net amount, and any $45/CYD exception still need an authoritative policy decision.

This is a tested workflow upgrade when the Windows gates pass. It is not evidence that every recognition limitation is solved, and it should not be described as perfect or fully automatic photo placement.
