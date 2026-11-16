# ED Package Builder v51 — Measured Results and Release Gate

Status: source candidate, not a replacement Windows release. v50 remains the last Windows-tested release. The user approved the 7.49 MiB annotation reader on November 8, 2026. It is now bundled in this source candidate; Windows validation remains pending.

## Fresh source-photo evaluation

Reference labels were frozen before inspecting this run's predictions. The 88-photo set has not been established as wholly unseen during historical training; these results do not establish accuracy on new properties or handwriting styles.

| Check | Result | Interpretation |
|---|---|---|
| Broad photo purpose, 88 originals | 77 suggestions; 76 matched checked labels; 11 withheld | One pile close-up incorrectly suggested as a measurement. Some references accept both visible container and measurement content. |
| Before/After, 49 confidently labeled property scenes | 35 suggestions matched; 14 withheld | Another 12 ambiguous property scenes are unscored. No claim about their predictions. |
| Three handwritten loading-stage annotations | v50 recovered 0; v51 optional reader recovered 3 | Quarter, Half and Full; very small development sample, not general handwriting accuracy. |
| Template proposal given explicitly checked load membership | Quarter, Half and Full proposed in corresponding boxes | Empty, Three Quarters and a second Full view left unfilled; no invented trip labels or duplicate photo placement. |
| Fresh current-reader scan, 336 originals | 157 candidates; no readable load-number results | Source sample lacks readable physical-trip cards. Prior cached replay did not establish this reader's current accuracy. |
| Compact reader on 12 load cards plus 53 controls | 0 recovered load cards; 0 false positives on controls | Rejected as a replacement for the existing load-card reader. |
| Experimental feature matching of reused containers | 0 correct, 1 wrong, 29 unresolved on nonseed references | Rejected; not included in app. |
| Similar-view review assistance on 88-photo set | Two property-review groups containing 7 unresolved photos | Review convenience only, not verified stage/trip assignments. Not a measured staff time saving. |

No source photographs were uploaded to public model services. Existing model assets were used locally. Developer-host speed is not work-laptop speed.

## Candidate changes

- Detect large annotations above embedded scene photos; parse stage evidence independently of load numbers.
- Optional compact handwriting reader uses the existing inference runtime; 7,850,705 bytes (7.49 MiB) extra model data. The approved model is bundled with the app, with no extra installation or copied model cache. No Paddle runtime is included.
- Fraction preprocessing aligns existing visible glyphs; it does not add or substitute digits. Plain digits and dimensional text are rejected as stage fractions. Conflicting stage claims are withheld.
- Stage-only evidence can assist template proposals after source-checked load assignment, with explicit user confirmation before placement.
- Similar-view review batches use fixed representative similarity, date/category boundaries, and source checks. They never assign physical trips or stages.
- Load-card hints reject outdated model versions or changed sources; dismissed cards remain accessible for restoration.
- Export read-back integrity checks and a same-computer export lock protect against corrupted copies and simultaneous writes.
- Removed the irrelevant $45/CYD exception from pending requirements. No active $45 policy trigger was present. Exact $2,500 boundary and gross/net basis remain unspecified by policy owner.

## Verification

431 source tests: 359 passed, 72 GUI tests skipped because no graphical display was available. The fraction negative controls, source immutability, changed-source rejection, batch grouping boundaries, export corruption rollback and concurrent-export refusal passed. Windows frozen-executable and GUI validation must run before a v51 Windows release. No new end-to-end staff time or first-use usability result is claimed.

## Export recovery, in plain language

The PDF and separate description/report cannot appear at precisely the same instant as one file-system operation. An interruption can briefly leave files from different exports. The journal restores the previous complete set when recovery runs. The candidate additionally checks the bytes written and prevents two app instances on the same computer from exporting to the same folder simultaneously. Physical drive damage, destroyed backups and storage devices that falsely report successful durable writes cannot be guaranteed recoverable. This is not a promise of cross-computer locking on network shares.

## Remaining release gates

1. Storage approval is complete. The bundled reader passed a direct CPU inference check; its small handwriting benchmark supports a narrow benefit, not broad load-card improvement.
2. Windows packaging and GUI regression validation after the final asset decision.
3. Independently checked photos from additional properties and handwriting styles to establish generalization. Existing examples cannot prove that.
4. Work-laptop and first-time staff trial to measure actual effort saved.
5. Authoritative $2,500 boundary and gross/net basis. Do not invent a policy answer.

Unclear reused-container trips remain a review decision unless distinct source-bound evidence supports them. No threshold was relaxed to force assignments.

## Approved integration verification

The bundled model hash and Apache license passed checks. A direct CPU inference read synthetic Full text correctly without copying the model into a user cache. The Windows build now bundles these assets, and its frozen card-reader test exercises the annotation model. Reader cache version advanced to 7 so prior no-annotation results do not prevent reanalysis. Windows CI has not yet run for this candidate.
