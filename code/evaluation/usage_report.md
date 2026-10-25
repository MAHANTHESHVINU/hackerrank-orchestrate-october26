# Model Usage and Cost Report

## 1. Scope and Verification

The agent processed 518 deletion requests and generated `output.csv` in the reported execution of the Ghost Data Still Exists challenge.

The inspected Python source files did not reveal detectable model API integrations or token-usage instrumentation. The available evidence therefore does not establish which models, if any, were called during the final dataset run.

This limitation does not prove that no AI models were used during development or through external tools.

## 2. Model Providers and Calls

| Metric | Verified result |
|---|---|
| Model providers used during final execution | Not verifiable |
| Model identifiers used during final execution | Not verifiable |
| Primary model calls | Not recorded |
| Auxiliary model calls | Not recorded |
| Total model calls | Not verifiable |
| Model-usage instrumentation in inspected Python source | No detectable instrumentation found |

## 3. Token Consumption

| Metric | Verified result |
|---|---|
| Input tokens | Not recorded |
| Output tokens | Not recorded |
| Total tokens | Not calculable |
| Average tokens per request | Not calculable |
| Minimum tokens per request | Not recorded |
| Maximum tokens per request | Not recorded |

Token consumption cannot be calculated reliably without provider usage metadata, API logs, or equivalent records.

## 4. Financial Cost

| Metric | Verified result |
|---|---|
| Input-token cost | Not verifiable |
| Output-token cost | Not verifiable |
| Total model cost | Not calculable |
| Average model cost per deletion request | Not calculable |

Unverified cost must not be interpreted as zero cost.

## 5. Execution Metrics

| Metric | Result |
|---|---|
| Deletion requests processed | 518 |
| Output data rows | 518 |
| Output file | `output.csv` |
| Independently verified runtime | Not recorded |
| Verified throughput | Not calculable without verified runtime |

## 6. Implementation Overview

The inspected implementation uses Python logic for evidence processing, identity resolution, policy checks, and deletion-status and step generation.

The source search did not identify model API integration in the inspected Python files. Claims of LLM-assisted classification, measured token savings, or model-call optimization during the final run could not be substantiated from the available evidence.

## 7. Future Usage Instrumentation

For a future run, record:

1. Model provider and exact model identifier.
2. Input and output token counts from provider usage metadata.
3. Successful calls, failed calls, retries, and auxiliary calls.
4. Execution start and end times.
5. Cost calculations using verified pricing and billable usage.
6. Per-request averages with an explicitly stated denominator.
7. Supporting usage logs or provider records for auditability.

## 8. Conclusion

The reported run processed 518 deletion requests and generated the corresponding output file. Actual model-call counts, token consumption, model costs, runtime, and throughput could not be independently verified from the available records.

This report distinguishes confirmed execution results from unmeasured usage metrics and does not present unsupported figures as measured facts.
