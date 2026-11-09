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
