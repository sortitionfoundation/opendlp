---
title: "CSV File Format"
description: "Required format for category and respondent CSV files used in selections"
---

To run a selection on OpenDLP using CSVs, the user must upload two files: one for the **categories** or targets that we will be using to select people, and one for the **respondents**, or people who have responded to register their interest.

These files should be put together by the user in a spreadsheet package of their choice, and downloaded as a .csv file format. The potential spreadsheet work is beyond the scope of this help document.

This document details the required format for these two files.

## Categories (targets)

A sample categories file is [available to download](/files/Categories_csv_example.csv). This file must conform to the following criteria:

1. There are columns headed **category**, **name**, **min** and **max**. (Other columns may be included – we recommend having a column for **Notes** where one keeps track of any key decisions to do with target-setting. However this is not mandatory)
2. The **category** column contains the name of the various stratification categories – e.g. *gender, age, ethnicity etc.* – for which we will be setting targets.
3. The **name** column contains the possible values of the various categories.
   1. E.g. for the *gender* category, in our sample file we consider values *Female, Male* and *Non-binary or other*.
   2. E.g. in our sample file we consider the age of respondents in terms of various "buckets". Hence we call this category *age\_bucket* and the possible values are *0-17, 18-24, 25-34* and so on.
   3. Note: it is vitally important that every single person in your respondents pool can be assigned exactly one of the values listed in the Categories file for each category.
4. The **min** and **max** values are numerical values which specify the minimum and maximum number of people you want to select with the given category value.
   1. E.g. For the *gender* category and the *female* value, we might set min=10 and max=11.
   2. In order for the selection to be possible:
      1. The number of people to be selected must be greater than or equal to the sum of the **min** values.
      2. The number of people to be selected must be less than or equal to the sum of the **max** values.
      3. E.g. if we say we want to select 20 people for an event, but we specify that we want **min 11 older** and **min 11 younger** people, **total min = 22**, then these numbers are in conflict with each other.
      4. Similarly, the different max and min values must not be in conflict with each other, e.g. if we say we want a total max of 25 people in the **gender** category values, and a total min of 30 people in the **age** category values, then these numbers are in conflict with each other.

## Respondents (people)

A sample respondents file is [available to download](/files/Respondents_csv_example.csv). This file must conform to the following criteria:

1. There is a column (typically the first column) which contains a unique and never-changing ID number for each respondent.
2. For each of the entries in the **category** column of the categories file, there is a column in the respondents file with that header.
   1. E.g. in the sample categories file, the category column contains five entries: *gender, age\_bucket, ethnicity, disability, colour\_bucket*. In the sample respondents file there are five columns with these headers.
3. For each column in the respondents file that corresponds to a stratification category, every single entry below the header must correspond to one of the listed values from the categories file.
   1. E.g. We saw above that our sample category file has three values for the *gender* category: *Female / Male / Non-binary or other.* If you look at column D in our sample respondents file, you will see that its header is *gender* and every entry below the header is one of *Female / Male / Non-binary or other.*
   2. E.g. Likewise in our sample category file, we had an *age\_bucket* category with values *0-17 / 18-24 / 35-34 / etc.* If you look at column K in our sample respondents file, you will see that its header is gender and every entry below the header corresponds to one of the values listed in the category file.
