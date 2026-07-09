# SCORING_ENGINE.md

**Project Atlas**

**Engineering Specification ESS-003**

**Status:** Draft for Founder Review
**Version:** 1.0-DRAFT
**Authority:** This document defines the Atlas Scoring Engine. It establishes how evidence is evaluated, how assessments are formed, how confidence is represented, and how explainable scores are produced.

---

# Introduction

The purpose of the Atlas Scoring Engine is not to predict future investment performance.

Its purpose is to organize evidence into transparent, explainable assessments that help investors make better-informed decisions.

Atlas does not score investments because they are "good" or "bad."

Atlas evaluates how well an investment aligns with clearly defined criteria, supported by observable evidence.

Every score must therefore be explainable, reproducible, and open to challenge.

---

# Design Philosophy

Scores are summaries.

Evidence is primary.

No score should exist without identifiable evidence.

No recommendation should depend upon a score that cannot be explained.

Atlas therefore treats scores as the final expression of a chain of reasoning rather than the beginning of one.

---

# The Scoring Pipeline

Every score follows the same sequence.

```text
Reality
    ↓
Evidence
    ↓
Assessment
    ↓
Confidence
    ↓
Score
    ↓
Decision Support
```

Each stage preserves the reasoning of the previous stage.

---

# Evidence

Evidence consists of observable information.

Examples include:

* historical dividend growth
* earnings stability
* valuation metrics
* debt ratios
* fund expense ratio
* portfolio concentration
* factor exposure
* theme exposure
* analyst-independent financial data
* documented investor research

Evidence should remain free from opinion.

---

# Assessment

An Assessment interprets evidence according to one explicit criterion.

Examples include:

* Dividend Quality
* Financial Strength
* Valuation
* Diversification
* Income Reliability
* AI Infrastructure Exposure
* Inflation Resilience
* Power Infrastructure Exposure

Every Assessment should answer one question.

Nothing more.

---

# Confidence

Confidence measures the reliability of an Assessment.

Confidence is influenced by factors such as:

* completeness of evidence
* freshness of data
* source reliability
* consistency across sources
* model maturity

Confidence does **not** measure investment quality.

Confidence measures how strongly Atlas believes the Assessment reflects reality.

---

# Score

A Score summarizes one Assessment.

Scores should be normalized to a common range.

Every Score must include:

* value
* confidence
* evidence count
* last evaluation date
* explanation
* contributing assessments

A score without context is incomplete.

---

# Composite Scores

Composite Scores combine multiple Assessments.

Example:

Long-Term Quality Score

may include:

* Financial Strength
* Earnings Stability
* Dividend Sustainability
* Management Quality
* Capital Allocation

Composite Scores should publish their weighting.

Hidden weighting is prohibited.

---

# Explainability

Every Score must answer four questions.

1.

What evidence contributed?

2.

Which Assessments were performed?

3.

How confident is Atlas?

4.

Why did this Score change?

Users should never wonder how a number was produced.

---

# Confidence Is Independent

Two investments may receive identical Scores.

Their Confidence may differ substantially.

Example:

Investment A

Score: 88

Confidence: 96%

Investment B

Score: 88

Confidence: 58%

These represent fundamentally different conclusions.

Atlas intentionally models both.

---

# Missing Evidence

Missing evidence is itself evidence.

Atlas should not estimate missing information without explicit justification.

When evidence is unavailable:

* reduce confidence,
* identify missing inputs,
* explain the limitation.

Artificial precision weakens trust.

---

# Investor Preferences

Investor preferences are not Scores.

Preferences influence how Scores are interpreted.

Examples:

Income-focused investors may prioritize Dividend Quality.

Growth-focused investors may prioritize Innovation.

Conservative investors may emphasize Financial Strength.

Atlas separates objective Assessments from subjective priorities.

---

# Themes

Theme exposure should be evaluated independently.

Example Themes include:

* Artificial Intelligence
* Electrification
* Automation
* Cybersecurity
* Demographic Change
* Energy Transition

Theme Scores describe exposure.

They do not imply desirability.

The investor determines whether exposure aligns with personal objectives.

---

# Scenario Scoring

Scores may be evaluated under Scenarios.

Example:

Persistent Inflation

↓

Infrastructure ETF

↓

Score improves

↓

Growth ETF

↓

Score declines

Scenario Scores evaluate resilience under stated conditions.

They are not forecasts.

---

# Historical Scores

Scores are observations.

History should remain visible.

Atlas preserves:

* current score
* previous scores
* confidence history
* evidence history
* assessment history

Understanding why a score changed is often more valuable than the current score itself.

---

# Explainable Objects

Within Atlas, a Score is not a number.

A Score is an object.

Every Score contains:

* Identifier
* Assessment
* Value
* Confidence
* Evidence
* Assumptions
* Explanation
* Timestamp
* Version
* Provenance

Scores therefore become fully auditable.

---

# Score Versioning

Scoring models evolve.

Atlas preserves:

* scoring model version
* assessment version
* evidence version

Historical decisions should always be reproducible using the model that existed when they were made.

---

# Extensibility

New Assessments should integrate without modifying existing Scores.

The Scoring Engine should encourage expansion through composition rather than replacement.

Future scoring domains may include:

* ESG (if user desired)
* Tax Efficiency
* Currency Exposure
* Liquidity
* Private Investments
* Real Estate

The engine should remain domain-independent.

---

# Engineering Constraints

The Scoring Engine shall:

* remain deterministic,
* remain explainable,
* remain testable,
* remain reproducible,
* preserve provenance,
* separate evidence from opinion,
* separate confidence from score,
* separate score from recommendation.

---

# Closing Reflection

A score should never end a conversation.

It should begin one.

The purpose of scoring is not to compress complexity into a number.

It is to summarize evidence while preserving the reasoning that produced it.

Atlas succeeds when users understand a score well enough to question it.

Trust is strengthened not when scores appear authoritative, but when they remain transparent, explainable, and open to examination.

That is the standard of the Atlas Scoring Engine.
