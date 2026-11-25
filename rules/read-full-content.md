---
alwaysApply: true
---

# Read Full Content Before Deciding

When making any decision based on external content — email body, web page, document, message thread — **always read the complete content**. Never base a decision on a preview, snippet, truncated summary, or subject line alone.

## The rule

Before drawing any conclusion from external content:

1. Fetch the full source (not a summary or preview field)
2. Read the complete text
3. Only then make a decision

For Gmail specifically: use `format: "full"`, decode `payload.parts[]` (find `mimeType: "text/plain"`, base64url-decode `body.data`). `messageText`, `preview`, and `snippet` fields are truncated — acceptable for **display only**, never for decisions.

## Clipped Sent Intake

Narrow exception for partial judgments in NanoClaw Admin promise-tracker Sent intake.

1. The approved Gmail owner attempts a full read and identifies a clipped or oversized Sent body.
2. Judge only the sanitized subject and contiguous readable beginning of the authored body. No readable beginning means no content judgment.
3. Mark every surfaced partial judgment “partially read”. Never infer missing content.
4. Follow the installed Admin rule `rules/email-read-full.md` for this path. A partial receipt does not certify a complete source read.

Every other case follows the complete-read rule. Later correspondence still requires a complete read.

## Applies to

- Task due date assignment from email links
- Email importance classification
- Any action, recommendation, or classification based on content from an external source
