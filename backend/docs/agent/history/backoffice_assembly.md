# Backoffice Assembly Module

This document describes the Assembly management module in the backoffice UI. For component usage and design tokens, see [backoffice_design_system.md](backoffice_design_system.md).

## Overview

The Assembly module provides CRUD operations for Citizens' Assemblies through a modern UI built with Tailwind CSS, Alpine.js, and Jinja2 templates.

## Route Map

```mermaid
flowchart TD
    subgraph Dashboard
        D["/backoffice/dashboard"]
    end

    subgraph Assembly CRUD
        NEW["/backoffice/assembly/new"]
        VIEW["/backoffice/assembly/:id"]
        EDIT["/backoffice/assembly/:id/edit"]
        MEMBERS["/backoffice/assembly/:id/members"]
    end

    subgraph API Endpoints
        SEARCH["/backoffice/assembly/:id/members/search"]
        ADD["/backoffice/assembly/:id/members/add"]
        REMOVE["/backoffice/assembly/:id/members/:user_id/remove"]
    end

    D -->|"Create New Assembly"| NEW
    D -->|"Go to Assembly"| VIEW
    NEW -->|"Create"| VIEW
    VIEW -->|"Edit Assembly"| EDIT
    VIEW -->|"Team Members tab"| MEMBERS
    EDIT -->|"Save/Cancel"| VIEW
    MEMBERS -->|"Search users"| SEARCH
    MEMBERS -->|"Add user"| ADD
    MEMBERS -->|"Remove user"| REMOVE
    ADD --> MEMBERS
    REMOVE --> MEMBERS
```

## Page Hierarchy

| Page | Route | Template | Purpose |
|------|-------|----------|---------|
| Dashboard | `/backoffice/dashboard` | `dashboard.html` | List user's assemblies |
| Create Assembly | `/backoffice/assembly/new` | `create_assembly.html` | New assembly form |
| Assembly Details | `/backoffice/assembly/:id` | `assembly_details.html` | View assembly info |
| Edit Assembly | `/backoffice/assembly/:id/edit` | `edit_assembly.html` | Edit assembly form |
| Team Members | `/backoffice/assembly/:id/members` | `assembly_members.html` | Manage team members |

## Data Flow

```mermaid
sequenceDiagram
    participant Browser
    participant Route as Flask Route
    participant Service as Service Layer
    participant UoW as Unit of Work
    participant Template as Jinja Template
    participant Alpine as Alpine.js

    Browser->>Route: GET /backoffice/assembly/:id/members
    Route->>Service: get_assembly_with_permissions()
    Service->>UoW: assemblies.get(), user_assembly_roles.get()
    UoW-->>Service: Assembly + permissions
    Service-->>Route: Assembly object
    Route->>Template: render_template(assembly, users, form)
    Template-->>Browser: HTML with Alpine.js components

    Note over Browser,Alpine: User types in search dropdown
    Browser->>Alpine: x-model updates query
    Alpine->>Route: GET /members/search?q=...
    Route->>UoW: users.search_users_not_in_assembly()
    UoW-->>Route: Matching users
    Route-->>Alpine: JSON [{id, label, sublabel}]
    Alpine-->>Browser: Render dropdown results
```

## Access Control

```mermaid
flowchart LR
    subgraph Roles
        ADMIN[Global Admin]
        ORGANISER[Global Organiser]
        MANAGER[Assembly Manager]
        USER[Regular User]
    end

    subgraph Permissions
        VIEW_DASH[View Dashboard]
        CREATE[Create Assembly]
        VIEW_ASSEMBLY[View Assembly]
        EDIT[Edit Assembly]
        MANAGE_MEMBERS[Add/Remove Members]
    end

    ADMIN --> VIEW_DASH
    ADMIN --> CREATE
    ADMIN --> VIEW_ASSEMBLY
    ADMIN --> EDIT
    ADMIN --> MANAGE_MEMBERS

    ORGANISER --> VIEW_DASH
    ORGANISER --> CREATE
    ORGANISER --> VIEW_ASSEMBLY
    ORGANISER --> EDIT
    ORGANISER --> MANAGE_MEMBERS

    MANAGER --> VIEW_DASH
    MANAGER --> VIEW_ASSEMBLY
    MANAGER -.->|"own assemblies"| EDIT

    USER --> VIEW_DASH
    USER -.->|"assigned only"| VIEW_ASSEMBLY
```

| Role | Dashboard | Create | View | Edit | Manage Members |
|------|-----------|--------|------|------|----------------|
| Global Admin | ✅ All | ✅ | ✅ All | ✅ All | ✅ |
| Global Organiser | ✅ All | ✅ | ✅ All | ✅ All | ✅ |
| Assembly Manager | ✅ Assigned | ❌ | ✅ Assigned | ✅ Assigned | ❌ |
| Regular User | ✅ Assigned | ❌ | ✅ Assigned | ❌ | ❌ |

**Key rules:**
- Users only see assemblies they're assigned to (unless admin/organiser)
- Only global admins can add/remove team members
- Unauthorized access redirects to dashboard with flash message

## Tab Navigation

Assembly pages use inline tab navigation for switching between sections:

```
┌─────────────────────────────────────────────────────────┐
│  Details    │  Data & Selection  │  Team Members       │
├─────────────┴────────────────────┴─────────────────────┤
│                                                         │
│  Page content for selected tab                          │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Implementation:** Tabs are simple anchor links to separate routes (not JavaScript tabs). The active tab is highlighted based on the current URL.

```jinja
{# In assembly_details.html and assembly_members.html #}
<nav aria-label="Assembly sections">
  <a href="{{ url_for('backoffice.view_assembly', assembly_id=assembly.id) }}"
     style="{% if current_tab == 'details' %}border-bottom: 2px solid var(--color-primary-action);{% endif %}">
    Details
  </a>
  <a href="{{ url_for('backoffice.view_assembly_members', assembly_id=assembly.id) }}"
     style="{% if current_tab == 'members' %}border-bottom: 2px solid var(--color-primary-action);{% endif %}">
    Team Members
  </a>
</nav>
```

## Alpine.js Patterns

### Autocomplete Search Dropdown

The team members page uses an Alpine.js autocomplete component for searching users. This pattern separates concerns:

| Layer | File | Responsibility |
|-------|------|----------------|
| Logic | `static/backoffice/js/alpine-components.js` | Reusable `autocomplete` data component |
| Presentation | `templates/backoffice/components/search_dropdown.html` | Jinja macro wrapping the Alpine component |
| API | `routes.py` → `search_users()` | JSON endpoint returning `[{id, label, sublabel}]` |

```mermaid
flowchart LR
    subgraph Template
        MACRO[search_dropdown macro]
    end

    subgraph Alpine.js
        DATA[autocomplete data]
        STATE[query, results, isOpen]
    end

    subgraph Backend
        ROUTE[search_users route]
        REPO[users.search_users_not_in_assembly]
    end

    MACRO -->|"x-data"| DATA
    DATA -->|"fetch"| ROUTE
    ROUTE -->|"JSON"| DATA
    DATA -->|"x-model, x-show"| STATE
    ROUTE --> REPO
```

**Usage:**

```jinja
{% from "backoffice/components/search_dropdown.html" import search_dropdown %}

{{ search_dropdown(
    name="user_id",
    label="Select User",
    fetch_url=url_for('backoffice.search_users', assembly_id=assembly.id),
    placeholder="Type to search...",
    hint="Search by email or name"
) }}
```

**Component options:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `name` | required | Hidden input name for form submission |
| `fetch_url` | required | URL returning JSON array |
| `min_chars` | 2 | Minimum characters before searching |
| `debounce_ms` | 300 | Debounce delay in milliseconds |
| `param_name` | "q" | Query parameter name |

See [backoffice_design_system.md](backoffice_design_system.md) for general component documentation.

## Key Files

| Purpose | Path |
|---------|------|
| Routes | `src/opendlp/entrypoints/backoffice/routes.py` |
| Templates | `templates/backoffice/` |
| Alpine components | `static/backoffice/js/alpine-components.js` |
| Forms | `src/opendlp/entrypoints/forms.py` |
| Services | `src/opendlp/service_layer/assembly_service.py` |
| Permissions | `src/opendlp/service_layer/permissions.py` |

## Testing

BDD tests cover the assembly module in `tests/bdd/test_backoffice.py`:

- Dashboard displays assemblies
- Assembly CRUD operations
- Tab navigation
- Role-based access control (admin vs member)
- Search dropdown functionality

Run tests:
```bash
uv run pytest tests/bdd/test_backoffice.py -v
```
