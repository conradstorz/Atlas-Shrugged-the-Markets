# ABS-001 — Atlas Kernel

**Project Atlas**  
**Build Specification ABS-001**  
**Status:** Draft Implemented  
**Version:** 0.7.0  

## Objective

Construct the smallest executable Atlas system capable of hosting every future capability while remaining independent of investment-specific logic.

The Kernel provides the environment in which Atlas capabilities execute. It does not contain ETF, portfolio, scoring, market-data, or knowledge-graph logic.

## Build Contract

ABS-001 is complete when Atlas can start, initialize, verify its environment, discover plugins, expose health endpoints, write structured logs, and shut down cleanly without possessing investment knowledge.

## Kernel Responsibilities

The Kernel owns only platform responsibilities:

- Application bootstrap
- Configuration loading and validation
- Secrets provider abstraction
- Structured logging
- Plugin lifecycle
- Health and version reporting
- Graceful shutdown
- Exception framework

## Explicit Non-Responsibilities

The Kernel shall not implement:

- ETFs
- Stocks
- Portfolios
- Scores
- Knowledge Graph
- Database schema
- Market data
- Research
- AI
- User authentication

## Startup Sequence

1. Configuration
2. Secrets provider
3. Logging
4. Plugin registration
5. Plugin validation
6. Plugin initialization
7. Health service readiness

## Shutdown Sequence

Shutdown occurs in reverse order. Plugins are notified, resources are released, and final structured logs are written.

## Acceptance Criteria

ABS-001 is accepted when:

- `uv run atlas kernel-check` starts and stops the Kernel.
- `uv run atlas serve` exposes `/health`, `/ready`, and `/version`.
- A simple `HelloAtlasPlugin` can be added without modifying Kernel code.
- Secrets are redacted by design.
- Structured logs include timestamp, severity, subsystem, message, and correlation identifier.
- Automated tests validate config, secrets, plugins, kernel lifecycle, and health endpoints.

## Definition of Done

A new contributor can clone the repository, run one command, observe Atlas starting successfully, and add a simple plugin without modifying Kernel code.

## Implementation Status

Implemented in v0.7.0 as the first production-style Kernel commit.
