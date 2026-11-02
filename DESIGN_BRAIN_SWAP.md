# The RSI Brain-Swap Test

*Proposal, 2026-10-29. Author: Thomas Liberman, built with Claude.*

> **Status.** This is the design as I originally proposed it, and the simulation
> results in section 9 come from mock models only. I've since run the experiment with
> real models (three scouts, two pilots, and a follow-up). The results are in
> `runs_brainswap/`, and the README has a summary. The real runs changed a few things
> from this plan: procedure edits became mandatory, the normalization test was dropped
> from the second pilot, and I overrode the final scout's NO-GO. The run configs and
> `scout_decision.json` files show each of these. Not finding prior work in a search
> doesn't mean nobody has done this.

## 1. Question

An agent improves itself by rewriting both its task solver and its own
improvement procedure. Over the generations, does its ability to keep producing
improvements become **specialized to the language model underneath it**? If it
does, is part of that specialization explained by **how the agent's own source
code is presented** to the model?

### Hypotheses

- **H1 (specialization).** Take a procedure evolved on model A. Model A gets more
  improvement out of it than model B does. Take a procedure evolved on B, and B
  gets more out of it than A does. This home-versus-away interaction grows
  relative to generation 0.
- **H2 (presentation).** Mechanically normalizing the source the model sees
  shrinks that growth, and shrinks it *selectively*: the interaction gets
  smaller. Everyone doing uniformly better or worse does not count.
  A length-matched renaming control separates the effect of style from the
  effect of token length.
- **Null outcomes are findings.** Gains that carry over intact to the other model
  mean the procedures are reusable. No improvement over the frozen-improver
  baseline means recursive self-improvement was not demonstrated at all.

## 2. Prior art: what overlaps and what does not

We read four of the five assigned sources and their repositories, plus DGM. The
MDPI paper (Appl. Sci. 16(15):7733) could **not** be read, because the URL was
blocked and searches did not find it. It is unassessed and could overlap.

| Source | Overlap | Not reported there |
|---|---|---|
| **Huxley-Gödel Machine** (Wang et al., ICLR 2026; repo metauto-ai/HGM) | The agent edits its own code, and edited code performs later edits. Clade-metaproductivity (CMP) scores an agent by its descendants. One-way transfer: the best GPT-5-mini agent re-run on GPT-5 (Table 4). | No starting-agent-plus-GPT-5 control. No crossed design. The improvement procedure is not transferred on its own. No specialization measure. No frozen or one-step baseline. No seeds. |
| **Hyperagents / DGM-H** (Zhang et al., Mar 2026; repo facebookresearch/Hyperagents) | Task and meta agent in one editable program; accepted meta edits run later generations. **imp@k** measures a fixed meta agent's gain over a starting task agent, transferred across domains. Frozen-meta-agent baseline. 5 runs with CIs. | No transfer across underlying models. No crossed matrix. The reset keeps non-task files, including the agent's own memory files. No presentation intervention. No one-step baseline. |
| **Harness Updating ≠ Benefit** (Lin et al., May 2026, 2605.30621) | Seven frozen models as evolver and solver. A **3×3 fully crossed evolver × solver core** (Tabs 5, 7). | The evolver prompt is fixed, so the procedure never self-modifies. The harness is built online. No home/away analysis; our arithmetic on their core gives about ±1 pp, at noise scale. No update gate. No held-out set. |
| **Harness Handbook** (Wang et al., Jul 2026, 2607.13285) | A behavior-indexed view of code beats raw navigation (win rate 45.6 vs. 26.7). | Not self-improvement: humans write the change requests. The representation and navigation policies change together, so their effects can't be separated. |
| **Darwin Gödel Machine** (Zhang et al., 2025), not on the assigned list | One-way transfer of evolved agents across models, *with* starting-agent controls. Gains shrink away from the evolving model on Polyglot. Frozen meta-agent baseline. | The whole agent is transferred, not the procedure with the solver reset. One-directional. Headroom is confounded with transfer. |

**What these sources do not report:**
- moving an evolved *improvement procedure* to another model with the original
  solver restored and memory cleared;
- a full origin × operator crossed design, with a gen-0 interaction baseline;
- whether specialization grows over generations;
- a source-normalization intervention inside a self-improvement loop;
- a one-generation baseline.

**What we took from them:**
- The forked audit is imp@k with an operator swap, and we use that framing.
- Memory is defined mechanically, which avoids Hyperagents' reset leak.
- The interaction is a difference-in-differences against gen 0, which handles
  the headroom confound seen in DGM and 2605.30621. A logit-scale version is
  reported as well.
- The size of effect to plan for is small. In 2605.30621, swapping the evolver
  moved scores by at most about 3 pp.

## 3. Design at a glance

```
            evolution (per model, L independent lineages, G generations)
  seed agent ──► gen 1 ──► gen 2 ──► ... ──► gen G         solver.py + improver.py both editable
                                     │
                    checkpoint procedure (improver.py only)
                                     ▼
         forked audit: seed solver + checkpoint procedure, memory cleared,
         fresh dev tasks, K continuation generations, scored on the sealed set
                ┌───────────────┬───────────────┐
                │ run by A      │ run by B      │
   evolved by A │ home          │ away          │
   evolved by B │ away          │ home          │   × presentation: orig / norm / neutral
                └───────────────┴───────────────┘
```

**Roles.** Within a lineage, and within an audit cell, *one* model is the brain:
it serves both the improvement procedure's calls and the solver's calls. HGM and
Hyperagents split these roles across models. Splitting them here (procedure
operator × solver model, a 2×2×2 design) is a possible extension, but it is not
in the pilot.

## 4. The agent, and what stays outside it

**The agent is exactly two files.** `solver.py` defines `solve(task, api)`.
`improver.py` defines `improve(ctx, api)`. Both start from `brainswap/seed/`.
The procedure returns full replacement files. An accepted `improver.py`
**governs every later generation**: the next generation executes the new file.

**Interface.**
- The solver gets `api.llm`, `api.check` (shown examples only) and `api.budget`.
- The procedure gets `api.llm`, `api.source(name)`, `api.trial(solver_source, n)`
  and `api.budget`.
- Agents cannot open files, use the network, or start processes. This is
  enforced twice: by a static policy check, and by a bubblewrap sandbox with no
  network that cannot see the repository.
- **`api.source` is the only way an agent sees its own code.** This is what makes
  the presentation intervention precise.

**Outside the agent, and not editable by it:**
- the evaluator and grader;
- every budget (calls, tokens, checks, trial tasks, wall time);
- the task partitions;
- the acceptance rule;
- the spend log and caps;
- the memory store. Memory is one line per generation, written by the harness
  from the procedure's note. Audits start with it empty.

**Acceptance.**
- A candidate's solver must solve more development tasks than the current bar,
  and must still beat the bar on the mean of a second evaluation.
- Procedure edits are accepted only together with an accepted solver gain, never
  alone. This is DGM-style hitchhiking.
- *Limitation:* procedure edits are therefore selected indirectly. HGM's CMP,
  which scores a procedure by what its descendants achieve, is the principled
  alternative. It costs more than a pilot can afford.

## 5. Task domain

Tasks are list-function induction, a form of programming by example:
- A hidden composition of 2–4 operations from a 44-operation DSL (filter, sort,
  rotate, prefix sum, modulo, ...) maps `list[int] → list[int]`.
- The solver sees 6 input/output examples and writes `def f(xs)`.
- It is graded on 30 hidden inputs, including edge cases such as `[]`, singletons
  and duplicates.

**Why this domain:**
- *Cheap.* Prompts are a few hundred tokens, and grading takes one sandboxed
  process.
- *Deterministic and executable.* Correctness is exact list equality.
- *Tunable.* Composition depth sets the difficulty, and calibration picks depths
  where **both** models' seed solvers land around 25–65%, so neither model
  saturates.
- *Fresh.* Tasks are generated from seeds, so they are new to both models, and
  no program appears in two partitions.
- *Identifiable.* A task is kept only if no alternative program fits the shown
  examples but disagrees on the hidden inputs. The alternatives checked are all
  ~2,000 programs of depth ≤ 2, plus 300 random programs at the target depth.

**Partitions** (disjoint):

| Partition | Purpose |
|---|---|
| `evo_dev` | Evolution feedback and acceptance |
| `evo_progress` | Lineage progress. Never shown to any agent. |
| `audit_dev` | Fresh development tasks for audits |
| `sealed` | Audit scoring only. Never shown to any agent. |

Expected outputs never enter the sandbox. The candidate program receives only
inputs, and comparison happens in the harness.

## 6. Phases

1. **Sealed baselines.** The seed solver is scored on the sealed set under each
   model.
2. **Evolution.** L independent lineages per model, G generations each, in mode
   `full`: both files are editable.
3. **Controls**, each with the same number of generations and the same budgets:
   - **Frozen improver** (`frozen`): `improver.py` edits are discarded, so an
     unchanged procedure improves the solver.
   - **One-generation** (`onegen`): every proposal comes from the *seed* agent,
     with its seed results and no memory, and the best proposal is kept. This has
     the same number of proposals as evolution, with no chaining.
4. **Forked audits.** For gen 0 and each checkpoint, for every lineage, under
   **both** models and every presentation condition:
   - Restore the exact original `solver.py`.
   - Keep the checkpoint's `improver.py`, and nothing else from the lineage.
   - Clear memory and history.
   - Use fresh `audit_dev` tasks.
   - Run K continuation generations under identical call and token budgets for
     both models. Dollar costs differ by price.
   - Score the final solver on `sealed`.
   - Repeat each cell R times and average. Continuations are close to
     all-or-nothing, so a single one is noisy (§9).
   - **Audit results are never fed back.** Evolution and controls finish first,
     audits write only under `audits/`, and a test checks that evolution
     directories are byte-identical before and after audits.
   - At gen 0 every lineage holds the seed procedure. Its 2L replicate cells per
     operator are split into pseudo-origins, which estimates the null
     interaction.

## 7. The source-presentation intervention

The intervention controls what `api.source()` returns, which is the source the
model sees when it edits itself. Evolution always sees the source as evolved
(`orig`). The intervention is applied in audits.

| Condition | What the model sees |
|---|---|
| `orig` | Source as evolved |
| `fmt` | black formatting only |
| `norm` | black, plus canonical alpha-renaming of function locals (`v0, v1, ...`) |
| `neutral` | black, plus renaming to random lowercase names of matched length. This is the **token-length control** for `norm`, and it is equally free of style. |
| `nocomment` | Comments removed and nothing else. This is a separate factor, because comments can hold learned information. |

**Safety (an argument, not a proof):**
- Only names bound inside a function are renamed. That excludes parameters,
  globals and nonlocals.
- Module-level names, attributes, keyword arguments and every string literal
  (including runtime prompt text) are untouched.
- New names collide with no identifier, attribute, keyword or builtin in the
  module.
- A function is left untouched, and reported, if it contains a nested
  def/lambda/class, global/nonlocal, an import, a `match`, a walrus inside a
  comprehension, an f-string `{x=}`, or a call to
  `locals/vars/eval/exec/globals/dir/compile/__import__/getattr/setattr/delattr/hasattr`.

**Mechanical checks on every presented file:**
- It must parse.
- *Renaming:* applying the same mapping to the original AST must give exactly
  the result's AST. This proves the change is an alpha-renaming and nothing
  else.
- *Formatting and comment removal:* the AST must be unchanged.
- Differential tests run original and transformed agents against a recording
  API and require identical prompts, tool calls and return values.
- Unit tests are **not** a general proof of equivalence.
- One known gap remains: exception messages that quote a local name, such as
  UnboundLocalError, change text.

**Reported per cell:**
- token counts before and after (an offline proxy; real runs can use the
  provider's token counter);
- renaming coverage, meaning the share of locals renamed;
- verification status.

When coverage falls below 100% because the model wrote unsupported constructs,
the claim narrows to the functions that were renamed. The control is never
silently weakened.

**Scope of the claim:** "renaming function-local identifiers and reformatting
changed (or did not change) specialization." It is not a claim about source
representation in general.

**Consequence of the design:** a lineage that edits normalized source continues
in normalized form. This is intended, because the edit is the model's own.

## 8. Estimands, analysis, interpretation

Let g(o, l, x) be the sealed-set gain over the seed solver for operating model x
running lineage l's procedure, evolved by origin o. Replicates are averaged.

**Estimands:**

| Symbol | Definition | Meaning |
|---|---|---|
| d(o, l) | g(o, l, A) − g(o, l, B) | One number per lineage |
| S | (mean d(A, ·) − mean d(B, ·)) / 2 | (H_A + H_B) / 2, half the 2×2 interaction |
| ΔS | S(checkpoint) − S(gen 0) | Primary specialization estimand |
| P_x | mean g(·, ·, x) at checkpoint − mean at gen 0 | Portable gain for operator x, i.e. is the evolved procedure better than the seed procedure for x? |
| Presentation effect | ΔS(orig) − ΔS(pres) | Paired by lineage |

**Comparisons:**
- Each operating model is compared across *both* procedure origins. A stronger
  model's raw advantage cancels out in d.
- RSI is tested with full − frozen on the progress set, plus the one-generation
  baseline.

**Uncertainty:**
- Welch t-intervals with Satterthwaite df, over lineages. Lineages are the unit
  of replication, since tasks within a lineage are not independent.
- A percentile bootstrap was tried and rejected. With 3 lineages per origin it
  was anti-conservative, and it produced a false positive in the null
  simulation.
- A logit-scale S is reported for headroom.

**Pre-registered readings:**

| Observation | Reading |
|---|---|
| P_x > 0 for both operators, ΔS ≈ 0 | Reusable improvement procedures (portable gains) |
| ΔS > 0, CI excludes 0 | Specialization grew |
| ΔS(orig) − ΔS(norm) > 0, CI excludes 0, and not also explained by `neutral` | Specialization depends partly on the identifier presentation |
| Normalization shifts every cell equally | *Not* evidence for H2 (main effect only) |
| A swap penalty alone, with no change in ΔS | *Not* evidence of a source-representation mechanism |
| full − frozen ≤ 0 | The RSI mechanism was not demonstrated. Specialization results are then moot. |

No outcome is read as consciousness, a secret language, or unbounded
intelligence growth.

## 9. What the simulations show (mock models; not evidence about real models)

The prototype runs the whole design end to end with two deterministic mock
"families" (`brainswap/mock.py`). Each has a scenario with a known built-in
effect:

- **null:** no effect.
- **presentation:** a mock edits better when its own source uses its own naming
  style.
- **content:** strategy notes written by a model help that model more.

Grading, acceptance, audits and analysis are all real. Results:

| Scale | Scenario | ΔS at gen 8 (orig), 95% CI | Presentation effect (orig − norm) | Reading |
|---|---|---|---|---|
| Pilot (4 lineages/model, `orig`+`norm`, 2 replicates) | null | +4.4 [−2.9, +11.7] | +7.9 [−3.5, +19.3] | Correctly nothing |
| Pilot | presentation (large built-in effect) | **+8.1 [+0.8, +15.4]** | **+11.2 [+0.2, +22.2]** | Detected, barely |
| Pilot | content (notes help their author) | +4.7 [−3.0, +12.3] | +7.0 [−4.0, +18.0] | Not detected |
| Powered (16 lineages/model, 3 presentations, 2 replicates) | null | −0.1 [−7.4, +7.1] | +3.3 [−7.6, +14.3] | Correctly nothing |
| Powered | presentation | **+8.5 [+1.4, +15.6]** | +10.8 [−0.4, +22.0]; `neutral` +4.0 [−6.5, +14.5] | Specialization detected; the presentation effect is borderline even here |
| Powered | content | (simulation still running at time of writing) | | |

The full − frozen RSI comparison had wide or undefined intervals in every run: the
pilot has one frozen lineage per model, so that comparison needs the powered design.

**Implications:**
- The analysis does not invent effects. The null scenario shows no false
  positives.
- At pilot scale, intervals are about ±7 tasks out of 40, so only a very large
  specialization effect would be visible, and even the deliberately large built-in
  effect was only just detected.
- Continuations are the main source of noise: either the solver gets its big fix
  in K generations or it doesn't. That is why each audit cell is repeated.
- The scout measures this noise on real models before the pilot runs.

## 10. Staged plan and go/no-go

| Stage | What | Decides |
|---|---|---|
| 0 | `preflight`: one real solver call and one improver call per model. `calibrate`: seed solve rate by depth. | Do both models follow the format without refusals? Which task depths? |
| 1 | **`scout`**: 2 lineages per model, 6 generations, gen-0 and gen-6 audits, `orig` only | GO / NO-GO for stage 2, against the criteria below |
| 2 | **`pilot`**: 3 lineages per model, 6 generations, 1 frozen and 1 one-generation baseline per model, audits at gen 0 and gen 6 × {orig, norm} × 1 replicate. The `neutral` length control and replicates live in `powered.yaml`. | Feasibility: failure modes, variance, and any very large effect |

**Scout criteria** (fixed in `brainswap/scout.py` before the scout ran):

| Criterion | Requirement |
|---|---|
| C1 health | Refusals < 5% of calls, no served-model mismatches, fewer than half of generations lost to crashes or policy violations |
| C2 headroom | Seed solver at 20–70% on the sealed set under both models |
| C3 loop works | Each model's lineages gain ≥ 1 development task on average, with at least one procedure edit accepted per model |
| C4 divergence | At least one lineage per model ends with a non-seed procedure |
| C5 noise | Pilot minimum detectable specialization, estimated from the scout's gen-0 replicate variance, ≤ 15% of the sealed set |
| C6 cost | The projected pilot fits within the configured spending limits |

**On a NO-GO,** the scout prints the specific fix for each failed criterion,
for example: raise replicates, drop `neutral`, change depths, or report that
procedure edits never stick as the finding.

**Pilot vs. powered study.** The pilot is a **feasibility pilot**. Its ~±5-task
intervals can rule in only a very large effect, and they cannot rule out a small
one. A study that can see effects of a few tasks is `configs/powered.yaml`:
- 12 lineages per model, 12 generations, checkpoints at 6 and 12;
- an 80-task sealed set and 4 presentations.

With the pilot's per-lineage noise σ_d, the minimum detectable S is about
2.8·σ_d/√(2L), and ΔS needs roughly twice the lineages of S at equal power.

**Models:**

| Model | Family | Pinning |
|---|---|---|
| `claude-haiku-5-5` | Anthropic | No dated snapshot is published, so every call records the served model and any mismatch discards the response. |
| `claude-sonnet-5-5` | Anthropic | Same as above. Effort set to `low`. Used in the second pilot. |
| `gpt-6.1-terra` | OpenAI | No dated snapshot published; served model recorded per call. Reasoning effort set to `low`. |

Model B was chosen for being a current frontier model from a different vendor. A
frontier-vs-small pairing risks a headroom mismatch that calibration must catch.

## 11. Integrity and safety

- **Isolation.** Model-written code runs only in bubblewrap: no network, private
  /tmp, CPU, memory and file limits, and the repo is invisible. The in-process
  path exists only for mock runs and is refused for real models.
- **Broker.** The agent never holds an API key. Requests must be plain text,
  because image or document blocks could make the API server fetch a URL.
- **Policy check** on every candidate: a stdlib allowlist, no introspection or
  dunders, no branching on task IDs, and both entry points must call the model.
- **Refusals are data.** Haiku 5.5 carries safety classifiers. Refusals are
  counted per model, never retried on another model, and never routed to a
  fallback.
- **Spend.** Every model call is appended to `spend.jsonl` as it happens, and a
  global cap is checked before every generation and evaluation, across resumes.
  Rejected candidates, trials and audits are all counted.

## 12. Known limitations

1. **Feasibility, not power.** At pilot size, only very large effects are detectable
   (§9–10).
2. **One brain per cell.** Procedure operator and solver model are the same
   model. The 2×2×2 split is future work.
3. **Hitchhiking acceptance.** Procedure edits are not selected on their own
   merit (§4).
4. **Narrow intervention.** It covers function-local renaming and formatting
   only. Module-level names and strings are deliberately untouched.
5. **Thinking parity.** Each model runs at its default reasoning setting under
   equal call and token budgets, so a model that thinks more pays in tokens,
   not in calls.
6. **Mock realism.** Simulated call counts are only as good as the resemblance
   of mock edits to real ones. The scout's measured tokens and calls correct
   the estimate.
7. **One unread source.** The MDPI paper is still unassessed.
8. **Resume granularity.** A line interrupted mid-run restarts from scratch.
   Its spend is still counted.

## 13. Reproduce

```bash
pip install -r requirements.txt
python -m pytest -q                                            # includes brainswap tests
python -m brainswap selftest                                   # normalizer, sandbox, path equivalence
python -m brainswap simulate --scenario all                    # SIMULATED pilot (3 scenarios)
python -m brainswap simulate --scenario all --config demo_powered.yaml
python -m brainswap budget                                     # pilot cost estimate
python -m brainswap scout --mock                               # dry run of the go/no-go
python -m brainswap demo                                       # site/brainswap_demo.html
# real (needs ANTHROPIC_API_KEY, GEMINI_API_KEY; or use the `brainswap` workflow)
python -m brainswap preflight && python -m brainswap calibrate
python -m brainswap scout --budget <dollars>
python -m brainswap run --config pilot.yaml                    # only after GO
```
