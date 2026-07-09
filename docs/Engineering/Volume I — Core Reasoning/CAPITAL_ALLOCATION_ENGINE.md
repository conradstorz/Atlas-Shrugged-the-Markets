# CAPITAL_ALLOCATION_ENGINE.md

**Project Atlas**

**Engineering Specification ESS-004**

**Status:** Draft for Founder Review
**Version:** 1.0-DRAFT
**Authority:** This document defines the Capital Allocation Engine of Atlas. It describes how Atlas represents portfolios, evaluates allocation decisions, measures concentration and diversification, and assists investors in aligning capital with purpose.

---

# Introduction

Every investment decision is ultimately a capital allocation decision.

Capital is finite.

Opportunities are infinite.

Every dollar committed to one idea cannot simultaneously support another.

The purpose of the Capital Allocation Engine is not to maximize returns.

Its purpose is to help investors allocate capital intentionally, consistently, and in alignment with their stated goals and convictions.

---

# Design Philosophy

Atlas does not optimize portfolios.

Atlas helps investors understand portfolios.

Optimization assumes a single correct answer.

Atlas recognizes that every investor possesses unique objectives, values, constraints, and time horizons.

The role of the Capital Allocation Engine is therefore to illuminate tradeoffs rather than prescribe solutions.

---

# Capital Allocation Hierarchy

Every allocation originates from purpose.

```text id="kq9v8h"
Purpose
    ↓
Goals
    ↓
Investment Policy
    ↓
Portfolio
    ↓
Allocation
    ↓
Holding
    ↓
Asset
```

Each level inherits meaning from the level above it.

---

# Purpose

Purpose belongs exclusively to the Investor.

Purpose answers:

> Why is this capital being invested?

Examples include:

* Retirement
* Financial Independence
* Income
* Wealth Preservation
* Intergenerational Transfer
* Philanthropy
* Business Liquidity
* Education

Atlas records purpose.

It never invents it.

---

# Goals

Goals translate purpose into measurable objectives.

Examples:

* Desired retirement income
* Target annual withdrawal rate
* Required dividend income
* Maximum acceptable drawdown
* Inflation protection
* Capital appreciation

Goals should remain observable and revisable.

---

# Investment Policy

Every Portfolio should possess an explicit Investment Policy.

The policy defines:

* acceptable asset classes
* allocation ranges
* diversification requirements
* liquidity needs
* tax considerations
* rebalancing philosophy
* concentration limits
* prohibited investments

The Investment Policy becomes the standard against which future decisions are evaluated.

---

# Portfolio

A Portfolio represents the current expression of the Investor's Investment Policy.

It is a snapshot.

Not an identity.

Portfolios evolve.

Purpose should remain comparatively stable.

---

# Allocation

Allocation represents intentional distribution of capital.

Allocation exists simultaneously across multiple dimensions.

Examples include:

* Asset Class
* Geography
* Sector
* Theme
* Factor
* Currency
* Risk
* Income
* Duration
* Conviction

Atlas evaluates all of these independently.

---

# Holdings

Holdings are implementation.

Allocations are intention.

Replacing one ETF with another should not necessarily alter the intended allocation.

Atlas therefore distinguishes implementation from objective.

---

# Diversification

Diversification is measured across multiple independent dimensions.

Including:

* Holdings
* Companies
* Industries
* Themes
* Factors
* Countries
* Currencies
* Income Sources
* Risk Drivers

Diversification should never be reduced to counting positions.

---

# Concentration

Concentration exists wherever dependency becomes excessive.

Atlas evaluates concentration by:

Capital

Revenue Exposure

Theme Exposure

Factor Exposure

Scenario Exposure

Counterparty Exposure

Concentration is neither inherently good nor inherently bad.

It should simply remain visible.

---

# Overlap

Overlap occurs when multiple Holdings provide substantially similar exposure.

Atlas evaluates overlap by:

Companies

Themes

Factors

Industries

Scenarios

Economic Drivers

Overlap reduces effective diversification.

Atlas measures overlap explicitly.

---

# Drift

Portfolios naturally drift as markets change.

Atlas measures drift relative to:

Investment Policy

Target Allocation

Historical Allocation

Personal Convictions

Drift should inform review rather than automatically trigger trading.

---

# Conviction

Every meaningful allocation should possess documented conviction.

Conviction is expressed by the Investor.

Not calculated by Atlas.

High conviction does not imply correctness.

It simply explains intentional concentration.

---

# Cash

Cash is an intentional allocation.

Not an absence of allocation.

Cash represents:

Liquidity

Optionality

Risk Reduction

Future Opportunity

Atlas evaluates cash as an active portfolio component.

---

# Rebalancing

Rebalancing is a strategic decision.

Not an automatic process.

Atlas identifies:

Magnitude

Direction

Causes

Tax Implications

Opportunity Cost

The Investor determines whether action is appropriate.

---

# Portfolio Health

Portfolio Health is an Assessment.

Not a Score.

Health summarizes:

Alignment

Diversification

Concentration

Resilience

Policy Compliance

Purpose Alignment

Health exists to encourage discussion rather than produce rankings.

---

# Portfolio Evolution

Portfolios represent ongoing conversations.

Every allocation change should preserve:

Reasoning

Evidence

Context

Expected Outcome

Review Date

Future investors—including the same investor years later—should understand why capital moved.

---

# Explainability

Every allocation recommendation should answer:

Why?

Compared to what?

Supported by which evidence?

Consistent with which goal?

Influenced by which assumptions?

Explainability precedes action.

---

# Engineering Constraints

The Capital Allocation Engine shall:

* separate implementation from intention,
* separate objective from recommendation,
* preserve historical allocations,
* preserve rationale,
* remain explainable,
* remain deterministic,
* remain investor-centric.

---

# Closing Reflection

A portfolio is more than a collection of investments.

It is a visible expression of an investor's beliefs, goals, priorities, and willingness to accept uncertainty.

The purpose of the Capital Allocation Engine is not to build portfolios.

Its purpose is to help investors build portfolios that faithfully reflect who they are, what they believe, and what they hope to accomplish.

Capital allocation is therefore not merely a financial activity.

It is one of the clearest expressions of long-term intention.

Atlas exists to help ensure that expression remains thoughtful, transparent, and deliberate.
