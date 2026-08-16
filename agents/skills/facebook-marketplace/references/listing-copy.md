# Listing copy

## Claim boundary

Draft buyer-facing copy only from facts that trace to seller confirmation,
direct observation, or cited product evidence. Before finalizing, perform a
field-to-source check for every buyer-facing claim:

| Buyer-facing field | Required source check |
| --- | --- |
| Product identity and variant | Seller confirmation, readable label, or cited evidence tied to the item. |
| Condition, wear, defects, and tests | Seller confirmation or direct observation. A source can never prove this unit's condition. |
| Features and compatibility | Cited evidence for the confirmed model, plus seller or observation evidence when the claim concerns this unit, an included accessory, or a working setup. |
| Included items | Seller confirmation or direct observation. |
| Price and warranty | Seller-approved price; seller confirmation or cited terms for any warranty claim. |
| Fulfillment, meetup, location, payment | Not description content. These live in the platform's delivery and location settings, the listing record's `seller.*` fields, project configuration, and buyer conversation. See "Transaction terms" below. |

If a claim cannot trace to one of those sources, remove it, qualify it as an
unknown for the seller, or ask the one consequential question that would
support it. Do not use buyer copy to convert an inference into a fact.

If the seller directs a buyer-facing claim after hearing that the evidence does
not fully support it, state the concern once, then use the seller's wording and
record the claim in the listing record as seller-directed together with the
concern raised. Do not repeat the objection in later turns.

## Title recipe

Put the exact product identity first. Add a meaningful confirmed variant or
condition next. Add one credible differentiator only when space and evidence
support it, such as a confirmed included accessory or stated test result.

A title must be searchable, immediately understandable, and concise. Do not
use decorative symbols, clickbait, all-caps emphasis, keyword stuffing, or
unsupported condition and feature claims.

## Description recipe

Write in this order, omitting anything not supported by the field-to-source
check:

1. Identify the item and state its condition.
2. Give verified highlights that matter to a buyer.
3. List included items.
4. State testing and material defects or limitations.
5. State the approved price.
6. End with a plain close.

The description is complete when it contains those six parts and nothing else.
Use short, ordinary sentences. Name a limitation plainly instead of hiding it
behind promotional language or technical detail that does not help a buyer
decide.

## Transaction terms

Pickup, delivery, meetup, the seller's town, and payment methods are handled
by the platform's delivery-method and location settings, the listing record's
`seller.fulfillment` and `seller.payment` fields, project configuration, and
the conversation with each buyer. Record them there. When a seller explicitly
asks for a transaction term in the description, add it as a final sentence
after the price and note the request in the record.

Payment: the description mentions no payment method. Read the project's
payment policy for use in buyer replies and handoff, never as a copy source.

## Humanizing buyer copy

**REQUIRED SUB-SKILL:** Use humanizer in embedded mode for buyer-facing title and description drafts when available.

In embedded mode, make an internal draft, audit it for artificial or
promotional phrasing and fabrication, then revise it into natural language.
Humanization cannot alter facts, add claims, change prices, or edit YAML and
research notes. It can only improve the phrasing of the buyer-facing title and
description.

If humanizer is unavailable, do the same internal sequence without requiring
the named skill: draft from the traceable fields, audit every claim against its
source, remove fabricated or inflated language, read for natural plain
language, then recheck that facts and prices are unchanged. Keep this fallback
portable and do not treat the unavailable sub-skill as a reason to block a
truthful draft.

## Complete example

The facts in this worked example are illustrative only. Never treat them as the
current listing record or copy them into buyer-facing fields unless current-item
evidence independently supports each fact.

### Factual input set

- Seller-confirmed identity: Jabra Elite 8 Active Gen 2 earbuds, navy.
- Seller-confirmed condition: both earbuds and the charging case work.
- Seller-confirmed test: pairing and playback were tested.
- Observed included items: earbuds, charging case, and USB-C cable.
- Observed defect: light scuffs on the charging case, visible in photos.
- Seller-confirmed fulfillment: pickup only (recorded in `seller.fulfillment`;
  set in the platform's delivery settings).
- Seller-approved price: $80.

### Drafted buyer copy

Title: `Jabra Elite 8 Active Gen 2 Earbuds, Navy, Tested`

Description:

> Jabra Elite 8 Active Gen 2 earbuds in navy. Tested for pairing and playback;
> both earbuds and the charging case work. Includes the earbuds, charging case,
> and USB-C cable. The charging case has light scuffs, shown in the photos.
> Price is $80. Please message with questions.

The identity, test result, condition, included items, and price each trace
directly to the factual input set. The pickup term is carried by the delivery
settings and the record, not the description. The description does not add
model features, battery claims, cleanliness claims, payment methods, or
accessories beyond the recorded evidence.
