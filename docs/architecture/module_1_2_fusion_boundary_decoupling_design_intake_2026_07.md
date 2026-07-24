# Module 1/2 Fusion Boundary Decoupling Design Intake

Date: 2026-07-19
Status: ready for implementation and focused verification.

## Decision

ASciFS owns research orchestration, storage, retrieval, Session isolation and
local tool execution. Fusion API is a separate commercial service. ASciFS may
consume an externally generated, metadata-only readiness report when a caller
explicitly supplies one, but a research run must never build, import, start, or
fail because the Fusion service is absent.

The dependency direction is therefore:

```text
ASciFS local research/Harness --optional metadata-only--> external Fusion readiness
external Fusion service       --no runtime dependency--> ASciFS research chain
```

## In scope

- Remove the unconditional Fusion smoke-builder call from the research Harness.
- Preserve standalone readiness parsing for an explicitly supplied report or a
  separately generated artifact.
- Mark missing external readiness as `missing` and `blocking_for_local_research:
  false`.
- Do not persist prompts, responses, credentials, paper text or provider URLs
  in the ASciFS readiness projection.
- Keep the existing model-tier readiness parser available to callers that
  explicitly integrate the independent service.
- Add a regression proving the local Harness path has no Fusion invocation.

## Out of scope

- Implementing or changing Fusion API algorithms, providers, models or routes.
- Treating Fusion readiness as evidence that ASciFS research quality is ready.
- Making external model calls from the local research acceptance suite.

## Acceptance contract

1. Importing and running the local research Harness does not import the Fusion
   server module as an execution dependency.
2. With no external readiness argument, the Harness produces all local research
   artifacts and reports Fusion status as `missing` with an explicit optional
   boundary marker.
3. With an external metadata-only report, the Harness consumes and projects its
   readiness without generating a new report.
4. An invalid or unsafe external report remains fail-closed for Fusion use but
   does not corrupt or expose local Session data.
5. Existing resolver/summary compatibility tests continue to pass.

## Failure and recovery

The local path is the recovery mode. A missing or unavailable Fusion service
causes only a metadata advisory for future model orchestration; it does not
prevent local literature, graph, RAG, web dry-run or Session artifact work.
