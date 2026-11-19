# Label versions

- `baseline-v1/golden/test_labels_v1.csv` (frozen): labels of 29-30 Oct 2026. Reference TP 3 / FP 3 / FN 3 / TN 33.
- `test_labels_v1_1.csv` (30 Oct 2026, Yuliia): one change, F-003 sentence 4. It is a synthesis of USER IMPACT + RECOMMENDATION
  (same content reworded across two fields), so by the single rule "a synthesis from several fields = Needs Human Verification"
  (the same as F-005 s7 and F-007 s7) the gold verdict is Needs Human Verification, not Supported.
  The judge's "Unsupported" for this sentence is now a TP (different verdict). Reference v1.1: TP 4 / FP 2 / FN 3 / TN 33.
  Reason for the change: consistency of the criterion, decided before the next judge change; the results of the judge are not tuned to it.
- Results recorded before this change are valid for v1; `lab/report.py` and `lab/score_golden.py` use v1.1 from now on.
