# 1. Tech Stack Choice

Date: 2025-05-14

## Status

Accepted

## Context

What tech stack to use to build OpenDLP?

### Choices

- pattern
  - active record vs data mapper
- language and framework
  - python - type hints, not enforced
    - Django (active record, batteries included)
    - Flask (find and include the components we need) & SQLAlchemy (data mapper)
  - typescript - compile step, so types pretty strict
    - nestjs
      - typeorm can do data mapper or active record
  - golang !!
    - gives single binary to deploy
    - haven't looked into frameworks
- client stacks
  - HTMX
    - definitely start with this
  - react/next.js
    - if we want to have that as a back up option, might be nicer if using nestjs
  - CSS - bootstrap, tailwind etc

### Django vs Flask & SQLAlchemy

Django vs Flask & SQLAlchemy - or in pattern terms: (Active Record, batteries included) vs (Data Mapper, assemble your own tools)

#### Reasons for Django

- faster to get going.
- security better managed.
- set of modules designed and released together leaves less space for security holes due to components being assembled poorly.

#### Reasons for Flask & SQLAlchemy

- easier to do hexagonal architecture.
  - better for responding to change a year in.
  - mocks/test doubles easier to exclude database layer - and so tests will be a lot faster.

## Considerations

### Broader team

Some of the team know python already.

Evolving the algorithms is done with other people who know python - academics, Philipp etc.

Front end dev with typescript might be easier to find.

### Long term refactoring vs short term get going

Django and Active Record almost certainly better to get going quickly - certainly for me.

But data mapper probably better for long term. Could also be better for "Clean Architecture" - and faster tests, ports and adapters etc.

### Maintenance

Django slowly evolving, so probably less rewriting due to new releases of framework.

Nestjs sounds like it is slower than most typescript but still a risk.

Golang has reputation of evolving slower.

### Security

Django has views, database, etc integrated. It has good protections against common vulnerabilities, and being "batteries included" the way things fit together makes it hard for vulnerabilities to slip through the layers. It also has a larger team and people dedicated to ensure urgent fixes are done quickly.

Flask is smaller. There are standard add ons, but you assemble things yourself and that leaves a higher chance for a mismatch at a boundary that lets a vulnerability through. Also some of the flask add ons might be maintained by a couple of people, so fixes might be slower, and you need to track more projects.

After 3 years, funding goes. What can reasonably be maintained and kept secure after that?

### Deployment

Golang produces single binary. (But is that true with templates, CSS etc.)

Just use docker would mean that you package all the code files and templates CSS in a single place. Or deploy with ansible, uv etc.

The issue motivating this decision, and any context that influences or constrains the decision.

## Decision

### Language

Use python.

### Framework

- Use Flask & SQLAlchemy. Use the patterns from [Architecture Patterns in Python](https://www.cosmicpython.com/).
- Web page interactivity: Use HTMX rather than react/next.js.
- CSS: Bootstrap to start with.

## Consequences

### Language

- I know python - so it will be faster to develop
- others in the team know it (Nick, Brett)
- others who contribute code know it (Philipp, Paul Golz)
- types are good enough
- no concerns about speed or scaling given the site is not going to be super-high traffic

### Framework

- Flask
  - Will need to be careful to set up the security stuff - auth, sessions etc.
  - Ensure we have OWASP ZAP scanning set up before going live.
- SQLAlchemy
  - The data mapper pattern means we will start slower, but will mean we can be more flexible over the medium to long term.
- HTMX
  - should have more in one codebase - so better from a very small team point of view.
- CSS
  - Bootstrap is simpler than tailwind - no separate build step required.
