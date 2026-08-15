# Listing record

## Contract

Use one Markdown file with YAML frontmatter per item. Treat every field as
optional until evidence or the seller confirms it. Do not add a required phase
or workflow-state field.

## Provenance

Classify material facts as seller-confirmed, source-supported, observed,
inferred, or unknown. Keep citations and reasoning in the Markdown body.

## YAML fields

The frontmatter uses these optional fields; use `null`, empty lists, and explicit
`unknown` values instead of guessing.

| Field | Meaning |
| --- | --- |
| `schema_version` | Version of this listing-record contract. |
| `listing_id` | Stable identifier for the item listing. |
| `item.brand` | Manufacturer or brand. |
| `item.model` | Product model name. |
| `item.variant` | Color, SKU, generation, or other variant; may be `unknown`. |
| `item.category` | Marketplace product category. |
| `item.quantity` | Number of items offered. |
| `condition.seller_assessment` | Seller's condition assessment; may be `unknown`. |
| `condition.known_defects` | Known defects or limitations. |
| `condition.included_items` | Accessories and items included in the sale. |
| `condition.tested` | Whether the item has been tested; may be `unknown`. |
| `seller.postal_code` | Seller's listing postal code. |
| `seller.fulfillment` | Available pickup, delivery, or shipping options. |
| `pricing.currency` | Currency for pricing values. |
| `pricing.recommended` | Research-based price recommendation; not an approval. |
| `pricing.approved` | User-approved price, or `null` until approved. |
| `listing.title` | Buyer-facing title proposal, or `null`. |
| `listing.description` | Buyer-facing description proposal, or `null`. |
| `listing.category` | Chosen Facebook category, or `null`. |
| `listing.condition` | Chosen Facebook condition, or `null`. |
| `media.source_directory` | Directory containing seller-provided source media. |
| `media.derived_directory` | Directory containing derived media. |
| `media.selected` | Selected media entries, including order and any rejection notes. |
| `approvals.listing_design` | Approval entry for listing design, or `null`. |
| `approvals.populated_form` | Approval entry for a populated form, or `null`. |
| `approvals.publication` | Approval entry for publication, or `null`. |
| `publication.url` | Published listing URL, or `null`. |
| `publication.published_at` | Publication timestamp, or `null`. |

## Module ownership

- Intake owns seller-confirmed item, condition, fulfillment, and open questions.
- Media owns source paths, derived paths, selected files, order, and rejection notes.
- Research owns sources and evidence in the Markdown body.
- Pricing owns recommendations; only the user supplies approved values.
- Copy owns buyer-facing title and description proposals.
- Browser posting owns form observations and publication facts.
- Approval entries record scope, decision, actor, and time.

## Revision rules

Append a decision-history entry when an approved value changes. A material change
to price, included items, condition, title, description, photo set, fulfillment,
or required Facebook fields requires renewed approval for the affected external
action.

## Buyer-facing boundary

Never expose private pricing floors, receipt identifiers, order numbers, personal
contact information, or internal negotiation notes in the listing text.
