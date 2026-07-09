# DATA_MODEL.md

**Project Atlas**

**Engineering Specification ESS-001**

**Status:** Draft for Founder Review
**Version:** 1.0-DRAFT
**Authority:** This document defines the canonical domain model of Atlas. It establishes the vocabulary used throughout the project. Architecture, database schemas, APIs, user interfaces, documentation, and source code should derive their terminology from this specification.

---

# Introduction

Atlas is a knowledge system.

Knowledge systems require a shared language.

This document establishes the canonical meaning of every major concept within Atlas.

These definitions are intentionally independent of programming language, database implementation, or user interface.

Every engineering artifact should remain consistent with this vocabulary.

---

# Design Philosophy

The Atlas data model is organized around **meaning** rather than implementation.

It does not begin with tables.

It does not begin with classes.

It begins with concepts.

Those concepts become objects.

Objects become relationships.

Relationships become knowledge.

Knowledge supports decisions.

---

# The Canonical Hierarchy

Atlas organizes information into six conceptual layers.

```
Reality
    ↓
Entities
    ↓
Relationships
    ↓
Knowledge
    ↓
Models
    ↓
Decisions
```

Each layer builds upon the one before it.

---

# Canonical Definitions

## Entity

An Entity is anything Atlas can identify independently.

Examples include:

* Company
* Fund
* Security
* Person
* Portfolio
* Economic Theme
* Country
* Currency
* Industry

Entities possess identity.

Entities may participate in relationships.

---

## Asset

An Asset is anything capable of contributing economic value to a portfolio.

Examples:

* ETF
* Mutual Fund
* Individual Stock
* Bond
* REIT
* Commodity
* Cash
* Cryptocurrency

Every investable instrument is an Asset.

Not every Entity is an Asset.

---

## Security

A Security is a tradable financial instrument.

A Security is one type of Asset.

Examples:

* Common stock
* Preferred stock
* ETF
* Mutual fund
* Corporate bond

Security describes legal and market characteristics.

Asset describes economic purpose.

---

## Company

A Company is a legal organization that creates economic value.

Companies may issue Securities.

Companies participate in Industries.

Companies express exposure to Themes.

---

## Fund

A Fund is an Asset that owns other Assets according to a defined investment strategy.

Funds contain Holdings.

Funds may themselves be held inside Portfolios.

Atlas treats ETFs, mutual funds, and similar pooled investments as Funds.

---

## Holding

A Holding represents ownership.

It connects an owner to an Asset.

Examples:

Portfolio → ETF

ETF → Company

Mutual Fund → Bond

Holding is a relationship, not an Asset.

---

## Portfolio

A Portfolio is a purposeful collection of Holdings assembled to achieve one or more investor-defined objectives.

A Portfolio belongs to an Investor.

A Portfolio expresses Decisions.

---

## Investor

An Investor is the decision-making authority.

Only the Investor possesses:

* goals
* values
* constraints
* convictions
* time horizon
* acceptable risk

Atlas models these attributes but never invents them.

---

## Theme

A Theme represents an enduring economic idea that influences multiple industries or investments.

Examples:

* Artificial Intelligence
* Electrification
* Aging Population
* Energy Transition
* Automation
* Cybersecurity

Themes organize understanding.

They are neither sectors nor industries.

---

## Thesis

A Thesis explains why capital has been allocated to an investment.

A Thesis should include:

* reasoning
* supporting evidence
* assumptions
* expected outcomes
* invalidation criteria

Every significant investment deserves an explicit Thesis.

---

## Evidence

Evidence consists of observable information that supports or challenges a Thesis.

Evidence may strengthen confidence.

Evidence may weaken confidence.

Evidence never changes automatically into conclusions.

---

## Knowledge

Knowledge is organized evidence.

Knowledge consists primarily of relationships.

Knowledge may evolve.

Reality does not.

---

## Model

A Model is an explainable interpretation of Knowledge.

Examples include:

* scoring
* risk analysis
* scenario analysis
* diversification analysis
* overlap analysis

Models support Decisions.

They do not replace them.

---

## Scenario

A Scenario is a coherent description of possible future conditions.

Examples:

* Persistent Inflation
* Falling Interest Rates
* AI Infrastructure Boom
* Global Recession

Scenarios evaluate resilience rather than predict outcomes.

---

## Decision

A Decision represents an intentional allocation of capital.

Every Decision belongs to an Investor.

Every Decision should reference:

* Thesis
* Evidence
* Portfolio
* Time
* Context

---

## Conviction

Conviction represents the Investor's confidence in a Thesis.

Conviction is subjective.

Evidence is objective.

Atlas intentionally models these separately.

---

## Journal Entry

A Journal Entry preserves reasoning at a point in time.

Journal Entries are immutable historical records.

History should be expanded rather than rewritten.

---

# Relationships

Atlas derives understanding from relationships rather than isolated objects.

Examples include:

```
Portfolio

contains

Holding

references

Asset

issued by

Company

participates in

Industry

contributes to

Theme

influences

Scenario

supports

Thesis

justifies

Decision
```

Relationships are first-class citizens within Atlas.

---

# Identity

Every Entity possesses one canonical identity.

Aliases may exist.

Duplicates should not.

Identity must remain stable across imports, plugins, and data providers.

---

# Time

Atlas recognizes three forms of time.

## Event Time

When something occurred.

---

## Observation Time

When Atlas learned it.

---

## Decision Time

When the Investor acted.

These timestamps should never be confused.

---

# Provenance

Every significant piece of information should preserve its origin.

Examples include:

* SEC filing
* Company report
* Market data provider
* User entry
* Research plugin

Knowledge without provenance deserves reduced confidence.

---

# Immutability

Historical observations should remain immutable whenever practical.

Corrections create new records.

They do not erase history.

Understanding improves when history remains visible.

---

# Extensibility

The data model is intentionally asset-agnostic.

Future asset classes should integrate by extending the existing vocabulary rather than replacing it.

The canonical definitions should remain stable even as Atlas expands.

---

# Closing Reflection

The purpose of a data model is not merely to organize information.

Its purpose is to create a shared language.

When every contributor, every module, every database table, every API, and every document use the same vocabulary, Atlas becomes easier to understand, easier to maintain, and easier to extend.

The Atlas Data Model therefore serves not only as an engineering specification, but as the common language through which the entire project understands the world.
