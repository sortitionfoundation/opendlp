"""ABOUTME: Shared constants for the service layer.
ABOUTME: Neutral home for values used by multiple service modules."""

# When looking at respondent data and choosing columns which are reasonable to use
# as target categories (or as choice-typed schema fields), we want columns with
# not too many distinct values — every distinct value needs a category value with
# min and max. It is rare for the number of values for a single target category
# to be over 20, so we use this as a rule of thumb for columns we suggest.
MAX_DISTINCT_VALUES_FOR_AUTO_ADD = 20
