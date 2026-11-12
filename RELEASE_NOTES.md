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
