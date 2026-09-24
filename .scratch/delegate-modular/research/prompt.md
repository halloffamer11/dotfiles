<agent><you are the orchestrator working on the dotfiles repo. manage the git state, worktrees, /herdr panes, and /delegate decisions. do not write code yourself. only review work at the git-merge level.</agent>

<task1>review the implementation of the delegate skill. evaluate adherence to deep modules concept:
### Architecture
Prefer deep modules: concentrate substantial behavior and complexity behind small, coherent interfaces at real seams. Callers and tests should depend on those interfaces; introduce abstractions only when they hide meaningful complexity or support actual variation, not as pass-through or speculative layers. /delegate-codex to astra on xhigh reasoning. and also /delegate-grok.
</task1>
<task2>building on the architecture learnings analyze the current architecture of the project relative to the following user-story and provide a refactoring consultation to adopt this kind of structure. do not compromise SWE best practices or your judgement:
  ## User story
The way I want this skill to work is somewhat modular. The intent is when I call the delegate skill, we're going to route work to different harnesses depending on the type of work, the usage available, and the model routing logic. Where I want to get to long term, and we're not there yet by intent because we haven't built all these features.

But let me describe the workflow. The delegate skill needs a setup phase. The setup phase will determine some level of classification or lanes where we currently have an implementation example of I think scouts and hard implements, implements, and just this is just examples of coding leans. This might expand to maybe knowledge work lanes as well.

And then we have a model routing setup phase where we use the benchmarks to establish what models are preferred for what type of work in what order, and then we have the usage capability, which should be able to be turned on and off, but also provides kind of a default configuration where it's on and has a gate and a metering. We have those two parameters.

I forget exactly what they are, but they help maintain usage across all the harnesses without breaking the selection of models within a tier and then we have to make a decision if you run out of usage in a tier the delegate skill should warn the user and basically ask for some instruction direction.

So by default it's just going to route things to a correct lane and burn down usage until it's to zero or whatever the criteria is the herder plugin is a additional feature we've built that allows for customization of the lanes and preferred models, but also visibility to where work is going.

So I think that's a core concept here. What I really want to get to is an abstraction where we can design the interfaces simply, specifically how does the model pick a lane or a classification, right? So how does the model understand if it's a regular implement or a hard implement?

And I want that abstraction to be in a markdown file or some sort of instruction that the agent loads for kind of that model routing. I think we have the tiers, right? The tiers are deterministic, but I think there's an unavoidable judgment call on the orchestrating agent for, okay, what kind of work needs to be done, right?

overall customer-facing workflow:
- clone skill to repo and set it up ideally with npx skills tool
- setup skill:
  - skill command like "/delegate-setup"
  - script or automation for detecting harnesses or installed agents wrapped with an agent to try{} and catch issues
  - configures the number of tiers
  - configures the classification types, definitions, and tier-mappings
  - tui/html interactive interface based on benchmarks to assist in tier-mappings
- /delegate skill
  - loads classification logic
  - provides scripts/tools for routing to tiers/models/harnesses
  - orchestrator runs delegated tasks in appropriate container and git-hygiene (worktrees, branches, etc...)
- management and project-specific use
  - allows for herdr integration for realtime observation, data, plots, and manual, hot-loaded configuration of order
  - maintains project-specific rules for delegate

  this is just a rough idea and it is missing some of the details, but is directionally correct.
</task2>

<task3>model benchmarks:
1/ AA intelligence index: https://artificialanalysis.ai/
2/ terminal bench (currently 4.0) https://artificialanalysis.ai/evaluations/terminalbench-v4-0
3/ APEX agents: https://www.mercor.com/apex/apex-agents-leaderboard/
4/ deep swe: https://deepswe.datacurve.ai/
5/ AA-Omniscience: https://artificialanalysis.ai/evaluations/omniscience
6/ AutomationBench-AA: https://artificialanalysis.ai/evaluations/automationbench-aa

</task3>

<task4>Based on the benchmarks and the different strengths and weaknesses of the different models, I think we're going to adapt a different classification and tier mechanism that allows for mapping of different tiers to different target use cases. I think broadly there are 2 or 3.

1. Coding agents, which is what the current classification is oriented towards.
2. Knowledge work, which is not coding specifically, but expert knowledge in different domains across finance to investing to supply chain, for example, or engineering.
3. Computer use and automation. That's kind of where I want to head to.

From the standpoint of modularity and seams and the workflow, I haven't articulated it well yet, but this task should be scoping out some of this idea and specifically how we can introduce a judgment-based tool where during setup or during some of this work, I wanted to kind of operate like a wizard where the data and information is curated, but the decision-making for setup of this delegate skill is done by the human in the loop, and the setup skill can actually be run at any time, and it makes it very easy to incrementally and surgically update things.

For example, maybe new model releases, I run delegate setup and just say, I want to use Astra6 more. Let's look at the benchmarks and update the default setup of this whole thing. Or I'm not doing any knowledge work, just coding, so we can reduce that classification.

Like these kind of things should just be executable with a setup skill to make it super easy. Right now it requires the TUI and some other things, so I think we can probably get away from the TUI for configuration and use the HTML as a reference. But I think the Herder integration is good. </task4>
