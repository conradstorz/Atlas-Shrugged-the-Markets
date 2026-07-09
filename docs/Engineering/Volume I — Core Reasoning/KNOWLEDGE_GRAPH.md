# KNOWLEDGE_GRAPH.md

**Project Atlas**

**Engineering Specification ESS-002**

**Status:** Draft for Founder Review
**Version:** 1.0-DRAFT
**Authority:** This document defines the Atlas Knowledge Graph. It specifies how Atlas represents relationships between entities, how knowledge is accumulated, and how understanding emerges from connected information.

---

# Introduction

Information answers questions.

Knowledge answers relationships.

Wisdom emerges from understanding those relationships.

The purpose of the Atlas Knowledge Graph is not to replace databases.

Its purpose is to transform isolated facts into connected understanding.

The Knowledge Graph is therefore one of the core reasoning systems within Atlas.

---

# Design Philosophy

Atlas does not reason primarily from values.

Atlas reasons from relationships.

A company is not important because it exists.

A company becomes important because of its relationships.

Everything meaningful in Atlas is connected.

Knowledge grows through those connections.

---

# The Nature of Knowledge

Atlas distinguishes four levels of understanding.

## Data

An isolated observation.

Examples:

* A share price.
* A dividend.
* A revenue figure.

Data has little meaning by itself.

---

## Information

Data with context.

Examples:

* Revenue increased 12%.
* Dividend has grown for 15 consecutive years.

Information answers:

**What happened?**

---

## Knowledge

Information connected to other information.

Examples:

* Rising electricity demand increases demand for transformers.
* Data-center expansion increases electricity demand.
* AI growth increases demand for data centers.

Knowledge answers:

**How are these things connected?**

---

## Understanding

Knowledge evaluated in light of the investor's purpose.

Examples:

* My portfolio benefits from AI infrastructure.
* My portfolio depends heavily on electricity availability.
* My portfolio has concentrated exposure to one macroeconomic theme.

Understanding answers:

**What does this mean for me?**

---

# The Graph

Every node represents an Entity.

Every edge represents a Relationship.

Nodes do not contain meaning by themselves.

Meaning emerges through relationships.

---

# Canonical Node Types

Reality Nodes

* Company
* Fund
* Security
* Industry
* Country
* Currency
* Economic Indicator
* Commodity

Knowledge Nodes

* Theme
* Scenario
* Factor
* Model
* Score
* Insight

Human Nodes

* Portfolio
* Thesis
* Decision
* Journal Entry
* Goal
* Conviction

The graph intentionally distinguishes between these categories.

---

# Canonical Relationship Types

Atlas recognizes several categories of relationships.

## Structural

Examples:

* owns
* contains
* issued_by
* headquartered_in
* belongs_to

These describe objective structure.

---

## Economic

Examples:

* depends_on
* competes_with
* supplies
* consumes
* benefits_from
* threatened_by

These describe economic relationships.

---

## Analytical

Examples:

* contributes_to_score
* increases_risk
* reduces_diversification
* overlaps_with
* strengthens
* weakens

These are created by Atlas models.

---

## Human

Examples:

* believes
* owns
* purchased
* sold
* documents
* prefers
* rejects

These represent investor actions and judgments.

---

# Relationship Properties

Every relationship may include metadata.

Examples:

* confidence
* source
* effective date
* expiration date
* strength
* direction
* explanation

Relationships are not merely connections.

They are evidence-bearing objects.

---

# Themes

Themes occupy a central role within the graph.

Unlike sectors, themes may connect unrelated industries.

Example:

Artificial Intelligence

↓

Semiconductors

↓

Power Infrastructure

↓

Cooling

↓

Networking

↓

Construction

↓

Cybersecurity

↓

Automation

↓

Software

↓

Robotics

One theme creates many paths.

---

# Scenarios

Scenarios are not predictions.

A Scenario represents one coherent possible future.

Example:

Persistent Inflation

↓

Higher borrowing costs

↓

Reduced construction

↓

Pressure on growth valuations

↓

Benefit to selected value sectors

↓

Portfolio impact

Multiple scenarios may exist simultaneously.

Atlas never assumes one scenario is inevitable.

---

# The Thesis Graph

Every investment thesis becomes a connected subgraph.

Decision

↓

Thesis

↓

Evidence

↓

Assumptions

↓

Supporting Themes

↓

Risks

↓

Scenarios

↓

Expected Outcomes

Atlas therefore evaluates reasoning rather than isolated statements.

---

# Knowledge Accumulation

Knowledge should compound.

Every new observation should strengthen, weaken, or refine existing relationships.

Atlas should avoid duplicate knowledge.

Instead, new evidence updates confidence in existing relationships.

---

# Provenance

Every relationship should preserve its origin.

Examples include:

* SEC filing
* Annual report
* User research
* Market data
* Plugin
* Manual entry

Users should always be able to ask:

> Why does Atlas believe this relationship exists?

The answer should always be available.

---

# Confidence

Confidence belongs to relationships.

Not facts.

A company's headquarters is either correct or incorrect.

A relationship such as:

AI increases electricity demand

may possess varying confidence depending upon available evidence.

Atlas should therefore model confidence independently.

---

# Time

Relationships evolve.

The graph therefore recognizes:

Beginning

Current State

Historical State

Retired Relationship

Knowledge should preserve history rather than overwrite it.

---

# Explainability

Every Insight should be explainable by traversing the graph.

Example:

Portfolio

↓

Holding

↓

Company

↓

Industry

↓

Theme

↓

Scenario

↓

Evidence

↓

Sources

Atlas should never produce an insight that cannot be reconstructed through the graph.

---

# Learning

The graph is cumulative.

Knowledge should become richer over time.

Relationships should become stronger.

Models should become better informed.

Understanding should become deeper.

Atlas therefore becomes increasingly valuable through continued use.

---

# Future Growth

The Knowledge Graph is intentionally domain-independent.

Although initially focused on investing, the architecture supports any field in which understanding emerges from relationships.

This flexibility is a consequence of the graph's design rather than its primary objective.

Atlas remains dedicated to investment decision support.

---

# Closing Reflection

The Atlas Knowledge Graph exists for one reason:

To transform isolated information into connected understanding.

Facts alone rarely improve decisions.

Relationships do.

By preserving those relationships, documenting their evidence, recording their confidence, and making them explainable, Atlas builds a body of knowledge that grows more valuable over time.

Knowledge is not merely stored.

It is cultivated.

That is the purpose of the Atlas Knowledge Graph.
