# Orchestrator-to-worker model routing, read 2026-09-27

Research for the question: inside usage limits, is delegate always picking the best
lane? And how good is an orchestrating agent at judging task difficulty for routing?

## Summary

- Two proven routing families exist: trained pre-generation routers (a classifier
  picks the model before any generation) and cascades (try cheap, escalate on a
  quality check). Both beat "always use the strong model" by 40-98% cost cuts at
  matched quality. [RouteLLM](https://arxiv.org/abs/2406.18665),
  [FrugalGPT](https://arxiv.org/abs/2305.05176).
- Anthropic's own multi-agent orchestrator does not use a learned difficulty model.
  It uses fixed prompt rules ("scale effort to query complexity": 1 agent for a
  simple lookup, 10+ for broad research). This is delegate's closest architectural
  cousin. [Anthropic, multi-agent research
  system](https://www.anthropic.com/engineering/multi-agent-research-system).
- Evidence that a general LLM can judge task difficulty well is weak. The best
  purpose-built difficulty predictor gets Spearman ρ=0.399 in-domain and drops to
  ρ=0.225 out-of-domain, across 17 agentic benchmarks including coding. [Predicting
  Task Difficulty Without Rollouts](https://arxiv.org/html/2608.05797). Studies that
  compare an LLM prompted as a router against a small trained classifier find the
  trained classifier wins. [Doing More with Less
  survey](https://arxiv.org/html/2502.00409v1).
- Self-confidence (a model rating its own chance of success) is calibrated on
  multiple-choice QA but that evidence does not transfer to agentic coding.
  [Kadavath et al. 2022](https://arxiv.org/abs/2207.05221).
- Budget-aware routing is usually framed as a contextual bandit spending a budget
  over time, not a one-shot best-pick. [Adaptive LLM Routing under Budget
  Constraints](https://arxiv.org/abs/2508.21141). This is structurally close to
  delegate's pace/margin mechanic.
- "JEV" is very likely **Jev**, a "System One" decision model from TypeSafe AI,
  announced 2026-09-15, marketed partly for model routing. [TypeSafe via
  Zapier](https://zapier.com/blog/jev/). An independent pilot that used Jev to route
  Claude Code tasks reports it *lost* to a simple baseline in a 6-task test.
  [suncirkles/jev-router](https://github.com/suncirkles/jev-router).
- One coding-specific vendor router exists today: Not Diamond markets a router
  "built to optimize coding agent cost." [Not Diamond
  docs](https://docs.notdiamond.ai/docs/what-is-not-diamond).
- OpenAI's GPT-5 router is retrained continuously on real usage outcomes (model
  switches, preference rates, measured correctness), not fixed at launch.
  [OpenAI, Introducing GPT-5](https://openai.com/index/introducing-gpt-5/).
- Net read for delegate: don't trust a holistic orchestrator "how hard is this"
  guess. Trust cheap, checkable proxies (tests present, spec has open questions) and
  a try-then-verify-then-escalate loop over a predict-then-route one.

## 1. Taxonomy of routing approaches

### Pre-generation routers (trained)

A trained model predicts, before generation, which worker model to use.

- **RouteLLM** [(arXiv:2406.18665)](https://arxiv.org/abs/2406.18665) trains four
  router types (similarity-weighted ranking, matrix factorization, a BERT
  classifier, a Llama-3-8B classifier) on human preference data (Chatbot Arena) to
  route between one strong and one weak model. The best router (matrix
  factorization) needs only 13.4% of calls to go to the strong model to recover 50%
  of the quality gap on MT-Bench, versus 49% for random routing. At 95% of GPT-4's
  quality it gets a 3.66x cost reduction. The router keeps working when the strong
  and weak models are swapped at test time, without retraining. RouteLLM measures a
  router by Performance Gap Recovered (PGR) swept across a cost threshold, and
  separately defines a "willingness to pay" (λ) dial for how much quality a caller
  will buy with cost.
- **Hybrid LLM** [(arXiv:2404.14618)](https://arxiv.org/abs/2404.14618), Microsoft:
  trains a router to predict the quality gap between a small and large model per
  query. Cuts large-model calls by up to 40% with no drop in response quality.
- **RouterBench** [(arXiv:2403.12031)](https://arxiv.org/abs/2403.12031): a
  benchmark, not a router — 405k precomputed outputs from 11 models across 7 tasks
  (MMLU, MT-Bench, MBPP, HellaSwag, Winogrande, GSM8K, ARC), built to score any
  router's cost/quality curve on a common footing. Finds that comparable quality can
  cost 2-5x more or less depending only on model choice.
- **Arch-Router** [(arXiv:2506.16655)](https://arxiv.org/abs/2506.16655), a 1.5B
  open model from Katanemo: routes on a "domain-action" label (e.g. `finance` +
  `summarization`) that a human defines, instead of a predicted quality score. Its
  argument: quality is often subjective (tone, style), so optimizing a predicted
  score is the wrong objective — a human-legible policy is more transparent and
  supports adding new models without retraining. Reports 93.17% routing accuracy,
  beating proprietary LLM routers by 7.71 points on average, at 28x the speed of the
  closest commercial competitor.
- A broader map, from the survey **"Dynamic Model Routing and Cascading for
  Efficient LLM Inference"** [(arXiv:2603.04445)](https://arxiv.org/html/2603.04445v2),
  names six paradigms: difficulty-aware (RouteLLM-style), preference-aligned
  (Arch-Router), clustering-based (group similar queries, route the cluster),
  RL/bandit-based (treat routing as a sequential decision), uncertainty-based
  (probe or self-verify confidence, escalate if low), and cascading (below).

### Cascades with escalation

Try the cheap model first; a checker decides whether to accept or pass the query up.

- **FrugalGPT** [(arXiv:2305.05176)](https://arxiv.org/abs/2305.05176): orders
  models cheapest-first; a learned scorer decides accept-or-escalate. Matches GPT-4
  accuracy at up to 98% lower cost, or beats GPT-4 accuracy by 4% at the same cost.
- **AutoMix** [(arXiv:2310.12963)](https://arxiv.org/abs/2310.12963): the small
  model generates, then does a noisy few-shot self-verification, then a POMDP-based
  router uses that confidence signal to decide whether to escalate. Cuts cost over
  50% for comparable quality, across 5 models and 5 datasets.

### Orchestrator-worker patterns (rule-based effort scaling)

No learned difficulty model — fixed rules in the orchestrator's own prompt.

- **Anthropic, "Building Effective Agents"**
  [(anthropic.com)](https://www.anthropic.com/engineering/building-effective-agents):
  defines "routing" as a workflow that classifies an input and sends it down a
  specialized path. Its own worked example is exactly delegate's problem: "Routing
  easy/common questions to smaller, cost-efficient models like Claude Haiku ... and
  hard/unusual questions to more capable models like Claude Sonnet."
- **Anthropic, "How we built our multi-agent research system"**
  [(anthropic.com)](https://www.anthropic.com/engineering/multi-agent-research-system):
  a lead agent (orchestrator) delegates to parallel subagents (workers). One of
  their stated prompt principles is "scale effort to query complexity" — written as
  explicit rules in the orchestrator's prompt, not a learned classifier: a simple
  fact-finding query gets 1 agent with 3-10 tool calls; a direct comparison gets 2-4
  subagents at 10-15 calls each; broad research gets 10+ agents. They report token
  usage alone explained 80% of the performance variance in one internal eval
  (BrowseComp). This is a rule-based analogue of delegate's Class-to-Tier mapping,
  hand-tuned rather than learned.

### Vendor routers

- **OpenAI's GPT-5 real-time router**
  [(openai.com, Introducing GPT-5)](https://openai.com/index/introducing-gpt-5/):
  picks between `gpt-5-main` and `gpt-5-thinking` (falling back to mini variants
  under load) using conversation type, complexity, tool needs, and explicit intent
  (e.g. "think hard about this" in the prompt). It is "continuously trained on real
  signals, including when users switch models, preference rates for responses, and
  measured correctness." I could not extract the GPT-5 system card PDF directly
  (binary/compressed, would not parse); the quotes above come from OpenAI's own
  launch page describing the same router, not from the raw system-card text, so
  treat the training-methodology detail as OpenAI's public description rather than
  something I verified against the primary PDF.
- **OpenRouter Auto Router**
  [(openrouter.ai docs)](https://openrouter.ai/docs/guides/routing/routers/auto-router):
  `openrouter/auto` picks a model per prompt using aggregate community usage,
  measured over a trailing 7-day window per task type — a market-revealed
  preference, not a difficulty classifier. A `cost_tier` field (low/medium/high/
  xhigh/max) sets a discrete willingness-to-pay; default is `low`.
- **Not Diamond** [(docs.notdiamond.ai)](https://docs.notdiamond.ai/docs/what-is-not-diamond):
  a commercial router, offered pre-trained or custom-trainable on your own data. It
  now markets a router variant specifically "built to optimize coding agent cost,"
  separate from its chat router — the clearest existing vendor precedent for a
  coding-agent-specific router.
- **Claude Code subagent `model` field**
  [(code.claude.com/docs/en/sub-agents)](https://code.claude.com/docs/en/sub-agents):
  each subagent config sets `model` to an alias, a full model ID, or `inherit`,
  resolved in a fixed order (call-time param, then frontmatter, then the
  `CLAUDE_CODE_SUBAGENT_MODEL` env var, then the parent session's model). This is
  static per agent definition — closest existing analogue to a delegate Lane, but it
  carries no runtime difficulty judgment at dispatch time.

## 2. Can an orchestrator judge task difficulty?

- **Kadavath et al., "Language Models (Mostly) Know What They Know"**
  [(arXiv:2207.05221)](https://arxiv.org/abs/2207.05221): larger models are
  reasonably well-calibrated on multiple-choice and true/false questions in the
  right format, and can self-evaluate "P(True)" on open-ended answers with
  encouraging (not perfect) calibration, improving when the model sees several of
  its own samples first. This is the best-known positive result, but the domain is
  chat QA, not agentic coding — it says models can sometimes judge "is this answer
  right," not "how hard will this coding task be."
- Verbalized-confidence surveys report a split field: models can "partially
  self-assess," producing higher confidence on correct answers, but imperfectly.
  See the TMLR 2025 survey
  [SihengLi99/LLM-Honesty-Survey](https://github.com/SihengLi99/LLM-Honesty-Survey)
  and **"Large Language Models Must Be Taught to Know What They Don't Know"**
  (NeurIPS 2024) [(paper)](https://proceedings.neurips.cc/paper_files/paper/2024/file/9c20f16b05f5e5e70fa07e2a4364b80e-Paper-Conference.pdf)
  — whose own title states that base models do not know this reliably without
  extra calibration training.
- **"Beyond Confidence: Rethinking Self-Assessments for Performance Prediction in
  LLMs"** [(arXiv:2605.07806)](https://arxiv.org/abs/2605.07806) argues raw
  verbalized confidence is not enough for reliable performance prediction. I could
  not extract clean numbers from this PDF (extraction failed on the binary content),
  so treat this citation as directional support, not a sourced statistic.
- **"Predicting Task Difficulty Without Rollouts"**
  [(arXiv:2608.05797)](https://arxiv.org/html/2608.05797) is the most relevant and
  best-extracted paper. It defines ground-truth difficulty via Item Response Theory
  fitted to real agent success/failure across 5,230 tasks over 17 agentic
  benchmarks (coding/SWE-bench, math, web navigation, function calling, ML
  engineering, cybersecurity, terminal use, reasoning). Its best predictor
  (embeddings plus token-level-entropy trajectory features) reaches Spearman
  ρ=0.399 in-distribution, but drops to ρ=0.225 out-of-distribution
  (leave-one-benchmark-out). Entropy alone gets ρ=0.193. The authors flag that AUC
  is a misleading metric here: a constant "always medium difficulty" predictor
  already scores 0.715 AUC with zero real ranking skill. Their conclusion:
  pre-execution difficulty prediction works somewhat within a familiar task
  distribution, and is weak across new kinds of tasks.
- **"Doing More with Less" survey**
  [(arXiv:2502.00409)](https://arxiv.org/html/2502.00409v1) reports that a small
  fine-tuned classifier (RoBERTa, 120M params) beat prompting GPT-4 to act as the
  router; a separate cited study found zero-shot/few-shot LLM-as-router prompting
  underperforms a purpose-trained router. The pattern across the literature I found
  is consistent: a cheap, purpose-trained classifier beats a general LLM merely
  asked to judge a query.
- **"LLMs Can Predict Failure Risk, But Struggle to Predict Which Collaboration
  Protocol Pays Off"** [(arXiv:2608.14927)](https://arxiv.org/abs/2608.14927): its
  own title is the nuance worth keeping — an LLM may be decent at "will I likely
  fail this," but that is a different (and easier) skill than "which strategy/model
  should handle this instead."

## 3. Trading quality against cost or a budget

- RouteLLM's α-swept **Performance Gap Recovered** and **willingness-to-pay (λ)**
  dial [(arXiv:2406.18665, ICLR 2025 version)](https://arxiv.org/abs/2406.18665)
  treat cost as a continuous knob, reporting an *average* PGR across a range of cost
  thresholds rather than one fixed operating point.
- **"Adaptive LLM Routing under Budget Constraints"**
  [(arXiv:2508.21141)](https://arxiv.org/abs/2508.21141) frames routing as a
  contextual bandit paired with an online multi-choice knapsack, so the system
  spends a budget over a stream of queries instead of scoring every model on every
  query. **WISERouter** [(arXiv:2607.23765)](https://arxiv.org/abs/2607.23765) does
  the same with a constrained contextual bandit plus a small linear program that
  turns remaining budget into a per-query spending limit as the period runs out.
  Both are structurally close to delegate's pace/margin mechanic (spend rate versus
  time-remaining, adjusted online).
- OpenRouter's `cost_tier` is a simpler, discrete version of the same idea: a
  named willingness-to-pay level rather than a continuous optimizer
  [(OpenRouter docs)](https://openrouter.ai/docs/guides/routing/routers/auto-router).
- I did not find a paper that names "treat near-equivalent lanes as a band and
  load-balance inside it" as a labeled technique (no hit for "satisficing" or
  "epsilon-band" in this exact framing). The closest formal cousin is
  epsilon-first exploration in budget-limited bandits, cited inside WISERouter as
  a known baseline strategy — explore a small slice of the budget across options
  before committing to the best-known one. That is an analogy, not a direct match;
  flag it as inference.

## 4. Escalation in agentic coding: the evidence

- FrugalGPT and AutoMix's strong cost numbers (section 1) come from chat/QA
  benchmarks (MT-Bench, MMLU, HotpotQA-style tasks), not from agentic coding.
- **"AI Agents That Matter"** [(arXiv:2407.01502)](https://arxiv.org/abs/2407.01502),
  Kapoor et al.: argues agent benchmarks that report accuracy alone produce
  needlessly expensive, overfit agents, because developer and researcher needs get
  conflated and holdout sets are often missing. They implement one cost-aware
  optimization and show it can cut cost while holding accuracy, but I could not
  extract the exact numbers (the PDF would not parse as text) — I can only confirm
  the claim at the abstract level. Its actionable point for delegate: always report
  cost and accuracy together, and evaluate any routing change on a held-out task
  set to avoid the classifier learning shortcuts.
- I could not find a peer-reviewed, primary-sourced paper measuring "try a cheap
  model on a real coding task, run tests, escalate on failure" with reported
  cost/quality numbers. A commonly repeated blog claim (cheap-model cascade,
  Llama-3-8B → GPT-3.5 → Llama-3-70B → GPT-4, gated on test failure) could not be
  traced back to a citable primary source — treat it as unverified.
- The most directly relevant evidence is negative and comes from the independent
  **JevRoute** pilot (section 5): a difficulty-classifier-style router for Claude
  Code coding tasks lost to a simple baseline in a small trial (1 of 6 hidden test
  suites passed by the Jev-based policy, versus 2 of 6 for the baseline control).
  This is one small, non-peer-reviewed pilot, but it is the only coding-agent
  routing result I found with a reported win/loss against a naive baseline, and it
  points against "let a fast classifier decide difficulty before trying."

## 5. What "JEV" most likely is

High confidence: Orin means **Jev**, a "System One Model" from TypeSafe AI,
announced 2026-09-15 alongside a $40M round led by DCVC; the company's founder,
Diogo Almeida, co-invented RLHF/InstructGPT at OpenAI.
[TypeSafe, via Zapier](https://zapier.com/blog/jev/),
[TechCrunch](https://techcrunch.com/2026/09/18/a-new-kind-of-ai-model-from-a-chatgpt-inventor-is-thrilling-developers/).

- Jev is a **decision-only** model: it takes a block of state plus a set of typed
  questions and returns typed answers (a classification, a score, a probability)
  instead of free text, and runs 40-200x faster than a frontier LLM.
- TypeSafe explicitly lists model routing as a use case: "predicting whether a
  given workload requires a specific model would be useful, but using an LLM for
  the job would be expensive" — Jev's low cost and speed are pitched for exactly
  that kind of real-time sorting [(same source)](https://zapier.com/blog/jev/).
- TypeSafe also ships its own product for this, **Jev Router**
  [(openrouter.ai/typesafe/jev-router)](https://openrouter.ai/typesafe/jev-router),
  released 2026-09-25 per one secondary source, which "picks the best model and
  reasoning effort for each request, balancing quality, speed, and cost."
- Separately, an **independent, non-TypeSafe** open-source pilot,
  [suncirkles/jev-router ("JevRoute")](https://github.com/suncirkles/jev-router),
  tried using Jev to route real Claude Code coding tasks. Its own README is
  explicit that this is unproven: a 6-task coding-agent pilot had the Jev-based
  policy pass 1 of 6 hidden test suites against 2 of 6 for a baseline control, and
  the authors state plainly "the evidence below does not yet establish that Jev
  routing beats simple controls."
- Confidence in the ID: high. "Jev" is a very close phonetic match to "JEV," it is
  a genuinely new (September 2026) model, and TypeSafe's own marketing language
  ("could help with model routing") nearly echoes Orin's phrasing. I could not
  find any other 2025-2026 model or system with a closer name match used for
  routing, so I am not hedging further on the identification itself — only on
  whether Jev-based routing actually works well for coding tasks, where the one
  data point I found is a loss against a naive baseline.

## 6. Implications for delegate (inference — not sourced claims)

Everything in this section is my own reasoning from the evidence above, not a
direct claim from any source. Each point below names what it leans on.

- **(a) Deterministic pick vs. an eligible band.** The bandit-routing and
  cost-threshold literature (section 3) treats "which model" as a knob swept
  across a cost/quality curve, not a single hard-sorted answer — that supports
  Orin's instinct that a Tier's eligible lanes are a band, not one correct pick.
  But section 2's evidence is that a general orchestrator is a *weak* difficulty
  judge, especially out-of-domain, and a purpose-trained classifier beats an LLM
  asked to route. So: returning a band and letting the orchestrator freely pick
  by "vibes" is not well supported. A narrower version is: keep `rank.py`'s
  deterministic pick as the default, and only let the orchestrator override
  inside the band when it can point to a concrete, checkable reason (see b) —
  closer to Arch-Router's "human-legible policy" idea than to a learned score.
- **(b) Which signals an orchestrator can judge.** From "Predicting Task
  Difficulty Without Rollouts": the features that carried *any* real (if weak)
  signal were structural/textual — not a holistic self-rating. Practical reading
  for delegate: trust binary, checkable facts the orchestrator can already see
  before dispatch — tests exist for the touched area or not, the spec/ticket has
  open questions or not, the diff is scoped to N files it can already name. Do
  not trust a free-text "how hard is this, 1-10" self-rating; section 2's
  calibration evidence for that kind of judgment comes from multiple-choice QA,
  not agentic coding, and the one coding-specific pilot (JevRoute) found a
  difficulty-classifier-style router losing to a naive baseline.
- **(c) Escalate on failure, don't predict-then-route.** Cascades (FrugalGPT,
  AutoMix) are the best-evidenced cost-saving pattern generally, but that
  evidence is from chat/QA. The one coding-agent data point (JevRoute) is a loss
  for a pre-classify approach, not for escalation itself — it never tested
  try-then-escalate, only predict-then-route. Given delegate already has a
  concrete failure signal available (tests, review), a "run at the Tier's normal
  pick, escalate one Tier only on a verified failure" rule is closer to what the
  evidence actually supports than pre-judging difficulty before the first
  attempt.
- **(d) Log outcomes before building any learned or LLM-judged difficulty
  signal.** Both cited vendor routers that adapt over time (OpenAI's GPT-5
  router, and implicitly Arch-Router's preference labels) are described as
  learning from real usage outcomes, not fixed at launch. Delegate does not need
  to build a classifier now; it needs a record — Class picked, lane picked, Tier,
  and the eventual pass/fail/review outcome — so that if an orchestrator-choice
  experiment runs later, there is already a baseline to check it against, and so
  any future "let the orchestrator pick inside the band" change can be measured
  against the deterministic baseline rather than argued from intuition.
