# OpenDLP integration with existing system

**Status:** Proposal.
_This is Hamish's view of how the system will evolve - to be reviewed by the rest of the team._

This document is to describe how OpenDLP will integrate with the existing system over the initial work. The primary focus is the GSheet - the Google spreadsheet named "Our Working Version". The Google spreadsheet for the Specification and the use of NationBuilder for registration will be covered by later work.

## Broad Outline

- Stage 1: Registrant data only in GSheet
- Stage 2: GSheet is source of truth - temporary copies of data in OpenDLP
- Stage 3: OpenDLP is source of truth - with auto-export to GSheet for missing features
- Stage 4: OpenDLP is source of truth - with manual export/import to/from GSheet

## Details

### Stage 1: Registrant data only in GSheet

In this stage, OpenDLP will run selection instead of running the "select strat" app on a laptop. This means the Delivery team just use OpenDLP for selection but otherwise their process and tools remain the same.

OpenDLP will still read from the "Our Working Version" GSheet to see the pool of registrants and create and write the selected and remaining tabs. It will **not** store the registrant data in its database or show individual registrants in the Web UI - to see them you have to look at the GSheet. It will show some summary statistics in the Web UI (as the strat app shows some stats when it does a selection.)

The "Assembly" object in OpenDLP will have a field for the URL of the "Our Working Version" GSheet.

OpenDLP selection/replacement will automate as much as possible, in particular:

- it will attempt to work out whether the selection is an initial selection or a replacement, and choose the tabs to read registrants and targets from on that basis.
- it will still be possible to change the config if required, but it should be rare.

### Stage 2: GSheet is source of truth - temporary copies of data in OpenDLP

The change from Stage 1 is that OpenDLP can show the individuals in the Web UI. That data will come from the GSheet.

To be determined: will OpenDLP store copies of user data? Maybe not at first, but it might happen before we get to Stage 3. However it will continue to pull updated data from the GSheet and _overwrite_ the local copy of the data.

### Stage 3: OpenDLP is source of truth - with auto-export to GSheet for missing features

This will wait until we can do Confirmation Calls in OpenDLP. At that point, the Delivery team will do all of Select/Confirm/Replace in OpenDLP. At this stage, the GSheet should be considered a secondary copy of the data - the primary copy is in OpenDLP.

However GSheets will still be used for some of the process. For example, the initial data will come out of NationBuilder, be put in GSheet and the derived data columns (eg. IMD from address) will be generated. Then the data, including the derived columns, can be imported into OpenDLP. But after that, selection, confirmation and replacement will be done in OpenDLP.

At this stage, it will still auto-export to the "Our Working Version" spreadsheet to allow for anything not yet supported by OpenDLP. For example, we might move to this step before the reporting is done. In that case, the old spreadsheets can generate the pie charts and report table from the exported data.

### Stage 4: OpenDLP is source of truth - with manual export/import to/from GSheet

At this point, there should be no automatic need to export to GSheet - standard reporting will be in OpenDLP. So there will be no _automatic_ export to GSheet. However OpenDLP will still support import and export to GSheet - it will just be manually run by the user. This will allow for any custom data manipulation not supported by OpenDLP itself.

How the user data gets into OpenDLP will continue to evolve. At first it will continue to come from NationBuilder, via a GSheet that creates the derived fields. And then it will be imported into OpenDLP. But we will then make OpenDLP create the derived fields, allowing direct import from NationBuilder. And then we will host the registration form on OpenDLP itself - so the data will go directly into OpenDLP.
