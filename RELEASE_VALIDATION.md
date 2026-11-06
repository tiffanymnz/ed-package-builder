# ED Package Builder v49: Validation and Release Status

**Status: release candidate, not final.** There is a narrow, measured recognition improvement and several review/recovery fixes. The source is uploaded to codex/accuracy-release-v49 in draft pull request #1. Windows validation is running; earlier attempts exposed workflow setup issues and outdated Windows test fixtures, now corrected. The first complete Windows suite ran all 398 checks and reported four failures and one error; its path-alias expectations and source-bound evidence fixtures were corrected without loosening application checks. No successful current Windows executable is claimed yet.

## Implemented

1. **Standalone handwritten half fractions.** The reader now checks a visible isolated numeral/divider/denominator layout rather than converting plain “12” into “1/2.” The rule proposes Half only for a supported two-shaped denominator, with no adjacent unit/equation text. It is restricted to localized card crops with a usable load-number reading. Conflicting literal Full/Quarter text vetoes the result. It does not change measured fill or invoice quantities. It is a proposal requiring an evidence choice.
2. **Source-specific load review.** A checked card keeps its own package-load mapping when the number is reused elsewhere. The mapping does not spread through conflicting dates, locations or package numbers. A disagreement between a checked photo-load assignment and its card mapping remains a conflict rather than silently preferring one.
3. **Hidden cards stay hidden, and can be restored.** Previously a dismissed card could still supply a number clue. It is now removed from grouping and stage clues. Show Hidden Cards lets the reviewer inspect and confirm a card again; confirming the current source restores it.
4. **Location text is visible.** Street clues from current, source-matched OCR are displayed for review. Different street text can be a nearby GPS address; it is not proof of a wrong job. Conflicting card location clues withhold global propagation, while an explicit source-specific mapping remains available.
5. **Calendar review buckets.** Where one observed card number is associated with a date, the app can offer same-date container photos together for bulk inspection. Multiple numbers that day, conflicting dates/locations, documents, property-stage photos and changed files are excluded. These are review-only buckets: they cannot supply template load evidence until the photos are explicitly checked and assigned.
6. **Review density.** The photo organizer offers 6, 12 and 24 previews per page, preserving selection when the layout changes. Six remains the default. Compact modes shorten captions; larger views and inspection remain available. Fewer navigation pages is not a measured staff time-saving claim.
7. **Every invoice is accessible.** Review Costs now exposes all invoice attachments, explains combined figures and asks the reviewer to exclude replaced versions and avoid deducting Initial Services twice. Multiple attachments are not silently merged by OCR.
8. **Stronger Windows verification.** CI now fetches and hash-verifies the existing pinned card-reader assets outside the application bundle, blocks inference network access, and runs a synthetic card through the actual frozen reader. The interface smoke path exercises all four workflow pages plus 6/12/24-photo views. Synthetic UI screenshots are captured when the Windows desktop permits it; missing capture is reported. These checks have been prepared, not executed on Windows here.

## Recognition validation

A fresh offline run used the existing 12-card development set and 53 negative controls. Original photo hashes were verified unchanged. Labels and filenames were not passed into recognition.

| Check | Result |
|---|---:|
| Load number suggestions on 12 cards | 10 correct, 0 wrong, 2 unresolved |
| False load numbers on 53 controls | 0 |
| New Half suggestions on the two difficult fraction photos | 2 recovered |
| Half-shape detections on the other 63 regression images | 0 |

Both recovered fraction photos show the same handwritten board/style in different views. They are **not independent handwriting examples**. Synthetic negative checks also cover plain 12, 1/3, 1/4, 1/7, letter Z, nearby unit text and unreadably small crops. This does not establish broad fraction accuracy, other handwriting styles or true physical fill. The detector is deliberately limited; unsupported fractions remain for review.

Load-number accuracy did not improve in this release. Two small/unreadable cards remain unresolved. The complex multi-line/circled boards from the other work order remain unresolved from the prior audit; no new claim is made for them.

A new action-scene prompt experiment was also rejected. It did not reliably distinguish actual debris removal from a stationary loaded trailer. No new During classifier or extra model weights were installed. Existing Before/After behavior and the v48 same-case example replay remain **25 correct, 0 wrong, 27 unresolved out of 52**, not a newly measured independent score.

## Template placement and recovery

After explicitly mapping one source card to Package Load 1, the Half photo became the Half proposal **without manually entering its fraction/stage**. It was not proposed in either Full box. A separate test mapping for Package Load 3 produced two distinct Full proposals. Missing stage evidence stayed empty.

These mappings are test inputs, not approved live package assignments. This tests assisted placement from checked load identity and source card content; it does not independently certify physical volume or every template position.

The calendar review buckets were excluded from the template index. In the supplied job, the available OCR supported only **one additional review-bucket photo**, so no substantial grouping-coverage improvement is claimed. Source identity and OCR gaps remain constraints.

The actual 508-file project saved and reopened with the fraction evidence and rounding choice intact:

- Archive: **122,822,303 bytes**.
- Save: **3.87 seconds**; reopen: **0.41 seconds** on this test host.
- Models are not embedded in the project. These timings are not work-laptop or staff-efficiency measurements.

## Software and package checks

- **398 checks: 328 passed, 70 skipped; no executed check failed.** Skips include graphical/platform checks. The added density UI check cannot run in this environment because its local display socket is blocked.
- Source launcher and synthetic combined Word/PDF package smoke: **PASS**.
- Actual ONNX CPU card-reader source smoke, on a clean synthetic card: **PASS**, with original pixels unchanged. This is runtime verification, not handwriting accuracy.
- Fresh 65-image native reading run: completed offline.
- Placement, source conflict and 508-file project recovery replay: **PASS**.
- Current Windows executable, full frozen interface and screenshots: **pending**.

Two old regression expectations were intentionally corrected: checked source cards now remain represented even without clock bounds or when another source uses the same number differently. Non-card neighbors still receive no file-order inference. New tests enforce no propagation, conflict retention, dismissal, restoration, location handling, calendar isolation and fraction negatives. Passing software tests does not establish recognition accuracy.

## Storage and privacy

No new model assets or runtime packages are introduced into the user application by v49. The existing optional card-reader assets remain 277,470,179 bytes; the existing photo model is unchanged. The added fraction analysis uses the current image library and stores small source-bound metadata, not duplicate photos. CI's test weights live only on the runner and are not bundled into the Windows artifact.

Public source contains no vendor photos, raw OCR caches, property records or private evaluation outputs. Private protocols and results are stored separately. Model inference stayed local; test asset downloads retrieve public weights, not vendor data.

## Remaining limits and final-release gates

| Area | Remaining limit / required verification |
|---|---|
| General card reading | Tiny, blurred, clipped, circled and multi-line cards can remain unreadable. A readable fragment is not a complete board identity. |
| General fractions | The new rule supports a narrow standalone handwritten-half layout. Other layouts, denominators and handwriting styles need separate examples and validation. |
| Repeated containers | Similar appearance does not establish a trip. Missing or contradictory clocks, reused numbers and unsupported source context still require checked assignments. |
| Physical loading stage | A card label is evidence, not independent proof of occupied cubic volume. Obstruction, irregular debris and poor viewpoints require review. |
| Measurement selection | Ranking does not reliably verify all tape endpoints, markings or whether a view measures length versus width. |
| Property stages | Independent During recognition and broad Before/After generalization are not established. Date/name alone never assigns a stage. |
| Reference quality | Duplicate template source selections and incomplete receipt/load links must not be treated as clean training truth. |
| Financial policy | The exact $2,500 boundary and threshold amount basis remain unconfirmed in the source audit. The unverified $45/CYD comparison rule is not invented. Existing ambiguous-case checks remain. |
| Invoice revisions | The user must exclude replaced versions and verify combined totals; incompatible revisions are not silently combined. |
| Windows | Source uploaded; current frozen/native/UI checks must pass before the Windows artifact is considered verified. |
| First use / efficiency | A real first-time-user walkthrough and time comparison have not occurred. Navigation density is implemented but is not proof of time saved. |
| Export interruption | Caught write failures are rolled back and portable projects are verified. Power-loss durability across multiple separate export files is not guaranteed. |

The v48 rate-based HUD deduction, explicit rounding method, bid quantity normalization, JPEG/PDF attachments, required package documents, no-double-deduction checks and portable project workflow are retained. The source update is concrete and tested within the limits above. Calling it final before the remaining platform and real-use gates pass would be misleading.
