# r43 External Ranking Source Audit

## Scope

Audited the current complete r43 live-probed pool before any provider baseline
freeze or target benchmark request. The work was limited to read-only public
source acquisition, exact identity coverage, and hash-only evidence recording.

## Evidence

- Current r43 registry: 10 logical canonical groups and 10 eligible physical
  profiles; the ranking template is bound to the final probe-bound registry
  digest rather than the pre-binding registry copy.
- LiveBench snapshot: 39 ranked rows, literal coverage `0/10`.
- Chatbot Arena snapshot: 384 ranked rows, literal coverage `1/10`.
- SimpleBench snapshot: 93 ranked rows, literal coverage `1/10`.
- No source family covers the complete pool; common complete source family
  count is zero.
- Effort, namespace, display-name, and precision variants were retained only
  as diagnostics. They were not treated as model identity proof.
- No target benchmark request, target label, target score, or Fusion prompt
  change was made.

## Decision

The ranking template remains `template_only=true` and
`ranking_assignment_present=false`. A rank-1/rank-2/rank-3 freeze would be
scientifically unsupported until two complete independent source families or
two pre-registered complete-pool non-target evaluations are available, with
dated identity attestations and population counts.

## Verification

The snapshots were acquired through `http://127.0.0.1:10808` and stored under
`/mnt/storage/axio_fusion_benchmarks/non_target_ranking_sources/r43_2026_08_09/`.
The safe receipt contains hashes, counts, and blocker codes only; it contains
no provider credentials, raw provider URLs, prompts, labels, or outputs.
