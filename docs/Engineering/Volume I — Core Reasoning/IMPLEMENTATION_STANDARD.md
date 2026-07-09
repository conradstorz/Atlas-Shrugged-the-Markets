# IMPLEMENTATION_STANDARD.md

**Project Atlas**

**Engineering Specification ESS-005**

**Status:** Draft for Founder Review
**Version:** 1.0-DRAFT
**Authority:** This document defines the engineering standards for implementing Atlas. Every source file, pull request, test, review, and architectural change shall conform to these standards unless an approved Architectural Decision Record (ADR) explicitly documents an exception.

---

# Introduction

Engineering excellence is achieved through consistent discipline rather than occasional brilliance.

This document establishes the implementation standards that preserve the quality, clarity, and longevity of Atlas.

These standards apply equally to production code, tests, documentation, tooling, automation, and infrastructure.

Every contribution should leave Atlas in a better state than it was found.

---

# Engineering Philosophy

Implementation exists to express architecture.

Architecture exists to express philosophy.

No implementation decision should contradict the Foundation Documents or the Engineering Specifications.

When uncertainty exists:

1. Foundation Documents prevail.
2. Engineering Specifications prevail.
3. ADRs resolve architectural questions.
4. Implementation follows.

---

# Definition of Complete

A capability is complete only when it includes:

* implementation,
* automated tests,
* documentation,
* appropriate logging,
* error handling,
* review,
* and traceability.

Code alone is never considered complete.

---

# The Rule of Three

Every feature shall include:

1. Production implementation.
2. Automated verification.
3. Human-readable documentation.

If any element is missing, the feature is incomplete.

---

# Repository Organization

The repository shall reflect the Atlas architecture rather than technical frameworks.

Directory names should communicate domain responsibility.

Avoid generic directories such as:

* utils
* helpers
* misc
* common

Prefer meaningful domains that describe purpose.

Every source file should have a clear architectural home.

---

# Naming

Names should communicate intent.

Prefer business terminology over implementation terminology.

Examples:

Good:

* CapitalAllocation
* ThemeExposure
* InvestmentThesis
* DividendAssessment

Avoid:

* Manager
* Helper
* Processor
* Util
* DataThing

Names should remain understandable without reading implementation details.

---

# Functions

Functions should:

* perform one clearly defined responsibility,
* be easy to test,
* avoid hidden side effects,
* express intent through naming,
* return meaningful values.

Functions should generally remain small enough to understand without scrolling extensively.

Complexity should be decomposed through composition rather than deeply nested logic.

---

# Classes

Classes represent domain concepts.

Classes should not become collections of unrelated behavior.

Large classes should usually indicate multiple responsibilities.

Inheritance should remain the exception.

Composition is preferred.

---

# Dependencies

Every dependency introduces long-term maintenance cost.

Before adding a dependency, contributors should ask:

* Does the standard library already solve this?
* Does Atlas already contain equivalent functionality?
* Is the dependency actively maintained?
* Does it improve long-term clarity?
* Does it reduce overall complexity?

Dependencies should be introduced deliberately.

---

# Configuration

Configuration belongs outside source code.

Hard-coded values should be avoided unless they represent true constants.

Configuration should be:

* explicit,
* documented,
* validated,
* versioned when appropriate.

---

# Secrets

Secrets shall never appear in:

* source code,
* tests,
* documentation,
* examples,
* commit history.

All secrets shall be managed through the centralized secrets architecture defined by Atlas.

Secret access should follow least-privilege principles.

---

# Logging

Logs exist to improve understanding.

Logging should explain:

* what happened,
* why it happened,
* what Atlas decided,
* and what should happen next.

Logs should avoid unnecessary verbosity.

Sensitive information must never be written to logs.

---

# Error Handling

Errors should be informative.

Unexpected failures should:

* preserve context,
* explain probable causes,
* support diagnosis,
* avoid exposing sensitive information.

Atlas should fail clearly rather than silently.

---

# Testing

Every implementation should be testable.

Tests should verify observable behavior rather than implementation details.

Where practical:

* unit tests verify individual behavior,
* integration tests verify collaboration,
* regression tests preserve previous behavior,
* acceptance tests validate user expectations.

Testing is specified in ESS-006.

---

# Documentation

Documentation evolves with implementation.

Behavior changes require documentation updates.

Documentation should explain:

* purpose,
* assumptions,
* constraints,
* extension points,
* and architectural reasoning.

Documentation is part of the implementation.

---

# Source Control

Every commit should represent one coherent idea.

Commit messages should explain intent rather than mechanics.

Examples:

Good:

"Introduce Theme Exposure Assessment"

Poor:

"Fixed stuff"

History should remain understandable.

---

# Code Reviews

Reviews exist to improve Atlas.

They are collaborative rather than adversarial.

Reviewers should evaluate:

* correctness,
* clarity,
* architecture,
* maintainability,
* documentation,
* tests,
* adherence to Foundation Documents.

Disagreement should be resolved through evidence.

---

# Architectural Changes

Architectural changes require an ADR whenever they:

* introduce new architectural concepts,
* alter subsystem responsibilities,
* change canonical definitions,
* introduce significant dependencies,
* modify engineering standards.

ADRs preserve institutional memory.

---

# Backward Compatibility

Interfaces should remain stable whenever practical.

Breaking changes require:

* documented rationale,
* migration guidance,
* version identification,
* architectural justification.

Compatibility should be preserved unless change clearly improves the long-term health of Atlas.

---

# Technical Debt

Technical debt should be:

* visible,
* documented,
* intentional,
* temporary.

Unacknowledged technical debt is a defect.

Known technical debt should include a plan for eventual resolution.

---

# Quality Gates

Before any contribution is accepted, it shall:

* satisfy the Foundation Documents,
* comply with applicable Engineering Specifications,
* pass automated tests,
* include documentation updates,
* preserve explainability,
* avoid introducing unnecessary complexity,
* maintain architectural consistency.

Passing tests alone is insufficient.

---

# Definition of Done

A contribution is complete when another engineer can:

* understand it,
* test it,
* extend it,
* document it,
* and maintain it

without requiring the original author.

That is the standard Atlas seeks to achieve.

---

# Closing Reflection

Software is temporary.

Engineering discipline endures.

The purpose of these standards is not to restrict contributors.

It is to preserve clarity, trust, and long-term maintainability.

Atlas is intended to remain understandable for decades.

Every implementation decision should move the project toward that objective.

The measure of successful engineering is not merely that today's software works.

It is that tomorrow's engineer is grateful for today's decisions.
