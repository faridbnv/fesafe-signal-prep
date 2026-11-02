# Implementation plan

1. Establish the documented ASCII header, supported binary formats and loading controls.
2. Implement automatic table discovery with explicit mappings for ambiguous layouts.
3. Validate complete time histories and preserve signed, synchronized acceleration.
4. Add explicit integer-factor reduction with a verified symmetric anti-alias FIR.
5. Export portable ASCII, diagnostic plots, provenance and handover instructions.
6. Write a concise illustrated guide with math and fe-safe click sequences.
7. Test normal inputs, ambiguous layouts, unit conversions, timing faults and alias rejection.
8. Verify installation from a fresh checkout, publish publicly and check CI.

The implementation does not infer gravity removal, sensor bias, filter bandwidth,
FE-load equivalence or fatigue equivalence. Full-rate output is the default.
fe-safe performs the final AMC export; this repository contains no vendor binary writer.
