# v58 - Faster Photo Selection and Clearer Actions

- Selecting/deselecting photos, selecting a page and clearing selection update the existing controls without reopening, rehashing or decoding the page's source images. Previews, keyboard focus and scroll position stay in place. Assignment still verifies original hashes.
- The selected count identifies photos outside the current filter; applying a load/stage to that wider selection requires an explicit confirmation. Selection across ordinary pages remains available.
- Next, Save Project and Open Output Folder are disabled until a case is open. Measurement issues display the same field names staff see in the form.
- Recognition models and thresholds remain unchanged. This release improves review efficiency and safeguards, not recognition recall.

# v57 - Developer Workflow Acceptance

- Vendor folder/ZIP imports prepare files and PDF document suggestions off the interface thread. Cancel leaves the case unchanged; commit failures roll back newly moved files. Original bytes, exact duplicate detection and import limits are preserved.
- The document dialog has scrollable details, responsive sizing, Cancel/Escape and a fixed confirmation footer. Card descriptions wrap to available width. First-run instructions follow the actual create/import/review/export order.
- One scrolling dispatcher replaces callbacks accumulated by repeated refreshes; destroyed pages are removed.
- Export cancellation, declined draft export, failed project save and cancelled closing resume current-case photo processing.
- Missing invoice sources no longer break page creation. Changed invoice sources cannot refill empty fields from source-bound old cost suggestions. A damaged optional analysis cache falls back to in-memory results so original evidence and progress can still be saved.
- Recognition models, thresholds, physical-trip rules and financial policy are unchanged. No accuracy increase or staff-efficiency percentage is claimed.
- See DEVELOPER_ACCEPTANCE.md and RELEASE_VALIDATION.md for the checked workflow and Windows delivery gate.

# v56 - Smoother Card Review and Reliable Recovery

- Incoming source-checked card readings update the open form without recreating its preview or overwriting manually edited fields. Possible stages are visible; Use Suggested Stage requires an explicit choice before confirmation. Suggested numbers never assign a physical trip automatically.
- Confirmed cards leave the pending queue. Show Reviewed Cards reopens saved decisions, and the completed queue shows a clear next step.
- Retry Card Reading recovers failed and unstarted cards while retaining successful readings. Reader cancellation is handled correctly, and missing/changed photos show a readable warning instead of crashing.
- Cancelling Save Project, Open Project or New Case resumes the current case's background work. A failed project open preserves the current case and resumes processing.
- 476 local source/desktop tests passed. Source interface smoke passed navigation, 6/12/24-photo layouts and six card-review checks. The Windows EXE must pass the same new card workflow before delivery.
- Recognition models, thresholds and financial rules are unchanged; this release makes existing suggestions and recovery more usable. No new recognition-accuracy gain or staff time-saving percentage is claimed.

# v55 - Stronger Stage Clues and Faster Card Inspection

- A bounded compact-reader pass recovers isolated Full/Empty words after a load clue exists. Limited OCR typography such as fu!l is accepted only as a single-reader stage suggestion after two source-pixel reads agree. Nearby fraction ink vetoes the isolated-word interpretation. This never repairs load numbers, assigns trips or fills templates.
- Review Load Cards now offers Card Detail to cycle detected areas; Fit restores the full photo. Zoom affects the preview only. Original files and review decisions are preserved.
- The broad photo classifier stays unchanged after multi-view and tape-focus experiments failed to justify their processing/review cost. A broader yellow-paper detector was rejected because it increased unrelated review areas.
- The 90-photo validation references were reinspected. One exterior photo had been mislabeled as a document. Corrected v54/v55 results are 65 correct, zero wrong and 23 withheld on 88 scored photos. This is a reference correction, not a recognition gain.
- Local source/desktop suite: 464 tests, no skips. The matching Windows build must pass before distribution.

# v54 - More Photo Suggestions and Better Load-Card Reading

- A recalibrated compact category head makes more useful suggestions at the same 0.70 cutoff. The established measurement prior remains available to protect tape evidence. No additional runtime model download is required.
- Load-card reading adds bounded header, orientation and observed-text-region retries. Yellow strips retain nearby text across folds or glare. Original image bytes remain unchanged.
- Literal high-confidence LOAD #N readings can supply a review clue. Fused digit readings, conflicting numbers and incomplete output cannot establish a trip. Container similarity still never assigns physical loads.
- Current-version unread card candidates remain visible for review. Existing suggestions are invalidated by version changes.
- 459 local source/desktop tests passed without skips. Matching Windows executable checks are required before distributing this version.
- Checked sample results and their limits appear in RELEASE_VALIDATION.md.

# v53 - Supplied-Data Acceptance and Card Review Fixes

- Yellow paper cards use the same geometry and ink checks as neutral cards; blank yellow areas do not establish cards or loads.
- An unhelpful proposed card region no longer suppresses whole-photo reading when the reader found no load number.
- Text-only lawn-equipment comparisons withhold a false measurement suggestion while preserving the genuine tape suggestions in the expanded check. No new runtime model is introduced.
- Cache versions change so saved reader and sorting suggestions are rechecked.
- Four new synthetic regressions cover these behaviors. All 449 local source/desktop tests passed without skips.
- Supplied-data validation now covers all 14 ZIP submissions, four combined reference packages, 303 labeled category photos and actual handwritten load cards. The full results include mistakes and withheld readings; see RELEASE_VALIDATION.md.

# v52 - Smoother Review, Reliable Export and Further Validation

- Project opening and package export now run off the interface thread, show progress and support cancellation. A case cannot be changed or exported twice during a file operation.
- Review Loads has a scrollable load summary with the next action and a direct Review Selected Load button. Repeated loading photos are identified in the summary; it refreshes after template review.
- Long instructions wrap within the available width. The final checks show readable photo issues with full selected-row details.
- The saved-package screen opens the actual PDF or output folder and offers a direct return to remaining items for an incomplete draft.
- Exports to a chosen folder keep the PDF, description when complete and review report together.
- Ordinary JPEG photos retain their original compressed bytes; EXIF-rotated images remain upright. Imported PDF transparency color groups are preserved.
- Request descriptions recheck invoice arithmetic independently of a saved confirmation flag.
- Text-only measurement controls withhold confusing handheld-object suggestions. They add about 81 KB of source data and require no new deployed model. The photo-analysis cache version changes so previous suggestions are rechecked.

All 445 local source/desktop checks passed without skips. Matching Windows packaging remains required. See RELEASE_VALIDATION.md for measured results and outstanding acceptance work.
