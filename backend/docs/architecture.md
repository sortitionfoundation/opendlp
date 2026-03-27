# OpenDLP Backend Architecture

This document provides a visual and textual overview of the Flask backend architecture, including blueprints, services, and their relationships.

## Table of Contents

- [High-Level Architecture](#high-level-architecture)
- [Blueprint Overview](#blueprint-overview)
- [Service Layer Overview](#service-layer-overview)
- [Blueprint-Service Dependencies](#blueprint-service-dependencies)
- [Detailed Blueprint Analysis](#detailed-blueprint-analysis)
- [Detailed Service Analysis](#detailed-service-analysis)
- [Developer Tools (/dev/)](#developer-tools-dev)

---

## High-Level Architecture

```mermaid
flowchart TB
    subgraph Entrypoints["Entrypoints (Blueprints)"]
        direction LR
        admin[admin]
        auth[auth]
        main[main]
        profile[profile]
        backoffice[backoffice]
        gsheets[gsheets]
        db_selection[db_selection]
        respondents[respondents]
        targets[targets]
        health[health]
    end

    subgraph Services["Service Layer"]
        direction LR
        assembly_service[assembly_service]
        user_service[user_service]
        respondent_service[respondent_service]
        sortition[sortition]
        invite_service[invite_service]
        two_factor_service[two_factor_service]
        email_confirmation_service[email_confirmation_service]
        password_reset_service[password_reset_service]
        totp_service[totp_service]
        login_rate_limit_service[login_rate_limit_service]
        permissions[permissions]
        target_checking[target_checking]
    end

    subgraph Data["Data Layer"]
        direction LR
        repositories[Repositories]
        models[SQLAlchemy Models]
        db[(PostgreSQL)]
    end

    subgraph Background["Background Tasks"]
        celery[Celery Workers]
        redis[(Redis)]
    end

    Entrypoints --> Services
    Services --> Data
    Services --> Background
    repositories --> db
    celery --> redis
```

---

## Blueprint Overview

All blueprints are located in `src/opendlp/entrypoints/blueprints/`.

```mermaid
flowchart LR
    subgraph Public["Public Routes"]
        auth["/login, /register, /logout"]
        health["/health"]
    end

    subgraph Authenticated["Authenticated Routes"]
        main["/dashboard, /assemblies/*"]
        profile["/profile/*"]
    end

    subgraph Assembly["Assembly-Scoped Routes"]
        gsheets["/assembly/*/selection, /assembly/*/replacement"]
        db_selection["/assemblies/*/db_select"]
        respondents_bp["/assemblies/*/respondents"]
        targets_bp["/assemblies/*/targets"]
    end

    subgraph Admin["Admin Routes"]
        admin["/admin/*"]
        backoffice["/backoffice/*"]
        dev["/backoffice/dev/* (dev only)"]
    end

    Public --> Authenticated
    Authenticated --> Assembly
    Authenticated --> Admin
```

### Blueprint Summary Table

| Blueprint | URL Prefix | Purpose | Auth Required | Admin Only |
|-----------|------------|---------|---------------|------------|
| `health` | `/health` | Health checks | No | No |
| `auth` | `/` | Login, register, password reset, OAuth | No | No |
| `main` | `/` | Dashboard, assembly CRUD | Yes | No |
| `profile` | `/profile` | User profile, 2FA settings | Yes | No |
| `gsheets` | `/assembly` | Google Sheets selection/replacement | Yes | No |
| `db_selection` | `/assemblies` | Database-based selection | Yes | No |
| `respondents` | `/assemblies` | Respondent management | Yes | No |
| `targets` | `/assemblies` | Target management | Yes | No |
| `admin` | `/admin` | User and invite management | Yes | Yes |
| `backoffice` | `/backoffice` | New admin interface | Yes | Yes |

---

## Service Layer Overview

All services are located in `src/opendlp/services/`.

```mermaid
flowchart TB
    subgraph Core["Core Domain Services"]
        assembly_service["assembly_service.py
        - Assembly CRUD
        - GSheet config
        - Target management
        - CSV config"]

        respondent_service["respondent_service.py
        - Respondent CRUD
        - CSV import
        - Attribute analysis"]

        sortition["sortition.py
        - Selection algorithms
        - Celery task management
        - CSV generation"]
    end

    subgraph Auth["Authentication Services"]
        user_service["user_service.py
        - User CRUD
        - Authentication
        - OAuth
        - Role management"]

        invite_service["invite_service.py
        - Invite generation
        - Invite validation
        - Batch invites"]

        two_factor_service["two_factor_service.py
        - 2FA setup/enable/disable
        - Backup codes
        - Admin 2FA management"]

        totp_service["totp_service.py
        - TOTP verification
        - Secret encryption
        - Backup code generation"]

        email_confirmation_service["email_confirmation_service.py
        - Confirmation emails
        - Token validation"]

        password_reset_service["password_reset_service.py
        - Reset tokens
        - Reset emails"]

        login_rate_limit_service["login_rate_limit_service.py
        - Rate limiting
        - Failed login tracking"]
    end

    subgraph Support["Support Services"]
        permissions["permissions.py
        - Role checks
        - Assembly access
        - Global admin checks"]

        target_checking["target_checking.py
        - Target validation
        - Detailed error reports"]

        report_translation["report_translation.py
        - Run report formatting"]
    end
```

### Service Summary Table

| Service | Primary Responsibility | Key Dependencies |
|---------|----------------------|------------------|
| `assembly_service` | Assembly CRUD, targets, CSV config | Repositories, respondent_service |
| `respondent_service` | Respondent management | Repositories |
| `sortition` | Selection/replacement tasks | Celery, Redis, assembly_service |
| `user_service` | User management, auth | Repositories, invite_service |
| `invite_service` | Invite lifecycle | Repositories |
| `two_factor_service` | 2FA management | totp_service, Repositories |
| `totp_service` | TOTP crypto operations | pyotp, cryptography |
| `email_confirmation_service` | Email verification | Email sender |
| `password_reset_service` | Password recovery | Email sender |
| `login_rate_limit_service` | Login rate limiting | Redis/DB |
| `permissions` | Authorization checks | User context |
| `target_checking` | Target validation | respondent_service |

---

## Blueprint-Service Dependencies

This diagram shows which services each blueprint depends on.

```mermaid
flowchart LR
    subgraph Blueprints
        admin_bp[admin]
        auth_bp[auth]
        main_bp[main]
        profile_bp[profile]
        backoffice_bp[backoffice]
        gsheets_bp[gsheets]
        db_selection_bp[db_selection]
        respondents_bp[respondents]
        targets_bp[targets]
    end

    subgraph Services
        assembly_svc[assembly_service]
        user_svc[user_service]
        respondent_svc[respondent_service]
        sortition_svc[sortition]
        invite_svc[invite_service]
        two_factor_svc[two_factor_service]
        email_confirm_svc[email_confirmation_service]
        password_reset_svc[password_reset_service]
        totp_svc[totp_service]
        login_rate_svc[login_rate_limit_service]
        permissions_svc[permissions]
        target_check_svc[target_checking]
    end

    admin_bp --> user_svc
    admin_bp --> invite_svc
    admin_bp --> two_factor_svc

    auth_bp --> user_svc
    auth_bp --> email_confirm_svc
    auth_bp --> password_reset_svc
    auth_bp --> login_rate_svc
    auth_bp --> totp_svc

    main_bp --> assembly_svc
    main_bp --> user_svc
    main_bp --> permissions_svc

    profile_bp --> user_svc
    profile_bp --> two_factor_svc

    backoffice_bp --> assembly_svc
    backoffice_bp --> user_svc
    backoffice_bp --> respondent_svc
    backoffice_bp --> permissions_svc

    gsheets_bp --> assembly_svc
    gsheets_bp --> sortition_svc

    db_selection_bp --> assembly_svc
    db_selection_bp --> respondent_svc
    db_selection_bp --> sortition_svc

    respondents_bp --> assembly_svc
    respondents_bp --> respondent_svc

    targets_bp --> assembly_svc
    targets_bp --> respondent_svc
    targets_bp --> target_check_svc
    targets_bp --> permissions_svc
```

### Dependency Matrix

|                  | assembly | user | respondent | sortition | invite | 2fa | email_confirm | pass_reset | totp | rate_limit | permissions | target_check |
|------------------|:--------:|:----:|:----------:|:---------:|:------:|:---:|:-------------:|:----------:|:----:|:----------:|:-----------:|:------------:|
| **admin**        |          |  ✓   |            |           |   ✓    |  ✓  |               |            |      |            |             |              |
| **auth**         |          |  ✓   |            |           |        |     |       ✓       |     ✓      |  ✓   |     ✓      |             |              |
| **main**         |    ✓     |  ✓   |            |           |        |     |               |            |      |            |      ✓      |              |
| **profile**      |          |  ✓   |            |           |        |  ✓  |               |            |      |            |             |              |
| **backoffice**   |    ✓     |  ✓   |     ✓      |           |        |     |               |            |      |            |      ✓      |              |
| **gsheets**      |    ✓     |      |            |     ✓     |        |     |               |            |      |            |             |              |
| **db_selection** |    ✓     |      |     ✓      |     ✓     |        |     |               |            |      |            |             |              |
| **respondents**  |    ✓     |      |     ✓      |           |        |     |               |            |      |            |             |              |
| **targets**      |    ✓     |      |     ✓      |           |        |     |               |            |      |            |      ✓      |      ✓       |

---

## Detailed Blueprint Analysis

### admin Blueprint

**File:** `blueprints/admin.py`

```mermaid
flowchart TB
    subgraph Routes
        dashboard["/admin/"]
        users["/admin/users"]
        user_detail["/admin/users/<id>"]
        user_edit["/admin/users/<id>/edit"]
        user_2fa["/admin/users/<id>/2fa/*"]
        invites["/admin/invites"]
        invite_detail["/admin/invites/<id>"]
    end

    subgraph Services
        user_svc[user_service]
        invite_svc[invite_service]
        two_factor_svc[two_factor_service]
    end

    dashboard --> user_svc
    users --> user_svc
    user_detail --> user_svc
    user_edit --> user_svc
    user_2fa --> two_factor_svc
    invites --> invite_svc
    invite_detail --> invite_svc
```

**Route Count:** 11 routes
**Service Dependencies:** 3 services

---

### auth Blueprint

**File:** `blueprints/auth.py`

```mermaid
flowchart TB
    subgraph Routes
        login["/login"]
        login_2fa["/login/verify-2fa"]
        logout["/logout"]
        register["/register"]
        confirm_email["/confirm-email/<token>"]
        forgot_password["/forgot-password"]
        reset_password["/reset-password/<token>"]
        google_oauth["/login/google/*"]
        microsoft_oauth["/login/microsoft/*"]
    end

    subgraph Services
        user_svc[user_service]
        email_confirm_svc[email_confirmation_service]
        password_reset_svc[password_reset_service]
        totp_svc[totp_service]
        rate_limit_svc[login_rate_limit_service]
    end

    login --> user_svc
    login --> rate_limit_svc
    login_2fa --> totp_svc
    register --> user_svc
    confirm_email --> email_confirm_svc
    forgot_password --> password_reset_svc
    reset_password --> password_reset_svc
    google_oauth --> user_svc
    microsoft_oauth --> user_svc
```

**Route Count:** 15+ routes (including OAuth variants)
**Service Dependencies:** 5 services (highest)

---

### backoffice Blueprint

**File:** `blueprints/backoffice.py`

```mermaid
flowchart TB
    subgraph Production["Production Routes"]
        dashboard["/backoffice/dashboard"]
        assembly_new["/backoffice/assembly/new"]
        assembly_view["/backoffice/assembly/<id>"]
        assembly_edit["/backoffice/assembly/<id>/edit"]
        assembly_data["/backoffice/assembly/<id>/data"]
        assembly_members["/backoffice/assembly/<id>/members"]
        showcase["/backoffice/showcase"]
    end

    subgraph Dev["Developer Routes (dev only)"]
        dev_dashboard["/backoffice/dev"]
        service_docs["/backoffice/dev/service-docs"]
        service_execute["/backoffice/dev/service-docs/execute"]
    end

    subgraph Services
        assembly_svc[assembly_service]
        user_svc[user_service]
        respondent_svc[respondent_service]
        permissions_svc[permissions]
    end

    Production --> assembly_svc
    Production --> user_svc
    Production --> respondent_svc
    Production --> permissions_svc

    Dev -.->|"testing only"| assembly_svc
    Dev -.->|"testing only"| respondent_svc
```

**Route Count:** 15+ production routes + 3 dev routes
**Service Dependencies:** 4 services

---

### gsheets Blueprint

**File:** `blueprints/gsheets.py`

```mermaid
flowchart TB
    subgraph Selection
        selection_view["/assembly/<id>/selection"]
        selection_run["POST /selection/run"]
        selection_progress["GET /selection/<run_id>/progress"]
        selection_cancel["POST /selection/<run_id>/cancel"]
    end

    subgraph Replacement
        replacement_view["/assembly/<id>/replacement"]
        replacement_run["POST /replacement/run"]
        replacement_progress["GET /replacement/<run_id>/progress"]
        replacement_cancel["POST /replacement/<run_id>/cancel"]
    end

    subgraph TabManagement
        manage_tabs["POST /manage-tabs/<run_id>"]
        tabs_progress["GET /manage-tabs/<run_id>/progress"]
    end

    subgraph GSheetConfig
        gsheet_new["/assembly/<id>/gsheet/new"]
        gsheet_edit["/assembly/<id>/gsheet/edit"]
        gsheet_remove["/assembly/<id>/gsheet/remove"]
    end

    subgraph Services
        assembly_svc[assembly_service]
        sortition_svc[sortition]
    end

    Selection --> sortition_svc
    Replacement --> sortition_svc
    TabManagement --> sortition_svc
    GSheetConfig --> assembly_svc
```

**Route Count:** 14 routes
**Service Dependencies:** 2 services

---

### db_selection Blueprint

**File:** `blueprints/db_selection.py`

```mermaid
flowchart TB
    subgraph Selection
        select_view["/assemblies/<id>/db_select"]
        select_check["POST /db_select/check"]
        select_run["POST /db_select/run"]
        select_progress["GET /db_select/<run_id>/progress"]
        select_cancel["POST /db_select/<run_id>/cancel"]
    end

    subgraph Downloads
        download_selected["GET /db_select/<run_id>/download/selected"]
        download_remaining["GET /db_select/<run_id>/download/remaining"]
    end

    subgraph Settings
        settings_view["GET /db_select/settings"]
        settings_save["POST /db_select/settings"]
        reset_respondents["POST /db_select/reset-respondents"]
    end

    subgraph Services
        assembly_svc[assembly_service]
        respondent_svc[respondent_service]
        sortition_svc[sortition]
    end

    Selection --> sortition_svc
    Downloads --> sortition_svc
    Settings --> assembly_svc
    reset_respondents --> respondent_svc
```

**Route Count:** 12 routes
**Service Dependencies:** 3 services

---

## Detailed Service Analysis

### assembly_service.py

This is the largest service, handling assembly lifecycle and related entities.

```mermaid
flowchart TB
    subgraph assembly_service
        subgraph Assembly["Assembly CRUD"]
            create_assembly
            update_assembly
            get_assembly_with_permissions
        end

        subgraph GSheet["GSheet Config"]
            add_assembly_gsheet
            update_assembly_gsheet
            remove_assembly_gsheet
            get_assembly_gsheet
        end

        subgraph Targets["Target Management"]
            get_targets_for_assembly
            import_targets_from_csv
            create_target_category
            update_target_category
            delete_target_category
            add_target_value
            update_target_value
            delete_target_value
        end

        subgraph CSV["CSV Config"]
            get_or_create_csv_config
            update_csv_config
            get_csv_upload_status
        end

        subgraph Delete["Deletion"]
            delete_targets_for_assembly
            delete_respondents_for_assembly
        end
    end

    subgraph CalledBy["Called By Blueprints"]
        main_bp[main]
        backoffice_bp[backoffice]
        gsheets_bp[gsheets]
        db_selection_bp[db_selection]
        respondents_bp[respondents]
        targets_bp[targets]
    end

    CalledBy --> assembly_service
```

**Function Count:** 20+ functions
**Potential Split Candidates:**
- Target management could be `target_service.py`
- GSheet config could be `gsheet_config_service.py`
- CSV config could be `csv_config_service.py`

---

### sortition.py

Handles all selection-related background tasks.

```mermaid
flowchart TB
    subgraph sortition
        subgraph GSheet["GSheet Tasks"]
            start_gsheet_load_task
            start_gsheet_select_task
            start_gsheet_replace_load_task
            start_gsheet_replace_task
            start_gsheet_manage_tabs_task
        end

        subgraph DB["DB Selection Tasks"]
            start_db_select_task
            check_db_selection_data
            generate_selection_csvs
        end

        subgraph Status["Task Status"]
            get_selection_run_status
            get_manage_old_tabs_status
            cancel_task
            check_and_update_task_health
            get_latest_run_for_assembly
        end
    end

    subgraph CalledBy["Called By Blueprints"]
        gsheets_bp[gsheets]
        db_selection_bp[db_selection]
    end

    subgraph External["External Dependencies"]
        celery[Celery]
        redis[Redis]
    end

    CalledBy --> sortition
    sortition --> External
```

**Function Count:** 12+ functions
**Potential Split Candidates:**
- GSheet tasks could be `gsheet_sortition.py`
- DB tasks could be `db_sortition.py`

---

### user_service.py

Handles user lifecycle and authentication.

```mermaid
flowchart TB
    subgraph user_service
        subgraph CRUD["User CRUD"]
            create_user
            get_user_by_id
            list_users_paginated
            update_user
            get_user_stats
        end

        subgraph Auth["Authentication"]
            authenticate_user
            find_or_create_oauth_user
            link_oauth_to_user
            remove_password_auth
            remove_oauth_auth
        end

        subgraph Roles["Role Management"]
            assign_assembly_role
            grant_user_assembly_role
            revoke_user_assembly_role
            get_user_assemblies
        end

        subgraph Profile["Profile"]
            update_own_profile
            change_own_password
        end

        subgraph Invite["Invite Validation"]
            validate_invite
            use_invite
            validate_and_use_invite
        end
    end
```

**Function Count:** 18+ functions
**Well-organized:** Functions are grouped by responsibility

---

## Developer Tools (/dev/)

The `/backoffice/dev/` routes provide interactive testing for the service layer.

```mermaid
flowchart TB
    subgraph DevRoutes["/backoffice/dev/*"]
        dev_dashboard["GET /dev
        Developer dashboard"]

        service_docs["GET /dev/service-docs
        Interactive documentation UI"]

        service_execute["POST /dev/service-docs/execute
        Execute service functions"]
    end

    subgraph Handlers["Internal Handlers"]
        handle_respondents["_handle_import_respondents()"]
        handle_targets["_handle_import_targets()"]
        handle_get_config["_handle_get_csv_config()"]
        handle_update_config["_handle_update_csv_config()"]
    end

    subgraph Services["Services Being Tested"]
        assembly_svc[assembly_service]
        respondent_svc[respondent_service]
    end

    subgraph Guards["Security Guards"]
        admin_check["has_global_admin()"]
        prod_check["config.is_production()"]
    end

    DevRoutes --> Guards
    Guards -->|"allowed"| Handlers
    Handlers --> Services
    Guards -->|"blocked"| return_404["Return 404"]
```

### Current /dev/ Implementation Issues

1. **Mixed Concerns:** Dev routes are in the same file as production `backoffice` routes
2. **No Separation:** Dev handlers use the same service imports as production code
3. **Limited Coverage:** Only tests a few service functions

### Recommended Structure

```
blueprints/
├── backoffice.py          # Production routes only
└── dev/                   # Development-only routes
    ├── __init__.py
    ├── dashboard.py       # /backoffice/dev
    └── service_docs.py    # /backoffice/dev/service-docs
```

---

## Observations and Recommendations

### Blueprint Observations

| Blueprint | Routes | Services | Notes |
|-----------|--------|----------|-------|
| `admin` | 11 | 3 | Well-focused |
| `auth` | 15+ | 5 | Complex but necessary |
| `main` | 10 | 3 | Could split assembly routes |
| `profile` | 15 | 2 | Well-focused |
| `backoffice` | 18+ | 4 | **Mixed prod/dev routes** |
| `gsheets` | 14 | 2 | Well-focused |
| `db_selection` | 12 | 3 | Well-focused |
| `respondents` | 3 | 2 | Small, focused |
| `targets` | 10 | 4 | Well-focused |

### Service Observations

| Service | Functions | Callers | Notes |
|---------|-----------|---------|-------|
| `assembly_service` | 20+ | 6 blueprints | **Could be split** |
| `user_service` | 18+ | 4 blueprints | Well-organized |
| `respondent_service` | 8+ | 4 blueprints | Focused |
| `sortition` | 12+ | 2 blueprints | **Could split GSheet/DB** |
| `invite_service` | 6 | 1 blueprint | Focused |
| `two_factor_service` | 7 | 2 blueprints | Focused |

### Recommendations

1. **Separate dev routes:** Extract `/backoffice/dev/*` routes into a separate blueprint module
2. **Consider splitting `assembly_service`:** Target management and CSV config are distinct concerns
3. **Consider splitting `sortition`:** GSheet and DB selection are separate workflows
4. **Standardize route patterns:** Some blueprints use `/assembly/<id>`, others use `/assemblies/<id>`
