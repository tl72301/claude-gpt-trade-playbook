# Claude and GPT Trade Playbooks

If Claude develops a way to improve a puzzle solver, how well does that approach work for GPT? I tested it in both directions by having the two models trade playbooks.

Claude and GPT started with the same puzzle-solving program. Each also had a second program that reviewed the solver's results and proposed edits to both programs, including itself. I call that second program the playbook. Over six rounds, each model could revise both programs.

Then I set the improved solvers aside. I wanted to see what carried over in the playbook itself, so every swap run started with the original solver. Claude tried improving it starting with a playbook it had developed, and starting with one GPT had developed. GPT did the same. The model doing the work could keep editing the playbook along the way. After three rounds, I scored the resulting solvers on 40 puzzles held back from practice.

Claude's solver averaged 2.3 more correct answers when Claude started with its own playbook instead of GPT's. For GPT, the gap was 3.0 puzzles in favor of its own. Both comparisons pointed in the same direction, but with three runs per model, the results varied too much to establish a reliable advantage.

## The setup

- **Models:** Claude Sonnet 5.5 and GPT-6.1 Terra, called through their APIs at each provider's "low" reasoning setting. The models themselves never changed. Only the two programs did.
- **Runs:** three independent runs per model, six rounds each. Four more runs per model kept the playbook fixed, for comparison.
- **Puzzles:** 16 practice puzzles scored each round, 16 fresh practice puzzles for the swap, 20 for tracking progress, and 40 held back for the final score. No puzzle appears in more than one set.

## What solving a puzzle involved

Each puzzle hides a rule that turns one list of integers into another. Here are three of the six examples the solver saw for one real practice puzzle (`pbe-ee94e2a552` in [tasks.json](runs_brainswap/brain-swap-pilot-v3/tasks.json)):

| Input | Output |
|---|---|
| `[7, 0, 8, 1, 6, -4, 1, 0, 2]` | `[2, 3, 7, 2, 3, 1]` |
| `[11, -3, 9, 7]` | `[4]` |
| `[2, -4, 10, 10]` | `[7]` |

The solver had to infer the rule and write a Python function for it. This one chains three steps: drop the first three numbers, subtract 3 from each, and take the absolute value.

```python
def f(xs):
    xs = xs[3:]
    xs = [x - 3 for x in xs]
    xs = [abs(x) for x in xs]
    return xs
```

The function was then run on 30 lists the solver never saw, including edge cases like `[]` and `[0]`. A puzzle counted as solved only if all 30 matched.

### One improvement round

The original solver ([`brainswap/seed/solver.py`](brainswap/seed/solver.py)) asked the model once and handed in whatever code came back. It already contained a loop that could test the code on the shown examples and retry, but the loop was switched off.

Each round followed the same steps:

1. The solver attempted the 16 practice puzzles.
2. The playbook ([`brainswap/seed/improver.py`](brainswap/seed/improver.py) at the start) received the results. For each failed puzzle, it saw the shown examples and how the attempt failed, such as "12/30 hidden tests passed." It never saw the hidden lists.
3. The model, working through the playbook, proposed a new solver and a new playbook.
4. The harness scored the new solver on the practice puzzles and kept the change only if its first score beat the best so far and its average over two scores did too. In these runs, a change also had to include an edit to the playbook.

In Claude's first run, the original solver averaged 7 of 16 practice puzzles. In round 1, Claude switched the retry loop on, asked for four attempts (the harness capped each puzzle at three model calls), and added hints about rules built from neighboring numbers, such as pairwise sums or differences. It also changed the playbook to try two candidate edits and keep the one that did better on a quick trial. The new version scored 8 and then 7, an average of 7.5, so the change was kept ([history](runs_brainswap/brain-swap-pilot-v3/evolution/A0/history.json)).

## How the swap worked

After six rounds, I took the playbook from each of the six runs, three from Claude and three from GPT. For each one, I:

- reset the solver to the original version,
- cleared the external memory log, which held the notes passed between rounds,
- gave it 16 fresh practice puzzles, and
- ran three more rounds with Claude doing the work, and separately with GPT.

I reset the solver so the comparison would reflect what the playbook brought, without the head start of an already improved solver.

The model doing the work kept editing the playbook during the swap. The same rule applied as in the main runs, so any change it kept had to include a playbook edit, and the playbook changed in 23 of the 24 swap runs. A swap run is closer to handing someone a playbook and letting them revise it as they go than to having them follow a finished manual. The model doing the work also ran the solver on every puzzle, and anything already written into the playbook's code and prompts carried over.

For comparison, I ran the original playbook through the same three rounds six times under each model.

## Results

Each number is the average gain on the 40 held-back puzzles, compared with the original solver run by the same model. The original solver scored 16 of 40 under Claude and 17.5 under GPT, each the average of two tests.

| Model doing the work | Started with Claude's playbook | Started with GPT's playbook | Started with the original playbook |
|---|---|---|---|
| Claude | **+4.3** | +2.0 | +3.2 |
| GPT | +5.5 | **+8.5** | +5.8 |

Bold marks each model starting with its own playbook. Each evolved-playbook cell averages three runs, and each original-playbook cell averages six.

For example, +8.5 means that when GPT started with one of its own evolved playbooks, its solver after three rounds got 8.5 more held-back puzzles right than the original solver did under GPT, or about 26 of 40.

## What I can conclude

**Own versus borrowed.** Both models did better starting with their own playbook than with the other model's: Claude by 2.3 puzzles (4.3 against 2.0) and GPT by 3.0 (8.5 against 5.5). Neither borrowed playbook did better than the original playbook.

**The main test.** Those two gaps are final scores. The main test asks a narrower question: did the own-playbook advantage grow while the playbooks evolved? It averages the two gaps (2.7) and subtracts the same calculation from the runs that started with the original playbook, split into two arbitrary groups. Those runs all used identical playbooks, so their true advantage is zero, yet they still came out at -1.2. The difference is +3.8 puzzles, with a 95% interval of -3.4 to +11.1. Zero is inside the interval, so this pilot can't separate a real advantage from noise. The calculation is in [`brainswap/analysis.py`](brainswap/analysis.py).

**How much a new playbook added.** All 12 runs that started with the original playbook beat the original solver, by 4.5 puzzles on average. The 12 runs that started with an evolved playbook beat it in 11 cases, by 5.1 on average. Most of the gain came from three rounds of the loop itself, whichever playbook it started with.

**What the models' edits added.** In a follow-up, I switched on the original solver's retry loop by hand and changed nothing else. It gained 1.0 puzzle under Claude and 0.5 under GPT, less than any cell in the table for that model ([`retry_only.json`](runs_brainswap/brain-swap-pilot-v3-extra/retry_only.json)). The prompts, hints, and feedback the models wrote around the loop did most of the work.

**Editing the playbook itself.** Over six rounds, runs that could rewrite their playbook gained 3.3 puzzles on the progress set, against 2.3 for runs where it stayed fixed (Claude), and 1.0 against 0.5 (GPT). The per-run gains were 2, 5, 3 against 2, 3, 2, 2 for Claude, and 0, 1, 2 against 1, 0, 1, 0 for GPT. Welch 95% intervals on those gaps both include zero, so this pilot found no benefit from letting the playbook edit itself.

## What I'd test next

A few limitations change how to read these results:

- **Small sample.** There were three runs per model, and they varied a lot. One of GPT's own-playbook runs gained 12.5 puzzles while another gained 4.5.
- **The playbooks kept changing.** Because the model doing the work also edited the playbook and ran the solver, the swap measures each model working with a playbook, not the playbook on its own.
- **I went ahead after a NO-GO.** The final scout run missed two of its go/no-go criteria: a resource projection, and a minimum-gain rule that the smaller Claude model (Haiku) didn't meet. I ran the pilot anyway ([`scout_decision.json`](runs_brainswap/brain-swap-scout-v3/scout_decision.json)).
- **Settings weren't fully matched.** Claude's per-call output limit was half of GPT's, and 46 of Claude's solver responses reached it. Additionally, 179 of Claude's 5,043 calls came back as API refusals, while GPT had none in 4,066. I didn't measure how much either affected the results.

The next test I'd run is a second swap with the playbooks frozen. If each model still does better with its own playbook when neither can edit the one it receives, the advantage lives in the playbook as written. If the advantage disappears, it came from how each model revised the playbook during the swap. I'd also estimate the sample size I need before adding runs.

## Check the work

The fastest way to inspect the pilot is to open its saved analysis, [`analysis.json`](runs_brainswap/brain-swap-pilot-v3/analysis.json). The `rows` entry holds the swap results before and after the playbooks evolved, and `lineages` holds each run's practice scores. To recompute everything from the raw runs without calling any API:

```bash
pip install -r requirements.txt
cp -r runs_brainswap/brain-swap-pilot-v3 /tmp/pilot-v3
python -m brainswap analyze --out /tmp/pilot-v3 --config pilot_v3.yaml
```

The copy keeps `analyze` from rewriting the saved file. It prints the same +3.8 and interval.

| What | Where |
|---|---|
| Experiment runner, including the swap | [`brainswap/experiment.py`](brainswap/experiment.py) (`audit_specs`, `audit`) |
| One improvement run and the acceptance rule | [`brainswap/lineage.py`](brainswap/lineage.py) |
| How the solver and playbook run, and what feedback the playbook sees | [`brainswap/runtime.py`](brainswap/runtime.py) (`evaluate`, `run_improver`) |
| Grading against the hidden lists | [`brainswap/grading.py`](brainswap/grading.py) |
| Statistics | [`brainswap/analysis.py`](brainswap/analysis.py) |
| Go/no-go criteria | [`brainswap/scout.py`](brainswap/scout.py) |
| Starting solver and playbook | [`brainswap/seed/`](brainswap/seed/) |
| Pilot config | [`brainswap/configs/pilot_v3.yaml`](brainswap/configs/pilot_v3.yaml) |
| Pilot results | [`runs_brainswap/brain-swap-pilot-v3/`](runs_brainswap/brain-swap-pilot-v3/): `tasks.json`, `sealed_baselines.json`, `cells.json`, `analysis.json`, `evolution/`, `audits/` |
| Follow-up results | [`runs_brainswap/brain-swap-pilot-v3-extra/`](runs_brainswap/brain-swap-pilot-v3-extra/): `retry_only.json`, `frozen/` |

**Reading the files.** In code and data, A is Claude Sonnet 5.5 and B is GPT-6.1 Terra. The playbook is `improver.py`, which the code also calls the "procedure" or "improver." The six main runs are `evolution/A0` through `A2` and `B0` through `B2`. Each swap run is a folder in `audits/` named like `c6-A0-opB-orig`: checkpoint 6, the playbook from Claude's run A0, with GPT doing the work. Runs named `c0-` started with the original playbook. In `analysis.json`, a matrix key like `A->B` means Claude's playbook with GPT doing the work. The code and run folders use the project's working name, `brainswap`.

Earlier runs are in the same folder:

| Run | What it was |
|---|---|
| `brain-swap-scout`, `-v2`, `-v3` | Three small scout runs (Claude Haiku 5.5 vs GPT-6.1 Terra) that caught problems before the pilots |
| `brain-swap-pilot-v2` | First pilot, Claude Haiku 5.5 vs GPT-6.1 Terra |
| `brain-swap-pilot-v3` | The pilot reported above, Claude Sonnet 5.5 vs GPT-6.1 Terra |
| `brain-swap-pilot-v3-extra` | Follow-up: the retry-only baseline and three more fixed-playbook runs per model |

## Running it yourself

These commands run offline with no API calls:

```bash
pip install -r requirements.txt
python -m pytest -q
python -m brainswap selftest
python -m brainswap simulate --scenario null --config ci.yaml   # small simulated run, a few seconds
python -m brainswap simulate --scenario all                     # full simulated pilot, all three scenarios, about a minute
```

A new real run calls the Anthropic and OpenAI APIs, which costs money. It needs `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`, and Linux with bubblewrap, because model-written code only runs inside a sandbox with no network access and no API keys. Set your own spending cap under `limits` in the config first, then run `python -m brainswap run --config pilot_v3.yaml`, or use the stages in [`.github/workflows/brainswap.yml`](.github/workflows/brainswap.yml). `python -m brainswap --help` lists every command.

## About this public copy

This repo is a cleaned copy of my working repo. I removed dollar amounts, per-call token counts, and my own spending caps from the run data, logs, and configs. Each call in `spend.jsonl` keeps its model, role, refusal status, and a `hit_output_limit` flag, which marks calls that reached the model's per-call output limit. Re-running the analysis on this data reproduces the published results.

I built this with Claude Code.
