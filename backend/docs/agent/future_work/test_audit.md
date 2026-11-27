# Test Audit

The overall aim is to look for tests that are not providing long term value and drop them, to limit the long term build up of test numbers and test run time.

## What to review

One angle is to look for the most expensive tests aka the ones that take the longest to run. The BDD tests are slower and cannot be run in parallel. For non-BDD tests the E2E and integration tests are slower than others. A useful argument to pytest is `--durations=50` which would report the run time of the 50 slowest tests.

Another angle is to look for tests that have only been added to ensure one particular change is done, and once the change is done the test has little value. That could be a change to text produced - human readable text, particular HTML and the like. The test does not exercise branches in the code (conditionals, loops, polymorphism etc) just that a particular change was made.

Tests that are added to ensure a database migration works are valuable ahead of the migration being run. But once the migration has run in production and the database structure has been live for a while, the migration would only ever be run again on a blank database. So detailed tests of data migrations have no value after that.

## What to do with findings

A markdown file report of the tests found that could be deleted should be written. It will be reviewed by a team member and on their instruction some or all of the tests identified may be deleted.

## Long term

It would be nice to be able to find tests that only have short term value more easily in the future. There could be a standard comment or even a pytest mark applied to those tests. Then future rounds of audit would have less searching to do.

We could also add something to the `/sf-code-review` skill to ensure all short term tests are marked with the mark.
