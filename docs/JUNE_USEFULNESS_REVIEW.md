# Review the saved June agent answer

The read-only `agents.june_usefulness_review` command prepares a private packet from a pinned, passing live June HTTP rehearsal. It requires the complete check inventory, completed bounded provider calls, an unreviewed draft, the exact report fingerprint and canonical June evidence. This is unsigned content consistency, not source authentication or proof of reviewer identity.

From the project folder, use a retained receipt's actual SHA-256 and a new private output folder:

```powershell
.\.venv\Scripts\python.exe -m agents.june_usefulness_review prepare --receipt .local/REHEARSAL/evaluation.json --receipt-sha256 EXACT_RECEIPT_SHA256 --output .local/NEW_REVIEW
```

The command reads the receipt and committed public aggregate evidence. It creates `packet.json`, `review.txt` and `annotations.json`. It does not open an account database, call a provider, rerun June inference, change the agent's review status or overwrite an existing export. The readable text includes the objective, findings, citations, source text and execution revision. Keep these files private; do not add passwords or personal details.

Read `review.txt` and its source evidence. Edit `annotations.json` personally: leave unknown answers blank or `uncertain`; use `yes` or `no` only for your own judgement. Set `source_checked` and `own_assessment` only after actually completing those steps. The per-claim fingerprints and packet fingerprint must remain unchanged. All exported ratings start blank.

Compute the SHA-256 of the unchanged packet and edited annotations, then assess:

```powershell
Get-FileHash .local/NEW_REVIEW/packet.json -Algorithm SHA256
Get-FileHash .local/NEW_REVIEW/annotations.json -Algorithm SHA256
.\.venv\Scripts\python.exe -m agents.june_usefulness_review assess --packet .local/NEW_REVIEW/packet.json --packet-sha256 EXACT_PACKET_SHA256 --annotations .local/NEW_REVIEW/annotations.json --annotations-sha256 EXACT_ANNOTATIONS_SHA256
```

Use lowercase hashes. Assessment prints an unsigned declaration, not an approval. Missing acknowledgements, blank fields or uncertainty remain `pending`. A complete negative assessment is `declared_needs_revision`; all-positive complete declarations are `declared_acceptable`. Neither verifies identity, establishes independent review, changes the saved draft or closes a production gate. Test ratings use synthetic fixtures only.

Focused verification: `python -m unittest tests.test_june_usefulness_review -v`.
