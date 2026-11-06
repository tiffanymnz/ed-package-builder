# v50 Validation Candidate

Coordinated changes: readable scrollable photo grids; safe batch undo; checked trip-endpoint review queues; final-invoice version selection; source-bound combined-invoice confirmation that survives portable project reopening; interrupted-export recovery; tape-region navigation; local storage/performance diagnostics; split-line card labels; Unicode loading fractions. No new model assets.

## Validation status

Local final suite and Windows validation are being completed. The first Windows pass exposed a read-only fsync incompatibility; this candidate opens staged files writable before flushing. Do not use the earlier v50 checkpoint as the final release.

An actual local CPU photo model smoke check passed. Source SHA-256: 583fd1110a514667812fee7d684952aaf82a99b959760c8d7dca7e0ab9839299.

## Existing-case replay

336 photos; eight explicitly checked endpoint photos seeded four trips. Of 26 non-seed package-reference photos: three correct load proposals, zero wrong proposals, 23 unresolved. Sixty uncertain photos entered review-only trip windows. They are not sixty verified assignments. Cached review preparation was approximately 0.21 seconds; warm run approximately 0.24 seconds on this host. These times exclude model inference and human review.

Seventy historical OCR readings showed no changes under the split-line parser. Its new layout support is covered by synthetic regression checks, without a demonstrated accuracy increase on this example.

## Remaining practical limits

- Existing examples and package-derived references do not establish accuracy on new properties. A corrected reference may itself change the score.
- Blurry, occluded or illegible cards and tape endpoints remain unresolved. No dimensions are invented.
- Reused containers do not establish trip identity. Date-only or conflicting clocks cannot create a checked time window. Overlapping/interleaved trips are withheld; clear endpoints require explicit checking.
- Empty/quarter/half/full card text describes visible labeling, not a proven measured volume. Property work stages require visible evidence.
- Photo batches can be corrected together; a first-time staff walkthrough and measured time saving on the actual work laptop are still unverified.
- The application still needs the existing local model files. Setup requires storage and an initial download; no extra model was added here.
- Journal recovery handles an interrupted process, but multiple separate output files cannot be replaced simultaneously. Hardware that fails to honor durable writes and damaged backups cannot be guaranteed recoverable.
- The exact $2,500 bid boundary, gross-versus-net threshold basis and any $45/CYD rule need authoritative confirmation. The app does not invent the policy.

This is a candidate until the exact Windows executable passes native model, interface and export checks.
