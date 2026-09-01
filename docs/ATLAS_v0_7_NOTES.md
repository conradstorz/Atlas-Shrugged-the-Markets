# Atlas v0.7 Notes

Atlas v0.7 replaces guessed fund look-through with real, weighted fund look-through.

## The problem this milestone fixed

Before this milestone, look-through spread 100% of a fund's value equally across whatever
~10 symbols happened to be in its seed top-ten list. A $50,000 SCHB position was reported
as $5,000 of NVDA — one tenth of the position, in a fund that actually holds NVDA at roughly
9% and META, AMZN, and MSFT at other, different weights — while the other ~2,490 names SCHB
actually holds showed zero. The numbers looked precise. They were not; they were a fixed
1/10th split dressed up as an estimate.

## New commands

```bash
uv run atlas import-holdings SYMBOL FILE
uv run atlas coverage [--name PORTFOLIO]
```

`import-holdings` loads an issuer-published holdings-with-weights CSV for one fund.
`coverage` reports how much of the ETF universe — and, with `--name`, how much of a
portfolio's dollars — Atlas can currently model with real weights.

## What changed in the numbers

Where holdings have been imported for a fund, look-through is now exact: each underlying
company gets its real weight, not an equal share. Where holdings have not been imported,
the fund's value is excluded from the concentration table entirely and reported as
unmodeled fund value — never estimated, never guessed. A fund with no imported holdings
now contributes nothing to per-company concentration figures, on the theory that a wrong
number dressed as precise is worse than an honestly absent one.

## Coverage as a first-class output

`atlas coverage` and `atlas analyze-portfolio` both report modeled vs. unmodeled value
directly, so it's always visible how much of the picture Atlas can actually see, rather
than implying full coverage by silently filling gaps with guesses.

## Important limitation

Coverage starts at zero. The seed universe ships fund identity and top-ten *membership*
only — no weights — so until the user downloads and imports issuer holdings files with
`atlas import-holdings`, the concentration table is empty and every fund's value is
unmodeled. This is deliberate — it is the honest state, and the alternative is the bug
this milestone just fixed — but it means Atlas now shows *less* than it did before v0.7,
until real data is supplied one fund at a time.
