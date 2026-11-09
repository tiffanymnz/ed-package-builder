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
