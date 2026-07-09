# ADR-0002 — Build the Atlas Kernel Before Investment Logic

**Status:** Accepted  
**Date:** 2026-07-08  

## Context

Atlas will eventually support knowledge graphs, scoring, capital allocation, scenarios, plugins, and private portfolio analysis. Adding those capabilities before the platform boundary is established risks coupling domain logic to infrastructure.

## Decision

The first production-style build milestone is the Atlas Kernel. The Kernel provides configuration, secrets, logging, plugin lifecycle, health reporting, and application lifecycle only.

Investment-specific concepts are explicitly excluded from the Kernel.

## Consequences

- Atlas can host future capabilities without modifying platform code.
- The Domain remains insulated from FastAPI, SQLite, Docker, HTTP, JSON, and other external technologies.
- Later engines integrate through defined interfaces instead of changing Kernel responsibilities.
