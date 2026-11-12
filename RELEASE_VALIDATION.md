# v54 - Photo Coverage and Load-Card Validation

November 12, 2026. Supplied-data developer validation; no new vendor files are required for this pass.

## Measured changes

| Check | v53 | v54 |
|---|---:|---:|
| Correct broad-category suggestions, 88 scored photos | 41 | 64 |
| Wrong broad-category suggestions | 1 | 1 |
| Withheld broad-category suggestions | 46 | 23 |
| Correct load numbers, 10 positive examples | 3 | 7 |
| Wrong load numbers | 0 | 0 |
| Withheld load numbers | 7 | 3 |
| Negative controls with a false load or stage, 7 examples | 0 | 0 |

The 90-photo category selection spans nine supplied submissions. Two ambiguous references are excluded. All 90 were excluded from the 213-example v54 head fit; references were frozen before evaluation. They come from the existing property corpus, not untouched new properties or an independent third-party audit. Suggestion coverage rose from 42/88 (47.7%) to 65/88 (73.9%); precision among suggestions rose from 41/42 (97.6%) to 64/65 (98.5%). One receipt photographed against a property background remains misclassified. Withheld photos remain review work.

The card replay combines seven development positives and three separate positives. Development results improved from two to six correct numbers; the separate three returned one correct and two withheld in both versions. Thus the combined improvement is real on these examples but does not establish improved generalization to new handwriting. Positive stage results remain three correct and four withheld; no stage-recall improvement is claimed. All seven negative controls remained clear. Reading proposes review clues only: appearance does not identify physical trips, and conflicts remain unresolved.

## Software and package checks

459 local source/desktop tests passed without skips. New regressions cover retry geometry and pixel bounds, unchanged originals, literal hash markers, conflicting readings, invalid vectors, measurement-prior retention, unresolved reused-container evidence and current-version unread cards. The original four reference packages were regenerated: all 309 selected images and 13 financial pages retained their source content. Existing missing evidence and invoice conflicts remain visible rather than being marked complete.

A matching Windows workflow must pass source tests, bundled offline photo/card/annotation checks, navigation at multiple photo counts and executable DOCX/PDF export before distributing the portable archive. The delivered validation record identifies its exact source and artifact hashes.

The work-laptop trial remains necessary to measure company-device compatibility, staff review effort and actual elapsed time. No staff time-saving percentage is claimed. This change does not alter financial policy rules.

## Historical validation

# v53 - Supplied-Data Acceptance

November 9, 2026. The user accepts the supplied corpus as the practical accuracy-test scope. No additional photo submission is required to finish this developer test pass. This does not convert development cases into untouched-property evidence.

## Completed developer checks

- 449 local source/desktop tests passed, no skips, including four new regressions for card localization/fallback and measurement controls.
- All 14 supplied ZIPs imported successfully. 6,776 source files imported uniquely within their submissions, decoded where images, retained their hashes and were not duplicated on repeat import. Duplicate submissions under alternate archive names were excluded.
- Four reference-directed package exports again preserved all 309 selected photos and all 13 imported financial pages, including their exact text and rendered pixels. The same expected source-evidence and financial conflicts remain visible; no vendor record was silently corrected.
- Broad category testing: 303 visually labeled photos, 294 scored and 9 excluded as ambiguous. Final results: 147 correct suggestions, 3 wrong suggestions and 144 withheld. Suggestion precision is 147/150 (98%); suggestion coverage is 150/294 (51%). Withheld results are review work, not successes. The 81-photo confirmation subset was disjoint from the first expanded sample and labeled before predictions; it returned 38 correct suggestions, 3 wrong and 40 withheld. These residual mistakes were not used to alter its reference labels or force a pass.
- Actual handwritten/printed load-card check: seven positive load numbers, two correct suggestions and five withheld, no wrong numbers. Four positive stage references: three correct, one withheld. Three negative controls: no false load or stage. This small test establishes reader behavior on those samples, not high recall or a fully automatic reading workflow.

## Distribution and remaining decisions

The v52 baseline passed 445 Windows tests and offline frozen photo/card/annotation, interface and executable export checks in run 42688684723. The v53 update requires its own successful matching workflow before distribution. Its exact run and executable hashes are recorded with the delivered portable draft rather than inferred from the baseline.

The software workflow is implemented. The next planned user step is the work-laptop trial for company-machine compatibility, real review effort and elapsed time. Those measurements cannot be made on this host. The exact $2,500 boundary and gross/net policy basis remain deferred; no new $45/CYD rule was introduced.

Real source conflicts are package-specific review work rather than unfinished application features. Repeated photographs cannot prove distinct progressive stages or trips; unreadable or unrecognized handwriting needs manual selection; an invoice disagreement needs a vendor correction. The app must preserve those findings rather than label the original package complete.

## Earlier v52 detail

# v52 Source Candidate - Release Validation

November 9, 2026. Prepared for review; not a replacement Windows release yet.

## Final software checks

445 source and desktop tests passed with no skips on the local Linux test host with a graphical display. This includes actual app export, selected-load navigation, saved-file actions, cancelled export/import, UI event processing during export, source changes, invoice arithmetic, duplicate evidence, portable projects, export corruption rollback and same-computer concurrent-export refusal. The final modified source has not run as a Windows frozen executable.

The prior v51 Windows run 42540173292 passed 432 tests with no skips, plus frozen photo, load/annotation reader, interface and executable checks. Its head was 3f7fda5d40026d83fd3bcc43ab454cacc4fa34e6; PR merge checkout e532b10536366f7d183f85032285dc82940b1aa7. Portable archive SHA-256: e25ff0b2a2b06e979ce5d2fd1d15e6d24cdcc1f9f15ecc8af89ee1b43ba39efd. That archive does not contain v52 changes.

## Real-source package comparison

Four supplied completed examples were reconstructed using their existing invoice, bid, RBB, calculator, measurement, progression and receipt sources. All 309 selected extracted source images were found in the generated PDFs by decoded-image hashes. All 13 imported financial pages retained their original text and exact rendered pixels. The four generated PDFs total 73 pages, including an extra supporting view in one case. Rendered load and property-grid pages were inspected.

This is reference-directed assembly, not independently verified physical-trip reconstruction. The examples are not clean acceptance baselines: duplicate photos occupy multiple loading stages in some examples, and one invoice states 48.84 CYD while its three calculator screenshots total 48.64 CYD. The software flags these conflicts and withholds a conflicting financial description. Explicitly reviewed during-removal, unloading and first-10 evidence was not invented to force a Complete result. A higher-value example also provides only one of the three required bids. These unresolved examples remain drafts.

## Broader raw-photo check

60 photos from five supplied submissions were visually labeled before this run's predictions. Five ambiguous broad-purpose references were excluded; 55 were scored. The historical training/development exposure of these properties is unknown, so this does not establish untouched new-property accuracy.

| Version | Suggestions made | Correct suggestions | Wrong suggestions | Withheld |
|---|---:|---:|---:|---:|
| Previous category behavior | 28 | 25 | 3 | 27 |
| Final measurement control | 25 | 25 | 0 | 30 |

The three removed suggestions were a spray can and two lock close-ups classified as measurements. Text-only competing-object controls add no runtime model download and do not assign any category, trip or template slot. The tradeoff is that two additional reference tape photos were withheld: 30 of 36 reference tape photos received measurement suggestions, versus 32 previously. The guard was developed against these errors; it needs independent validation rather than a universal accuracy claim. Thirty withheld results on the 55 scored examples are still review work. No overall 100% accuracy or measured staff saving is claimed.

## Large export and usability

The same synthetic 1,000-photo/130-page export improved from 26.06 seconds to 1.427 seconds after preserving ordinary JPEG compression. The PDF shrank from 18,875,331 to 8,142,387 bytes. Peak process RSS for the optimized check was about 76 MB. Portable save/resume preserved all 1,000 selected property-photo sources. These are developer-host results on small synthetic images, not work-laptop, full-resolution vendor-image, model-inference or staff-efficiency measurements.

The four main pages and the saved-package screen were inspected at desktop size. The load summary is scrollable, instructions wrap, selected issues expose their full text, and export actions remain available in the footer. Automated window, grid and navigation checks passed. A first-time staff walkthrough has not been performed.

## Remaining acceptance gates

1. Publish the reviewed source only after push authorization/access is available, then run the matching Windows workflow and test its frozen reader, interface, source modules and export. Do not relabel v51 as v52.
2. Resolve source-evidence and invoice conflicts in a real acceptance case. Do not invent photographs, trip relationships or supporting bids.
3. Use independently checked positive examples from genuinely new properties and handwriting styles to measure generalization. Current development and regression samples cannot establish that result.
4. Run a first-time workflow on the work laptop, checking usability, output correctness, review effort and elapsed time against the existing process.
5. Confirm the exact $2,500 boundary and gross-versus-net basis. The user deferred this answer. Existing conservative behavior and RBB requirements remain; no $45/CYD rule was introduced.

Similar-looking reused containers still require distinct source evidence or an explicit review decision. No threshold was relaxed to force physical-trip or stage assignments. No source photographs, property records, embeddings or private audit data belong in the repository update.
