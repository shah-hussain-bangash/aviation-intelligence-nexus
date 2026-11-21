# Aviation Intelligence Nexus

Shah Hussain Bangash · Dubai, UAE

Aviation decision-support research covering flight-data lineage, delay-model evaluation, and human-reviewed synthetic gate allocation.

## What the project demonstrates

| Area | Recorded result |
| --- | --- |
| Data lineage | Audited 2,835,101 historical US domestic flight records. Five archived imports reconciled to the stored monthly row counts. |
| Delay prediction | On the May holdout, ROC-AUC was 0.6506. At the 0.17 demonstration threshold, precision was 30.22% and about 58% of eligible flights were flagged. This operating point would create a substantial review workload. |
| Gate optimization | The solver assigned 5 of 5 flights versus 4 of 5 for the greedy baseline in one fixed synthetic scenario. An independent feasibility checker within the project verifies the proposed assignments. |

**My focus:** I lead the project across data lineage, temporal evaluation, and research review. One documented engineering decision was to switch the audit to month-by-month processing in a consistent read transaction after the all-period query exceeded temporary storage.

**Scope:** The recorded results come from historical US data and synthetic gate scenarios. They support research and demonstration. Airline deployment, operational acceptance, and measured business savings remain open.

## Reproduce one scenario

1. Use the [local setup](../DEVELOPMENT.md) and [local sign-in](../LOCAL_IDENTITY.md) guides on a fresh checkout.
2. Open **Gate Allocation Lab** with a local administrator or researcher account.
3. Run the supplied five-flight scenario with a 10-minute departure buffer, one narrow gate, and one wide gate.
4. Check for **5/5 optimized**, **4/5 greedy**, and an optimized assignment cost of **14 synthetic units**. Compare the output with the [recorded example](../GATE_OPTIMIZATION.md).

Independent fresh-checkout confirmation is pending. Record the checkout commit, environment, expected and actual results, and any setup issues when verified.

[Full technical case study](AVIATION_INTELLIGENCE_NEXUS_CASE_STUDY.md) · [Data audit](../DATA_QUALITY_LINEAGE.md) · [Delay evaluation](../DELAY_V2.md)
