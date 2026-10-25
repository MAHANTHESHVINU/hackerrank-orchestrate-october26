# Ghost Data Still Exists — HackerRank Orchestrate

**Challenge:** Ghost Data Still Exists  
**Platform:** HackerRank Orchestrate  
**Repository:** [hackerrank-orchestrate-october26](https://github.com/MAHANTHESHVINU/hackerrank-orchestrate-october26)  
**Language:** Python

---

## 1. Project Overview

This project implements a Python-based solution for the HackerRank Orchestrate challenge **Ghost Data Still Exists**.

The objective is to analyze data-deletion evidence and determine whether a resource's deletion can be considered complete, remains incomplete, or is not applicable. The solution produces structured results that can be evaluated against expected outcomes.

The implementation focuses on:

- Analyzing available evidence and data-flow information.
- Determining the appropriate deletion status.
- Producing structured, machine-readable results.
- Preserving evidence references and step-level information in the output.
- Evaluating predictions against the provided evaluation cases.
- Documenting model usage, evaluation results, and execution logs.

**Important:** A deletion status should be supported by available evidence. A proposed remediation or future verification step must not be represented as proof that deletion has already been completed.

## 2. Repository Structure

```text
hackerrank-orchestrate-october26/
│
├── README.md
├── chat_transcript.md
├── code.zip
├── output.csv
├── log.txt
│
├── code/
│   ├── main.py
│   │
│   └── evaluation/
│       ├── main.py
│       ├── diagnose_sequences.py
│       ├── evaluation_report.md
│       ├── sequence_diagnostics.md
│       └── usage_report.md
│
├── dataset/
│   └── Challenge input and supporting data
│
└── [Additional challenge files, if present]
```

### Key files

| File | Purpose |
|---|---|
| `code/main.py` | Main solution implementation. |
| `code/evaluation/main.py` | Evaluation script. |
| `code/evaluation/diagnose_sequences.py` | Sequence-level diagnostic analysis. |
| `code/evaluation/evaluation_report.md` | Documents evaluation results and observed limitations. |
| `code/evaluation/sequence_diagnostics.md` | Records sequence and field-level discrepancies. |
| `code/evaluation/usage_report.md` | Documents available model-usage and cost information. |
| `output.csv` | Structured prediction output for the challenge cases. |
| `log.txt` | Execution and interaction log. |
| `chat_transcript.md` | Project conversation transcript. |
| `code.zip` | Packaged solution and supporting documentation for submission. |
| `dataset/` | Challenge data and supporting input files. |

## 3. Requirements

- Python installed and accessible from PowerShell.
- The challenge files and dataset available in the expected locations.
- The Python dependencies required by the implementation.

Check that Python is installed:

```powershell
python --version
```

Navigate to the repository:

```powershell
cd D:\Projects\hackerrank-orchestrate-october26
```

Install dependencies only if a dependency file is provided:

```powershell
python -m pip install -r requirements.txt
```

If `requirements.txt` is not present, install the dependencies documented by the implementation rather than creating an assumed dependency list.

## 4. Running the Solution

The main script is located inside the `code` directory, not the repository root.

Run the solution from the repository root:

```powershell
python .\code\main.py
```

Run the evaluation script:

```powershell
python .\code\evaluation\main.py
```

Run the sequence diagnostics, if the evaluation data and paths required by the script are available:

```powershell
python .\code\evaluation\diagnose_sequences.py
```

**Note:** These commands launch the respective scripts. Whether a script generates or overwrites an output file depends on its implementation. Check the script's input paths, arguments, and output behavior before rerunning it against submission artifacts.

## 5. Output Format

The challenge output file is `output.csv`.

Its required header is:

```csv
case_id,deletion_status,steps_json
```

Each row represents one challenge case.

| Column | Description |
|---|---|
| `case_id` | Unique identifier for a challenge case. |
| `deletion_status` | Predicted deletion status. |
| `steps_json` | JSON array containing the structured sequence of steps. |

The status values used in the current output are:

- `COMPLETE`
- `INCOMPLETE`
- `NOT_APPLICABLE`

Each `steps_json` value must be a valid JSON array. Step numbering should be consecutive, and case identifiers should be unique and sorted according to the challenge's required ordering.

### Example format

The following is an illustrative schema example, not an actual challenge prediction:

```csv
case_id,deletion_status,steps_json
case_example,INCOMPLETE,"[{""step_no"":1}]"
```

Use the exact field structure expected by the challenge evaluator when generating real predictions.

## 6. Evidence and Decision Principles

The solution should distinguish between evidence of a completed deletion and actions that are still required.

1. **Evidence-based decisions:** Ground conclusions in the available records and evidence.
2. **Current-state verification:** A `COMPLETE` decision should be supported by evidence that establishes the required current state.
3. **Incomplete deletion:** Use `INCOMPLETE` when the available evidence indicates that required deletion or verification remains outstanding.
4. **Not applicable:** Use `NOT_APPLICABLE` only when the case's facts and challenge rules justify that classification.
5. **Remediation versus proof:** A proposed action or future verification step is not proof that the action has already succeeded.
6. **Resource identification:** Do not invent account IDs, resource IDs, or evidence references that are unsupported by the input.
7. **Structured output:** Ensure that each step follows the expected schema and numbering rules.

These principles describe the intended decision standard; they do not establish that every current prediction satisfies it.

## 7. Evaluation

Evaluation artifacts are provided under `code/evaluation/`.

Start with:

- `evaluation_report.md` — overall evaluation summary.
- `sequence_diagnostics.md` — detailed sequence-level discrepancies.
- `usage_report.md` — available information about model usage and costs.

The current evaluation report records the following results:

| Metric | Reported result |
|---|---:|
| Sample case-level status accuracy | 32/32 (100%) |
| Average field accuracy | 82.78% |
| Exact step matches | 125 |
| Expected steps | 193 |
| Predicted steps | 185 |
| Full sequence accuracy | 7/32 (21.88%) |
| Custom cases passed | 3/3 |

These are the results recorded in the project evaluation report, not a guarantee of hidden-test performance or final HackerRank acceptance.

**Known limitation:** Although the reported sample status accuracy is high, exact sequence accuracy remains low. Resource identifiers, system identifiers, operation values, and step-level fields require further verification. The evaluation report and diagnostics should be reviewed before claiming complete semantic correctness.

## 8. Output Validation Checklist

Before submitting, verify the following:

- [ ] `output.csv` contains the exact required header.
- [ ] Every expected challenge case is present.
- [ ] Case identifiers are unique and correctly ordered.
- [ ] Every `steps_json` value parses as a JSON array.
- [ ] Step numbers are consecutive where required.
- [ ] Resource identifiers and evidence references are supported by the input.
- [ ] Deletion statuses follow the challenge rules.
- [ ] Evaluation reports reflect the latest solution and output.
- [ ] `code.zip` contains the required solution files and documentation.
- [ ] `log.txt` is included in the required submission location.
- [ ] The final files have been uploaded to the appropriate HackerRank submission fields.

Structural validation alone does not establish semantic correctness.

## 9. Submission Artifacts

The repository maintains the following submission-related files:

- **`code.zip`** — packaged implementation and supporting reports.
- **`output.csv`** — structured challenge predictions.
- **`log.txt`** — execution and interaction log.

Upload each artifact to the corresponding field on the HackerRank challenge page, following the platform's instructions.

Pushing files to GitHub does not itself submit the challenge. Final submission status and acceptance must be verified on HackerRank.

## 10. Limitations and Future Improvements

Potential improvements include:

- Increasing exact sequence accuracy.
- Improving resource and system identifier extraction.
- Strengthening evidence-to-decision traceability.
- Preventing unsupported resource-ID construction.
- Expanding regression tests for edge cases.
- Re-running evaluation after each solution change.
- Ensuring that the final output and evaluation reports are generated from the same solution version.

## 11. References

- [HackerRank Orchestrate — Ghost Data Still Exists](https://www.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists)
- [Project GitHub Repository](https://github.com/MAHANTHESHVINU/hackerrank-orchestrate-october26)

---

**Project status:** Implementation and submission artifacts are maintained in the repository. Evaluation results and known limitations are documented above. Final challenge acceptance remains subject to HackerRank's evaluation.
