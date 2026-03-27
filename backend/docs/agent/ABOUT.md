# Agent Documentation

This folder contains documentation specifically for AI agents (Claude Code, etc.) working on this codebase.

## Folder Structure

```
docs/agent/
├── ABOUT.md                 # This file
├── [active-feature]/        # Active development specs (e.g., 547-component-redesign/)
├── code_quality_rules.md    # Permanent: coding standards and rules
├── frontend_design_system.md # Permanent: design system overview
├── frontend_testing.md      # Permanent: testing guidelines
├── govuk_components.md      # Permanent: GOV.UK component reference
├── migration_notes.md       # Permanent: migration guidelines
└── history/                 # Completed/merged feature specs
```

## What Goes Where

### Top Level (Always Relevant)
- **Permanent guidelines** - Coding standards, testing approaches, design system docs
- **Active feature folders** - Current development work with specs and prompts

### history/ Folder
- **Completed specs** - Feature specifications that have been implemented and merged
- **Research docs** - Investigation notes for completed features
- **Implementation plans** - Plans for features that are now done

## For AI Agents

When exploring this codebase:

1. **Read top-level files** - These contain current guidelines and standards
2. **Check active feature folders** - These are what's currently being worked on
3. **Consult history/ sparingly** - Only when you need context about past decisions or patterns

The `history/` folder exists to preserve context without cluttering your immediate focus. If you need to understand why something was built a certain way, the historical specs can help.
