# OpenDLP

OpenDLP is the Open Democratic Lottery Platform. A web platform for running the two-stage democratic lottery process for [Citizens' Assemblies](https://en.wikipedia.org/wiki/Citizens%27_assembly) and other deliberative mini-publics:

- The first stage is "invitation by lottery". Selecting people to invite from a population. This could be selecting addresses, selecting people from a database, selecting points on a map to go door knocking or various other options. The people are then sent an invite to register their interest, say via a web form or phone service.
- The second stage is "selection of participants by lottery". This picks from the pool of people who have registered interest. This is normally stratified with targets - say roughly half men and half women, so much in age brackets etc. This process is sometimes called "sortition". You can read more in the [sortition algorithms library docs](https://sortitionfoundation.github.io/sortition-algorithms/concepts/).
  - Sortition creates representative groups by randomly selecting people while respecting demographic quotas. For example, if your population is 52% women and 48% men, sortition ensures your panel maintains similar proportions rather than risking an all-male or all-female selection through pure chance.

## About

**Purpose:** A web application to support finding representative samples of people to participate in Citizens' Assemblies through a two stage Democratic Lottery.

### Key Features

- Specifying the Assembly.
- Support multiple methods of location selection.
- Creating and hosting a Registration page for invitees to sign up on.
- Doing the second stage of the democratic lottery over the set of invitees who signed up.
- Managing the confirmation process.

### Who is behind this

The [Sortition Foundation](https://www.sortitionfoundation.org/) is developing this, and welcomes open source contributions.

## Guide to the repo

We have started with a [backend](backend/) directory, containing the backend web app. So far we have no separate front end web app, but this structure allows us to add other projects to this monorepo as the project evolves.

### Docs

The [docs](backend/docs/) folder has lots of info in it.

### Deployment

Will write this when we can do it.

### Development

The [AGENTS.md](backend/AGENTS.md) file has good info for developers.
