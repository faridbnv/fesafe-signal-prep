# Validation and limits

The numerical tests are independent checks at the input-to-ASCII boundary:

- Known synthetic Excel values and their sample rate.
- Title rows, separate units, explicit mappings and mixed acceleration units.
- Rejection of missing/invalid data, duplicate axes and unknown units.
- Rejection of time gaps, repeated/reversed timestamps and excessive jitter.
- Conversion to g, signed axis permutations and subtraction order for known bias.
- Preservation of a 5 Hz sine's amplitude and phase and a constant 1 g channel.
- Rejection of a 180 Hz sine before 1000-to-250 Hz reduction, where it would alias
  to 70 Hz. The test checks that residual alias amplitude is below 0.0001.
- Exact six-line ASCII header structure, channel count, values and final newline.
- Complete command outputs and absence of an apparent result after a failed run.

The script checks the designed filter on a dense frequency grid. Kaiser design
margin helps meet the requested bounds; the report contains the measured response.
This is not a formal continuous-frequency proof or a fatigue qualification.

The default timing tolerance is 0.02 sample intervals for both individual intervals
and absolute position on the inferred grid. At 1000 Hz this is 20 microseconds.
Accepted timestamp rounding/jitter is replaced by uniform spacing and reported.
Large gaps are not interpolated. Use the original high-resolution timestamps if
Excel has rounded them. `--sample-rate` declares a rate but still checks every time.

The synthetic example contains 6001 samples at 1000 Hz from 0 to 6 seconds. X
contains 3 Hz and 180 Hz components; Y has a phase-shifted 5 Hz component; Z has a
1 g constant, an 8 Hz component and a smooth pulse. Its classification of the
180 Hz component as removable is an illustration, not a rule for vehicle data.

## Native application acceptance

Python tests cannot verify fe-safe's binary writer. Before adopting the workflow,
open `examples/acceptance.asc` in the installed fe-safe version. It must show three
channels, four samples, rate 1000 Hz, last sample at 0.003 s, and these rows:

| GX | GY | GZ |
|---:|---:|---:|
| 0.1 | -0.2 | 1.0 |
| -0.3 | 0.4 | 0.8 |
| 0.5 | -0.6 | 1.2 |
| 0.0 | 0.0 | 1.0 |

Export to AMC with Reduction Factor 1, reopen it, and check the same values,
channel order, rate and length. Repeat after transfer to the recipient's machine.
This native acceptance has not been executed by the repository's automated tests.
The example is a format check, not a fatigue duty.

Then compare your actual full-rate and reduced histories in the same FE fatigue
analysis. Include several hot spots and less-damaged locations; check changes in
life, damage and hot-spot position against the project's agreed tolerance.
