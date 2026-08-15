# Browser posting procedure

## Entry precondition

Begin only when `approvals.listing_design` is a current, affirmative approval
whose recorded scope covers the final price, title, description, selected media
and their order, fulfillment, condition, and every known platform choice. Read
the approval entry's scope, decision, actor, and time alongside the proposed
values. A recommendation is not approval.

Before form entry, compare the approved design with the canonical listing
record. If price, title, description, photo set or order, included items,
condition, fulfillment, or a required Facebook field has changed, the design
approval is stale for the affected action. Preserve the draft and obtain a
renewed listing-design approval; do not silently carry the earlier approval
forward.

## Inspect the live form

Use an available signed-in browser capability by default. Inspect the live form
after opening it: labels, choices, required indicators, validation, visible
restrictions, and the review/publish controls are the authoritative current
interface. Do not rely on a permanent Facebook field schema or a particular
browser, automation tool, or page layout.

Record only what is visible or entered. If the form offers a consequential
choice that the approved design did not resolve--for example a category,
condition meaning, shipping commitment, location visibility setting, payment
or delivery term, or audience setting--stop and ask for a decision. Do not
choose on the seller's behalf.

## Mapping and reversible entry

The current listing-design approval authorizes only reversible form entry. For
each value, make a mapping record in the listing record or posting notes:

| Canonical value | Facebook field used | Normalization or platform-generated change |
| --- | --- | --- |
| `listing.title` | Observed title field label | Exact entered text; any truncation or normalization. |
| `pricing.approved` and `pricing.currency` | Observed price field label | Exact entered amount and displayed currency or formatting. |
| `listing.description` | Observed description field label | Exact entered text; any truncation or normalization. |
| `listing.category` | Observed category selector | Selected path; note a suggested or substituted category. |
| `listing.condition` | Observed condition selector | Selected visible label and any platform interpretation. |
| `seller.fulfillment` | Observed delivery, shipping, or pickup controls | Exact selected options and any resulting platform text. |
| `seller.postal_code` | Observed location field | Exact locality level displayed; do not record or expose more than necessary. |
| `media.selected` | Observed photo/video uploader | Approved filenames in order; note reorder, rejection, or processing. |

Fill only a value or choice that is already resolved by the approved design.
Do not resolve an unknown, accept an unanticipated consequential default, or
make a claim the record cannot support. Do not enter private notes, research,
receipt identifiers, contact details, or unpublished pricing floors.

### Media upload

Upload only the approved selected source files or approved derived files named
in `media.selected`, in the approved order. Confirm the visible post-upload
order and record any upload-side reorder, crop, compression, rejection, or
other platform-generated change. A file that was not selected or a material
change to the selected set requires renewed design approval before use.

## Preflight and populated-form review

After reversible entry, provide concise **Preflight** output: title, displayed
price and currency, category, condition, fulfillment, visible location level,
media count and order, and every observed normalization, warning, restriction,
or unresolved choice. Include a visible form review or screenshot when
practical and safe to retain; redact or avoid private information.

The seller must review the populated form and record a current affirmative
`approvals.populated_form` decision for that visible state. This approval says
the form is ready for publication. It does not authorize clicking Publish.
If any mapped field or visible platform change differs after review, repeat the
preflight and obtain a renewed populated-form approval.

## Separate publication decision

Form entry, populated-form review, and final publication are distinct external
actions. After the populated-form approval, request a **separate explicit**,
current publication decision recorded in `approvals.publication`. Do not infer
it from delegated judgment, a listing-design approval, populated-form approval,
or the seller being unavailable. Do not click the platform's publication or
confirmation control without that decision.

## Completion record

After publication succeeds, capture the listing URL in `publication.url`, the
publication timestamp in `publication.published_at`, the final displayed price,
and every platform-generated change observed at publication. Preserve the
field mapping, final review evidence when safely retainable, and any relevant
platform confirmation text. Report completion without exposing private account
or location details.

## Failure recovery

Never bypass a login challenge, account-security check, confirmation screen,
warning, category restriction, or platform limitation. Preserve the completed
reversible work and give a recoverable failure report:

| Failure | Safe recovery |
| --- | --- |
| Login or expired session | Stop; state that sign-in is required. The seller completes sign-in in their browser, then re-inspect the form and its values. |
| Account security check | Stop; do not handle credentials, codes, identity checks, or recovery flows. Ask the seller to complete the platform's security step. |
| Unsupported category or required category change | Record the visible restriction and proposed alternatives. Obtain an explicit decision and renewed approval if the selection or buyer-facing design changes. |
| UI change or an unfamiliar consequential field | Record the visible labels and state. Do not guess a mapping; ask the seller to resolve the choice or approve an updated design. |
| Upload failure | Preserve approved file paths and the visible error. Retry only the same approved file when the error is transient; otherwise stop for a changed-file or changed-order decision. |
| Browser loss, crash, or session interruption | Treat the populated state as unverified. Reopen the live form, inspect every mapped field and media order, then repeat Preflight and obtain the needed current approval. |
| Platform warning or restriction | Preserve the exact visible warning and stop. The seller decides whether to satisfy it, change the listing, or abandon publication; never work around it. |

Each recovery report names completed work, preserved artifacts, the exact
blocker, the safest next action, and any manual seller step. A recovery never
converts a prior approval into publication authority.
