# ADR-0001 — Atlas Will Be Engineered as an Institution Rather Than an Application

**Status:** Accepted  
**Date:** 2026-07-08  

## Context

Atlas began as an ETF evaluation tool but evolved into a private decision intelligence platform for long-term capital allocation. The project requires more than working code; it requires institutional memory, explainability, privacy, and long-term maintainability.

## Decision

Atlas will prioritize architectural clarity, documented reasoning, explainability, and long-term maintainability over rapid feature development.

Engineering specifications and build specifications are first-class artifacts. Significant architectural decisions are recorded as ADRs before or alongside implementation.

## Consequences

- Every major subsystem receives an engineering specification.
- Build milestones receive build specifications.
- Pull requests should reference Foundation Documents, Engineering Specifications, Build Specifications, and ADRs where applicable.
- The project optimizes for decades of evolution rather than rapid feature accumulation.
