# New model prices, read 2026-09-22

The prices for the Lanes that ticket 33's first wizard run adds. Each figure is USD per
1M tokens, read from the vendor page named in its section on 2026-09-22. The catalog
`price` keys are `in`, `cache_read`, `cache_write` and `out`. A key the page does not
list stays `null`.

## OpenAI: developers.openai.com/api/docs/pricing, standard tier, short-context rows

| Model | in | cache_read | cache_write | out |
|---|---|---|---|---|
| gpt-6-sol | 2.00 | 0.20 | 2.50 | 10.00 |
| gpt-6-luna | 0.10 | 0.01 | 0.125 | 0.50 |
| gpt-6-astra (unchanged, for comparison) | 10.00 | 1.00 | 12.50 | 50.00 |
| gpt-5.6-sol (superseded) | 4.00 | 0.40 | 5.00 | 20.00 |
| gpt-5.6-luna (superseded) | 0.20 | 0.02 | 0.25 | 1.20 |

## Anthropic: platform.claude.com/docs/en/about-claude/pricing, model pricing table

`cache_write` is the 5-minute cache write price.

| Model | in | cache_read | cache_write | out |
|---|---|---|---|---|
| claude-opus-5-5 | 4 | 0.20 | 5 | 20 |
| claude-opus-5 (superseded) | 5 | 0.50 | 6.25 | 25 |

Cache hits on Opus 5.5 cost 0.05x the input price, where most models cost 0.1x
(footnote 2 on that page).

## xAI: docs.x.ai/docs/models, rows for prompts under 200k tokens

| Model | in | cache_read | cache_write | out |
|---|---|---|---|---|
| grok-4.7 | 2.00 | 0.50 | null | 6.00 |
| grok-4.7-build-fast | not listed | | | |
| grok-4.6 (superseded) | 2.00 | 0.50 | null | 6.00 |

The page lists no cache-write price. `grok-4.7-build-fast` stays `UNPRICED`.

## Google: ai.google.dev/gemini-api/docs/pricing, paid tier, prompts of 200k tokens or fewer

| Model | in | cache_read | cache_write | out |
|---|---|---|---|---|
| gemini-3.1-pro (listed as Preview) | 2.00 | 0.20 | null | 12.00 |

The page prices context caching per token read and storage per hour. It gives no
cache-write price, the same as the existing `flash-*@agy` Lanes.

The page also lists Gemini 3.8 Flash at $0.75 in, $0.075 cached and $3.75 out through
2026-12-31, rising to $1.50, $0.15 and $7.50 on 2027-01-01. The `flash-*@agy` catalog
prices should be checked against that date.
