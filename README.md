# Same Solver, Different Improver

Does each AI model gain more from the improvement process it helped write?

I gave Claude Sonnet 5.5 and GPT-6.1 Terra the same two Python files. One solved logic puzzles. The other, `improver.py`, which I call the improvement process, proposed edits to both files, including itself. After six rounds, I restored the original solver, cleared the external memory log, and gave each evolved improvement process three more rounds under each model. Would either model gain more from the improvement process it had helped write?

This repo has the full harness, the configs, and the raw results from every real run.

## How it works

Each agent is two small Python files, and the model can rewrite both of them:

- `solver.py` attempts the puzzles. It decides what to ask the model, how many tries to take, and what answer to hand in.
- `improver.py` is the improvement process. It looks at how the solver did and rewrites both files, including itself.

Each puzzle hides a rule that turns one list of numbers into another, such as "sort high to low, keep numbers under 4, take a running total, and mark odd as 1 and even as 0." The model usually sees six examples and is graded on 30 lists it hasn't seen.

Each round, the improvement process proposes a new solver and a new version of itself. A change is kept only if its first practice score beats the best so far and its average over two tries does too. In the main runs, every proposal had to change both files.

After six rounds, I took each run's evolved improvement process, reset the solver to the original, cleared the external memory log, and gave the process three more rounds under each model. The results were scored on 40 puzzles that were held back from the models the whole time.

## A few highlights from the results

From the second pilot (Sonnet vs Terra) and a follow-up run:

- After three rounds of self-improvement, 23 of 24 test runs scored above the original solver on the 40 held-back puzzles. This held whether a run started with the original improvement process (12 of 12) or an evolved one (11 of 12).
- The original solver had a retry loop that was turned off, and every main run turned it on. Turning it on by hand and changing nothing else gained 1.0 puzzle for Sonnet and 0.5 for Terra, while the evolved solvers gained 4.3 and 8.5.
- Each model did better with its own improvement process than with the other model's, by 2.3 puzzles for Sonnet and 3.0 for Terra. With three runs per model, the main test is inconclusive: +3.8, with a 95% range of -3.4 to +11.1.
- Runs that could rewrite their improvement process didn't show a benefit over runs where it stayed fixed. With four fixed runs per model, both 95% ranges include zero.

There are some limitations worth mentioning. The improvement process could keep editing itself during the swap, and the model running it also ran the solver, so the swap measures each model and process together. The two models' settings weren't fully matched, and 179 of Sonnet's 5,043 calls came back as API refusals (Terra had none). Additionally, the last scout run failed two of its go/no-go criteria, and I ran the pilot anyway. The details are in `runs_brainswap/brain-swap-scout-v3/scout_decision.json`.

## What's in here

| Path | What it is |
|---|---|
| `brainswap/` | The experiment: lineages, swap audits, analysis, the scout's go/no-go rules, and simulated models for offline runs |
| `brainswap/seed/` | The starting solver and improvement process every run began from |
| `brainswap/configs/` | Run configs. `pilot_v3.yaml` is the Sonnet vs Terra pilot and `pilot_v3_extra.yaml` is the follow-up |
| `rsi/` | Shared pieces: the model client, sandbox, broker, and code policy check |
| `runs_brainswap/` | Raw results from every real run, including each generation's code |
| `DESIGN_BRAIN_SWAP.md` | The original design, prior-art review, and simulation results |

The code, run folders, and design doc still use the project's working name, `brainswap`, so the run identifiers match the recorded results.

The runs, in order:

| Run | What it was |
|---|---|
| `brain-swap-scout`, `-v2`, `-v3` | Three small scout runs (Haiku vs Terra) that caught problems before the pilots |
| `brain-swap-pilot-v2` | First pilot, Claude Haiku 5.5 vs GPT-6.1 Terra |
| `brain-swap-pilot-v3` | Second pilot, Claude Sonnet 5.5 vs GPT-6.1 Terra |
| `brain-swap-pilot-v3-extra` | Follow-up: the retry-only baseline and three more runs per model with a fixed improvement process |

## Running it

```bash
pip install -r requirements.txt
python -m pytest -q
python -m brainswap selftest
python -m brainswap simulate --scenario all            # offline, with simulated models
python -m brainswap analyze --out runs_brainswap/brain-swap-pilot-v3 --config pilot_v3.yaml
```

Real runs need `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`, and they run through `.github/workflows/brainswap.yml`. Model-written code only runs inside a bubblewrap sandbox with no network access and no API keys. Set your own spending cap in each config under `limits` before a real run.

## About this public copy

This repo is a cleaned copy of my working repo. I removed dollar amounts, per-call token counts, and my own spending caps from the run data, logs, and configs. Each call in `spend.jsonl` keeps its model, role, refusal status, and a `hit_output_limit` flag, which marks calls that reached the model's per-call output limit. Re-running the analysis on this data reproduces the published results.

I built this with Claude Code.
