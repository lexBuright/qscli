# qsrct: Randomized trials

A command line tool to make it easy to run randomized controlled trials

## Test methodology

The command `qsrct test` tests to see your data is signficant.

I envisage this tool mostly being used for "quantified-self" type tests: small trials with one busy participiant, where the cost of the trial compared to the payoff it provides can be quite high. For these sort of trials planning a start and end date, and having a well definite experimental procedure can be difficult, and one often wants to get given a *p-value* and a confidence interval rather than decide ahead of time what your acceptance criteria are.

The temptation therefore is to continually look at your data, however, this causes problems due to *Multiple Comparison Problems*.
To deal with these we use *Bonferroni* correction and use two-tailed tests.

Bonferroni correction is at odds with the p-value approach, since it requires to decide your acceptance p-value ahead of time.
The work around here is that the "p-value* we display is the minimal *family p-value* for all the tests carried out, such that current test is significant. The reasoning being that if you are willing to accept this p-value, you are using it as your acceptance
criterion, so should have used a similar p-value for all prior tests.

This correction method means that looking at your data in quite expensive in terms off power. Particularly if you were never going to make a decision based on it anyway, you just wanted to look. However, "just looking" looking can often cease to be "just looking" after the fact.

For this purpose, we provide a *cheat p-value* which is the p-value for the individual test, which allows you to perceive statistical cost you are paying for your impatience. There is also the `--cheat` options, to run a test without updating the *bonferroni* correction if you trust your trust your own moral rectitude.

# Useful features

** The use of bonferroni correction is throwing away power, since tests

## Caveats

For complicated models you might prefer to perform the analysis yourself. For these cases the command `qsrct data` is provided.

Care must be taken around the assumptions of various models in randomized tests.

Bonferroni correction does not fully exploit the non-independence of rerunning tests after new data has been added. There
are more powerful approaches.
