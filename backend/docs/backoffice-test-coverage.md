# Backoffice Test Coverage Report

This document provides a visual overview of test coverage for the backoffice functionality, including which routes and services are covered by BDD/E2E tests.

**Reference IDs:** Each item has a unique ID (e.g., `BO-ASM-3`) for easy reference in discussions.

## Table of Contents

- [Coverage Summary](#coverage-summary)
- [User Flows (BDD Features)](#user-flows-bdd-features)
- [Route Coverage](#route-coverage)
- [Service Coverage](#service-coverage)
- [Test Type Legend](#test-type-legend)
- [Gaps and Recommendations](#gaps-and-recommendations)

---

## Coverage Summary

| Category | Covered | Partial | Not Covered | Coverage |
|----------|:-------:|:-------:|:-----------:|:--------:|
| Backoffice Routes | 14 | 3 | 2 | 74% |
| GSheets Routes | 10 | 4 | 2 | 63% |
| Dev Routes | 0 | 0 | 4 | 0% |
| assembly_service | 12 | 2 | 6 | 60% |
| respondent_service | 2 | 0 | 5 | 29% |
| user_service (backoffice) | 3 | 0 | 0 | 100% |
| sortition | 6 | 2 | 4 | 50% |

**Overall: ~60% coverage**

---

## User Flows (BDD Features)

BDD feature files describe user flows in human-readable Gherkin format. These are the primary reference for understanding what each feature should do.

| ID | Feature File | User Flow Description | Scenarios |
|----|--------------|----------------------|:---------:|
| BDD-BO | [backoffice.feature](../features/backoffice.feature) | Design system showcase, tokens, components | 8 |
| BDD-ASM | [backoffice-assembly.feature](../features/backoffice-assembly.feature) | Assembly CRUD: create, view, edit | 14 |
| BDD-MEM | [backoffice-assembly-members.feature](../features/backoffice-assembly-members.feature) | Team member management, permissions | 9 |
| BDD-GS | [backoffice-assembly-gsheet.feature](../features/backoffice-assembly-gsheet.feature) | Google Sheets configuration | 13 |
| BDD-CSV | [backoffice-csv-upload.feature](../features/backoffice-csv-upload.feature) | CSV file uploads for targets/respondents | 10 |
| BDD-SEL | [selection-history.feature](../features/selection-history.feature) | Selection run history and details | 8 |
| BDD-REP | [replacement-selection.feature](../features/replacement-selection.feature) | Replacement selection workflow | 12 |

---

## Test Type Legend

| Symbol | Meaning |
|:------:|---------|
| :white_check_mark: | Fully tested |
| :large_orange_diamond: | Partially tested |
| :x: | Not tested |
| **[H]** | Happy path test |
| **[V]** | Validation error test |
| **[P]** | Permission/auth error test |
| **[N]** | Not found error test |
| **[E]** | Edge case test |

---

## Route Coverage

### Backoffice Blueprint (`/backoffice/*`)

| ID | Route | Method | Coverage | Test Types | User Flow (BDD Scenario) |
|----|-------|:------:|:--------:|------------|--------------------------|
| BO-SC-1 | `/showcase` | GET | :white_check_mark: | [H] | [BDD-BO](../features/backoffice.feature): *"I should see Design System"* |
| BO-SC-2 | `/showcase/search-demo` | GET | :white_check_mark: | [H][E] | - |
| BO-DSH-1 | `/dashboard` | GET | :white_check_mark: | [H][P] | [BDD-ASM](../features/backoffice-assembly.feature): *"Dashboard displays create assembly button"* |
| BO-ASM-1 | `/assembly/new` | GET | :white_check_mark: | [H][P] | [BDD-ASM](../features/backoffice-assembly.feature): *"User can navigate to create assembly page"* |
| BO-ASM-2 | `/assembly/new` | POST | :white_check_mark: | [H][V][P] | [BDD-ASM](../features/backoffice-assembly.feature): *"User can create a new assembly"* |
| BO-ASM-3 | `/assembly/<id>` | GET | :white_check_mark: | [H][P][N] | [BDD-ASM](../features/backoffice-assembly.feature): *"Assembly details page displays assembly information"* |
| BO-ASM-4 | `/assembly/<id>/edit` | GET | :white_check_mark: | [H][P][N] | [BDD-ASM](../features/backoffice-assembly.feature): *"User can navigate to edit assembly"* |
| BO-ASM-5 | `/assembly/<id>/edit` | POST | :white_check_mark: | [H][V][N] | [BDD-ASM](../features/backoffice-assembly.feature): *"User can update assembly details"* |
| BO-ASM-6 | `/assembly/<id>/update-number-to-select` | POST | :x: | - | **No BDD scenario** |
| BO-DAT-1 | `/assembly/<id>/data` | GET | :white_check_mark: | [H][P][N][E] | [BDD-GS](../features/backoffice-assembly-gsheet.feature): *"User can navigate to data tab"* |
| BO-DAT-2 | `/assembly/<id>/data/upload-targets` | POST | :large_orange_diamond: | [H] | [BDD-CSV](../features/backoffice-csv-upload.feature): *"After uploading targets, People upload becomes active"* |
| BO-DAT-3 | `/assembly/<id>/data/delete-targets` | POST | :large_orange_diamond: | [H] | - |
| BO-DAT-4 | `/assembly/<id>/data/upload-respondents` | POST | :white_check_mark: | [H][V][P] | [BDD-CSV](../features/backoffice-csv-upload.feature): *"Both tabs enabled after both CSVs uploaded"* |
| BO-DAT-5 | `/assembly/<id>/data/delete-respondents` | POST | :large_orange_diamond: | [H] | - |
| BO-TGT-1 | `/assembly/<id>/targets` | GET | :x: | - | [BDD-CSV](../features/backoffice-csv-upload.feature): *"Targets page shows gsheet info"* |
| BO-RSP-1 | `/assembly/<id>/respondents` | GET | :x: | - | [BDD-CSV](../features/backoffice-csv-upload.feature): *"Respondents page shows gsheet info"* |
| BO-MEM-1 | `/assembly/<id>/members` | GET | :white_check_mark: | [H][P] | [BDD-MEM](../features/backoffice-assembly-members.feature): *"Admin can navigate to assembly members"* |
| BO-MEM-2 | `/assembly/<id>/members/add` | POST | :white_check_mark: | [H][P][V][E] | [BDD-MEM](../features/backoffice-assembly-members.feature): *"Admin can see add user form"* |
| BO-MEM-3 | `/assembly/<id>/members/<uid>/remove` | POST | :white_check_mark: | [H][P][V] | [BDD-MEM](../features/backoffice-assembly-members.feature): *"I should see remove buttons"* |
| BO-MEM-4 | `/assembly/<id>/members/search` | GET | :white_check_mark: | [H][P][E] | [BDD-MEM](../features/backoffice-assembly-members.feature): *"Search dropdown shows no results message"* |

### GSheets Blueprint (`/backoffice/*`)

| ID | Route | Method | Coverage | Test Types | User Flow (BDD Scenario) |
|----|-------|:------:|:--------:|------------|--------------------------|
| GS-SEL-1 | `/assembly/<id>/selection` | GET | :white_check_mark: | [H][P][E] | [BDD-SEL](../features/selection-history.feature): *"Selection page shows history section"* |
| GS-SEL-2 | `/assembly/<id>/selection/<run_id>` | GET | :white_check_mark: | [H][N] | [BDD-SEL](../features/selection-history.feature): *"User can view selection run details"* |
| GS-SEL-3 | `/assembly/<id>/selection/modal-progress/<run_id>` | GET | :white_check_mark: | [H][P][N][E] | - |
| GS-SEL-4 | `/assembly/<id>/selection/load` | POST | :white_check_mark: | [H][P][N] | - |
| GS-SEL-5 | `/assembly/<id>/selection/run` | POST | :white_check_mark: | [H][P][N][V][E] | - |
| GS-SEL-6 | `/assembly/<id>/selection/<run_id>/cancel` | POST | :white_check_mark: | [H][V] | - |
| GS-SEL-7 | `/assembly/<id>/selection/history/<run_id>` | GET | :large_orange_diamond: | [H] | [BDD-SEL](../features/selection-history.feature): *"History shows run status and details"* |
| GS-TAB-1 | `/assembly/<id>/manage-tabs/start-list` | POST | :x: | - | **No BDD scenario** |
| GS-TAB-2 | `/assembly/<id>/manage-tabs/start-delete` | POST | :x: | - | **No BDD scenario** |
| GS-TAB-3 | `/assembly/<id>/manage-tabs/<run_id>/progress` | GET | :large_orange_diamond: | - | - |
| GS-TAB-4 | `/assembly/<id>/manage-tabs/<run_id>/cancel` | POST | :large_orange_diamond: | - | - |
| GS-REP-1 | `/assembly/<id>/replacement` | GET | :white_check_mark: | [H] | [BDD-REP](../features/replacement-selection.feature): *"Replacement tab shows history"* |
| GS-REP-2 | `/assembly/<id>/replacement/load` | POST | :large_orange_diamond: | [H] | [BDD-REP](../features/replacement-selection.feature): *"User can start replacement validation"* |
| GS-REP-3 | `/assembly/<id>/replacement/run` | POST | :large_orange_diamond: | [H] | [BDD-REP](../features/replacement-selection.feature): *"User can run replacement selection"* |
| GS-REP-4 | `/assembly/<id>/replacement/<run_id>/cancel` | POST | :large_orange_diamond: | - | - |
| GS-REP-5 | `/assembly/<id>/selection/replacement-modal-progress/<run_id>` | GET | :x: | - | **No BDD scenario** |
| GS-CFG-1 | `/assembly/<id>/gsheet/save` | POST | :white_check_mark: | [H][V][P] | [BDD-GS](../features/backoffice-assembly-gsheet.feature): *"User can create new gsheet configuration"* |
| GS-CFG-2 | `/assembly/<id>/gsheet/delete` | POST | :white_check_mark: | [H][P][N] | [BDD-GS](../features/backoffice-assembly-gsheet.feature): *"User can delete configuration with confirmation"* |

### Dev Blueprint (`/backoffice/dev/*`)

| ID | Route | Method | Coverage | Test Types | User Flow |
|----|-------|:------:|:--------:|------------|-----------|
| DEV-1 | `/dev` | GET | :x: | - | Dev tools only |
| DEV-2 | `/dev/service-docs` | GET | :x: | - | Dev tools only |
| DEV-3 | `/dev/service-docs/execute` | POST | :x: | - | Dev tools only |
| DEV-4 | `/dev/patterns` | GET | :x: | - | Dev tools only |

> **Note:** Dev routes are only registered in non-production environments. Testing is low priority.

---

## Service Coverage

### assembly_service.py

| ID | Function | Coverage | Test Types | User Flow (BDD Scenario) |
|----|----------|:--------:|------------|--------------------------|
| SVC-ASM-1 | `create_assembly()` | :white_check_mark: | [H][V] | [BDD-ASM](../features/backoffice-assembly.feature): *"User can create a new assembly"* |
| SVC-ASM-2 | `update_assembly()` | :white_check_mark: | [H][V] | [BDD-ASM](../features/backoffice-assembly.feature): *"User can update assembly details"* |
| SVC-ASM-3 | `get_assembly_with_permissions()` | :white_check_mark: | [H][P][N] | [BDD-MEM](../features/backoffice-assembly-members.feature): *"Non-admin user without role cannot access"* |
| SVC-ASM-4 | `archive_assembly()` | :x: | - | **No user flow** |
| SVC-ASM-5 | `get_user_accessible_assemblies()` | :white_check_mark: | [H] | [BDD-ASM](../features/backoffice-assembly.feature): *"Dashboard displays create assembly button"* |
| SVC-GS-1 | `add_assembly_gsheet()` | :white_check_mark: | [H][V] | [BDD-GS](../features/backoffice-assembly-gsheet.feature): *"User can create new gsheet configuration"* |
| SVC-GS-2 | `update_assembly_gsheet()` | :white_check_mark: | [H][V] | [BDD-GS](../features/backoffice-assembly-gsheet.feature): *"User can update existing configuration"* |
| SVC-GS-3 | `remove_assembly_gsheet()` | :white_check_mark: | [H][N] | [BDD-GS](../features/backoffice-assembly-gsheet.feature): *"User can delete configuration"* |
| SVC-GS-4 | `get_assembly_gsheet()` | :white_check_mark: | [H] | [BDD-GS](../features/backoffice-assembly-gsheet.feature): *"User sees readonly view when config exists"* |
| SVC-TGT-1 | `create_target_category()` | :x: | - | **No user flow** |
| SVC-TGT-2 | `get_targets_for_assembly()` | :large_orange_diamond: | [H] | [BDD-CSV](../features/backoffice-csv-upload.feature): *"Targets page shows gsheet info"* |
| SVC-TGT-3 | `update_target_category()` | :x: | - | **No user flow** |
| SVC-TGT-4 | `delete_target_category()` | :x: | - | **No user flow** |
| SVC-TGT-5 | `import_targets_from_csv()` | :large_orange_diamond: | [H] | [BDD-CSV](../features/backoffice-csv-upload.feature): *"After uploading targets"* |
| SVC-TGT-6 | `delete_targets_for_assembly()` | :large_orange_diamond: | [H] | - |
| SVC-TGT-7 | `add_target_value()` | :x: | - | **No user flow** |
| SVC-TGT-8 | `update_target_value()` | :x: | - | **No user flow** |
| SVC-TGT-9 | `delete_target_value()` | :x: | - | **No user flow** |
| SVC-CSV-1 | `get_or_create_csv_config()` | :white_check_mark: | [H] | [BDD-CSV](../features/backoffice-csv-upload.feature): *"CSV upload section appears"* |
| SVC-CSV-2 | `update_csv_config()` | :white_check_mark: | [H] | - |
| SVC-CSV-3 | `get_csv_upload_status()` | :white_check_mark: | [H] | [BDD-CSV](../features/backoffice-csv-upload.feature): *"Both upload buttons are active initially"* |
| SVC-ASM-6 | `get_feature_collection_for_assembly()` | :x: | - | Internal to selection |

### respondent_service.py

| ID | Function | Coverage | Test Types | User Flow (BDD Scenario) |
|----|----------|:--------:|------------|--------------------------|
| SVC-RSP-1 | `create_respondent()` | :x: | - | Not exposed directly |
| SVC-RSP-2 | `import_respondents_from_csv()` | :white_check_mark: | [H][V] | [BDD-CSV](../features/backoffice-csv-upload.feature): *"Both tabs enabled after both CSVs uploaded"* |
| SVC-RSP-3 | `reset_selection_status()` | :x: | - | **No user flow** |
| SVC-RSP-4 | `get_respondents_for_assembly()` | :large_orange_diamond: | [H] | [BDD-CSV](../features/backoffice-csv-upload.feature): *"Respondents page shows gsheet info"* |
| SVC-RSP-5 | `count_non_pool_respondents()` | :x: | - | **No user flow** |
| SVC-RSP-6 | `get_respondent_attribute_columns()` | :x: | - | **No user flow** |
| SVC-RSP-7 | `get_respondent_attribute_value_counts()` | :x: | - | **No user flow** |

### user_service.py (Backoffice Functions)

| ID | Function | Coverage | Test Types | User Flow (BDD Scenario) |
|----|----------|:--------:|------------|--------------------------|
| SVC-USR-1 | `get_user_assemblies()` | :white_check_mark: | [H] | [BDD-ASM](../features/backoffice-assembly.feature): *"Dashboard displays create assembly button"* |
| SVC-USR-2 | `grant_user_assembly_role()` | :white_check_mark: | [H][P][V] | [BDD-MEM](../features/backoffice-assembly-members.feature): *"Admin can see add user form"* |
| SVC-USR-3 | `revoke_user_assembly_role()` | :white_check_mark: | [H][P][V] | [BDD-MEM](../features/backoffice-assembly-members.feature): *"I should see remove buttons"* |

### sortition.py

| ID | Function | Coverage | Test Types | User Flow (BDD Scenario) |
|----|----------|:--------:|------------|--------------------------|
| SVC-SRT-1 | `start_gsheet_load_task()` | :white_check_mark: | [H][N][P] | - |
| SVC-SRT-2 | `start_gsheet_select_task()` | :white_check_mark: | [H][V][N] | - |
| SVC-SRT-3 | `start_gsheet_replace_load_task()` | :large_orange_diamond: | [H] | [BDD-REP](../features/replacement-selection.feature): *"User can start replacement validation"* |
| SVC-SRT-4 | `start_gsheet_replace_task()` | :large_orange_diamond: | [H] | [BDD-REP](../features/replacement-selection.feature): *"User can run replacement selection"* |
| SVC-SRT-5 | `start_gsheet_manage_tabs_task()` | :x: | - | **No user flow** |
| SVC-SRT-6 | `get_selection_run_status()` | :white_check_mark: | [H][N] | [BDD-SEL](../features/selection-history.feature): *"History shows run status"* |
| SVC-SRT-7 | `cancel_task()` | :white_check_mark: | [H][V] | - |
| SVC-SRT-8 | `check_and_update_task_health()` | :white_check_mark: | [H] | - |
| SVC-SRT-9 | `get_manage_old_tabs_status()` | :x: | - | **No user flow** |
| SVC-SRT-10 | `check_db_selection_data()` | :x: | - | Not used in backoffice |
| SVC-SRT-11 | `start_db_select_task()` | :x: | - | Not used in backoffice |
| SVC-SRT-12 | `generate_selection_csvs()` | :x: | - | Not used in backoffice |

---

## Detailed Test Inventory

### BDD Scenarios by Feature

#### [backoffice-assembly.feature](../features/backoffice-assembly.feature) (BDD-ASM)

| ID | Scenario | Type | Routes Covered |
|----|----------|:----:|----------------|
| BDD-ASM-1 | User can navigate to assembly details from dashboard | [H] | GET /dashboard, GET /assembly/<id> |
| BDD-ASM-2 | Assembly details page displays breadcrumbs | [H] | GET /assembly/<id> |
| BDD-ASM-3 | Assembly details page displays assembly information | [H] | GET /assembly/<id> |
| BDD-ASM-4 | Assembly details page has edit button | [H] | GET /assembly/<id> |
| BDD-ASM-5 | User can navigate to edit assembly from details page | [H] | GET /assembly/<id>/edit |
| BDD-ASM-6 | Edit assembly page displays breadcrumbs | [H] | GET /assembly/<id>/edit |
| BDD-ASM-7 | Edit assembly page displays form fields | [H] | GET /assembly/<id>/edit |
| BDD-ASM-8 | Edit assembly page has save and cancel buttons | [H] | GET /assembly/<id>/edit |
| BDD-ASM-9 | User can update assembly details | [H] | POST /assembly/<id>/edit |
| BDD-ASM-10 | Dashboard displays create assembly button | [H] | GET /dashboard |
| BDD-ASM-11 | User can navigate to create assembly page from dashboard | [H] | GET /assembly/new |
| BDD-ASM-12 | Create assembly page displays breadcrumbs | [H] | GET /assembly/new |
| BDD-ASM-13 | Create assembly page displays form fields | [H] | GET /assembly/new |
| BDD-ASM-14 | User can create a new assembly | [H] | POST /assembly/new |
| BDD-ASM-15 | Empty state shows create assembly button | [H][E] | GET /dashboard |

#### [backoffice-assembly-members.feature](../features/backoffice-assembly-members.feature) (BDD-MEM)

| ID | Scenario | Type | Routes Covered |
|----|----------|:----:|----------------|
| BDD-MEM-1 | Admin can navigate to assembly members from details page | [H] | GET /members |
| BDD-MEM-2 | Assembly members page displays breadcrumbs | [H] | GET /members |
| BDD-MEM-3 | Admin can see add user form on members page | [H] | GET /members |
| BDD-MEM-4 | Admin can see team members table when members exist | [H] | GET /members |
| BDD-MEM-5 | Non-admin member can view members page | [H][P] | GET /members |
| BDD-MEM-6 | Non-admin member cannot see add user form | [P] | GET /members |
| BDD-MEM-7 | Search dropdown shows no results message | [H][E] | GET /members/search |
| BDD-MEM-8 | Non-admin user without role cannot see assembly | [P] | GET /dashboard |
| BDD-MEM-9 | Non-admin user without role cannot access assembly | [P] | GET /assembly/<id>, GET /members |

#### [backoffice-assembly-gsheet.feature](../features/backoffice-assembly-gsheet.feature) (BDD-GS)

| ID | Scenario | Type | Routes Covered |
|----|----------|:----:|----------------|
| BDD-GS-1 | User can navigate to data tab from assembly details | [H] | GET /data |
| BDD-GS-2 | Data source selector is shown when no config exists | [H] | GET /data |
| BDD-GS-3 | User can select Google Spreadsheet data source | [H] | GET /data |
| BDD-GS-4 | User can create new gsheet configuration | [H] | POST /gsheet/save |
| BDD-GS-5 | Form shows validation errors for missing URL | [V] | POST /gsheet/save |
| BDD-GS-6 | Form shows validation errors for invalid URL | [V] | POST /gsheet/save |
| BDD-GS-7 | User sees readonly view when config exists | [H] | GET /data |
| BDD-GS-8 | User can click Edit to switch to edit mode | [H] | GET /data |
| BDD-GS-9 | User can update existing configuration | [H] | POST /gsheet/save |
| BDD-GS-10 | User can cancel edit and return to view mode | [H] | GET /data |
| BDD-GS-11 | Data source selector is locked when config exists | [H] | GET /data |
| BDD-GS-12 | User can delete configuration with confirmation | [H] | POST /gsheet/delete |
| BDD-GS-13 | After delete data source selector is unlocked | [H] | POST /gsheet/delete |

#### [backoffice-csv-upload.feature](../features/backoffice-csv-upload.feature) (BDD-CSV)

| ID | Scenario | Type | Routes Covered |
|----|----------|:----:|----------------|
| BDD-CSV-1 | Targets and Respondents tabs are always visible | [H] | GET /assembly/<id> |
| BDD-CSV-2 | Targets tab is disabled when no data source | [H] | GET /data |
| BDD-CSV-3 | Targets and Respondents tabs enabled when gsheet configured | [H] | GET /assembly/<id> |
| BDD-CSV-4 | Targets page shows gsheet info | [H] | GET /targets |
| BDD-CSV-5 | Respondents page shows gsheet info | [H] | GET /respondents |
| BDD-CSV-6 | Targets tab disabled for CSV until targets uploaded | [H] | GET /data |
| BDD-CSV-7 | CSV upload section appears when CSV selected | [H] | GET /data |
| BDD-CSV-8 | Both Target and People upload buttons active initially | [H] | GET /data |
| BDD-CSV-9 | After uploading targets, People upload becomes active | [H] | POST /upload-targets |
| BDD-CSV-10 | Both tabs enabled after both CSVs uploaded | [H] | POST /upload-respondents |

### E2E Tests by File

#### test_backoffice_general.py

| ID | Test Class | Test Method | Type | Route |
|----|------------|-------------|:----:|-------|
| E2E-GEN-1 | TestBackofficeDashboard | test_dashboard_loads_for_logged_in_user | [H] | GET /dashboard |
| E2E-GEN-2 | | test_dashboard_redirects_when_not_logged_in | [P] | GET /dashboard |
| E2E-GEN-3 | | test_dashboard_shows_existing_assemblies | [H] | GET /dashboard |
| E2E-GEN-4 | | test_dashboard_accessible_to_regular_users | [H] | GET /dashboard |
| E2E-GEN-5 | TestBackofficeShowcase | test_showcase_page_loads | [H] | GET /showcase |
| E2E-GEN-6 | | test_search_demo_returns_empty_for_no_query | [E] | GET /showcase/search-demo |
| E2E-GEN-7 | | test_search_demo_returns_mock_results | [H] | GET /showcase/search-demo |
| E2E-GEN-8 | TestBackofficeAssemblyDataPage | test_data_page_loads_successfully | [H] | GET /data |
| E2E-GEN-9 | | test_data_page_with_gsheet_source_parameter | [H] | GET /data?source=gsheet |
| E2E-GEN-10 | | test_data_page_with_csv_source_parameter | [H] | GET /data?source=csv |
| E2E-GEN-11 | | test_data_page_invalid_source_parameter_ignored | [E] | GET /data?source=invalid |
| E2E-GEN-12 | | test_data_page_redirects_when_not_logged_in | [P] | GET /data |
| E2E-GEN-13 | | test_data_page_nonexistent_assembly | [N] | GET /data |
| E2E-GEN-14 | TestBackofficeDataSourceLocking | test_data_source_locked_when_gsheet_config_exists | [H] | GET /data |
| E2E-GEN-15 | | test_data_source_auto_selects_gsheet | [H] | GET /data |
| E2E-GEN-16 | | test_data_source_unlocked_when_no_config | [H] | GET /data |
| E2E-GEN-17 | | test_data_source_unlocked_after_delete | [H] | GET /data |
| E2E-GEN-18 | | test_gsheet_selected_shows_in_dropdown | [H] | GET /data |

#### test_backoffice_assembly.py

| ID | Test Class | Test Method | Type | Route |
|----|------------|-------------|:----:|-------|
| E2E-ASM-1 | TestBackofficeAssemblyDetails | test_view_assembly_details_page_loads | [H] | GET /assembly/<id> |
| E2E-ASM-2 | | test_view_assembly_redirects_when_not_logged_in | [P] | GET /assembly/<id> |
| E2E-ASM-3 | | test_view_nonexistent_assembly_redirects | [N] | GET /assembly/<id> |
| E2E-ASM-4 | | test_view_assembly_shows_key_fields | [H] | GET /assembly/<id> |
| E2E-ASM-5 | | test_view_assembly_permission_denied | [P] | GET /assembly/<id> |
| E2E-ASM-6 | TestBackofficeAssemblyCreate | test_create_assembly_get_form | [H] | GET /assembly/new |
| E2E-ASM-7 | | test_create_assembly_success | [H] | POST /assembly/new |
| E2E-ASM-8 | | test_create_assembly_minimal_data | [H] | POST /assembly/new |
| E2E-ASM-9 | | test_create_assembly_validation_errors | [V] | POST /assembly/new |
| E2E-ASM-10 | | test_create_assembly_redirects_when_not_logged_in | [P] | GET /assembly/new |
| E2E-ASM-11 | | test_create_assembly_appears_in_dashboard | [H] | Workflow |
| E2E-ASM-12 | TestBackofficeAssemblyEdit | test_edit_assembly_get_form | [H] | GET /assembly/<id>/edit |
| E2E-ASM-13 | | test_edit_assembly_success | [H] | POST /assembly/<id>/edit |
| E2E-ASM-14 | | test_edit_assembly_validation_errors | [V] | POST /assembly/<id>/edit |
| E2E-ASM-15 | | test_edit_nonexistent_assembly | [N] | GET /assembly/<id>/edit |
| E2E-ASM-16 | | test_edit_assembly_redirects_when_not_logged_in | [P] | GET /assembly/<id>/edit |
| E2E-ASM-17 | | test_complete_create_view_edit_workflow | [H] | Workflow |
| E2E-MEM-1 | TestBackofficeAssemblyMembers | test_members_page_loads | [H] | GET /members |
| E2E-MEM-2 | | test_members_page_redirects_when_not_logged_in | [P] | GET /members |
| E2E-MEM-3 | | test_members_search_returns_json | [H] | GET /members/search |
| E2E-MEM-4 | TestBackofficeAddUserToAssembly | test_add_user_to_assembly_success | [H] | POST /members/add |
| E2E-MEM-5 | | test_add_user_shows_success_message | [H] | POST /members/add |
| E2E-MEM-6 | | test_add_user_with_manager_role | [H] | POST /members/add |
| E2E-MEM-7 | | test_add_user_not_accessible_to_regular_user | [P] | POST /members/add |
| E2E-MEM-8 | | test_add_user_with_invalid_user_id | [V] | POST /members/add |
| E2E-MEM-9 | | test_add_user_sends_notification_email | [H] | POST /members/add |
| E2E-MEM-10 | TestBackofficeRemoveUserFromAssembly | test_remove_user_from_assembly_success | [H] | POST /members/remove |
| E2E-MEM-11 | | test_remove_user_shows_success_message | [H] | POST /members/remove |
| E2E-MEM-12 | | test_remove_user_not_accessible_to_regular_user | [P] | POST /members/remove |
| E2E-MEM-13 | | test_remove_user_with_invalid_user_id | [V] | POST /members/remove |
| E2E-MEM-14 | TestBackofficeSearchUsers | test_search_users_returns_matching_users | [H] | GET /members/search |
| E2E-MEM-15 | | test_search_users_excludes_already_added | [H] | GET /members/search |
| E2E-MEM-16 | | test_search_users_empty_query | [E] | GET /members/search |
| E2E-MEM-17 | | test_search_users_case_insensitive | [E] | GET /members/search |
| E2E-MEM-18 | | test_search_users_by_email | [H] | GET /members/search |
| E2E-MEM-19 | | test_search_users_by_last_name | [H] | GET /members/search |
| E2E-MEM-20 | | test_search_users_not_accessible_to_regular_user | [P] | GET /members/search |
| E2E-MEM-21 | | test_search_users_no_matches | [E] | GET /members/search |
| E2E-CSV-1 | TestBackofficeCsvUpload | test_upload_respondents_with_id_column | [H] | POST /upload-respondents |
| E2E-CSV-2 | | test_upload_respondents_without_id_column | [H] | POST /upload-respondents |
| E2E-CSV-3 | | test_upload_respondents_invalid_id_column | [V] | POST /upload-respondents |
| E2E-CSV-4 | | test_upload_respondents_shows_success | [H] | POST /upload-respondents |
| E2E-CSV-5 | | test_upload_respondents_redirects_when_not_logged_in | [P] | POST /upload-respondents |

#### test_backoffice_gsheet_selection.py

| ID | Test Class | Test Method | Type | Route |
|----|------------|-------------|:----:|-------|
| E2E-GS-1 | TestBackofficeGSheetConfigForm | test_form_shows_new_mode | [H] | GET /data?source=gsheet |
| E2E-GS-2 | | test_form_contains_required_fields | [H] | GET /data?source=gsheet |
| E2E-GS-3 | | test_form_shows_view_mode | [H] | GET /data?source=gsheet |
| E2E-GS-4 | | test_form_shows_edit_mode | [H] | GET /data?mode=edit |
| E2E-GS-5 | | test_form_shows_default_values | [H] | GET /data?source=gsheet |
| E2E-GS-6 | TestBackofficeGSheetFormSubmission | test_create_gsheet_config_success | [H] | POST /gsheet/save |
| E2E-GS-7 | | test_create_validation_error_missing_url | [V] | POST /gsheet/save |
| E2E-GS-8 | | test_create_validation_error_invalid_url | [V] | POST /gsheet/save |
| E2E-GS-9 | | test_update_gsheet_config_success | [H] | POST /gsheet/save |
| E2E-GS-10 | | test_update_with_team_eu | [H] | POST /gsheet/save |
| E2E-GS-11 | | test_update_with_custom_team | [H] | POST /gsheet/save |
| E2E-GS-12 | | test_update_validation_error | [V] | POST /gsheet/save |
| E2E-GS-13 | | test_warning_empty_columns_to_keep | [H] | POST /gsheet/save |
| E2E-GS-14 | | test_no_warning_empty_columns_with_team | [H] | POST /gsheet/save |
| E2E-GS-15 | | test_permission_denied_regular_user | [P] | POST /gsheet/save |
| E2E-GS-16 | | test_redirects_when_not_logged_in | [P] | POST /gsheet/save |
| E2E-GS-17 | TestBackofficeGSheetValidation | test_hard_validation_address_check | [V] | POST /gsheet/save |
| E2E-GS-18 | | test_hard_validation_passes_with_team | [H] | POST /gsheet/save |
| E2E-GS-19 | | test_hard_validation_passes_no_address | [H] | POST /gsheet/save |
| E2E-GS-20 | | test_hard_validation_on_edit | [H] | POST /gsheet/save |
| E2E-GS-21 | | test_url_validation_enforced | [V] | POST /gsheet/save |
| E2E-GS-22 | TestBackofficeGSheetDelete | test_delete_gsheet_config_success | [H] | POST /gsheet/delete |
| E2E-GS-23 | | test_delete_gsheet_not_found | [N] | POST /gsheet/delete |
| E2E-GS-24 | | test_delete_button_shown_view_mode | [H] | GET /data |
| E2E-GS-25 | | test_delete_button_shown_edit_mode | [H] | GET /data?mode=edit |
| E2E-GS-26 | | test_delete_button_not_shown_new | [H] | GET /data |
| E2E-GS-27 | | test_delete_permission_denied | [P] | POST /gsheet/delete |
| E2E-GS-28 | | test_delete_redirects_not_logged_in | [P] | POST /gsheet/delete |
| E2E-GS-29 | | test_gsheet_state_transitions | [H] | Workflow |
| E2E-SEL-1 | TestBackofficeSelectionTab | test_selection_page_loads_without_gsheet | [H] | GET /selection |
| E2E-SEL-2 | | test_selection_page_loads_with_gsheet | [H] | GET /selection |
| E2E-SEL-3 | | test_selection_page_redirects_not_logged_in | [P] | GET /selection |
| E2E-SEL-4 | | test_selection_load_starts_task | [H] | POST /selection/load |
| E2E-SEL-5 | | test_selection_load_redirects_not_logged_in | [P] | POST /selection/load |
| E2E-SEL-6 | | test_selection_run_starts_task | [H] | POST /selection/run |
| E2E-SEL-7 | | test_selection_run_redirects_not_logged_in | [P] | POST /selection/run |
| E2E-SEL-8 | | test_selection_run_test_mode | [H] | POST /selection/run |
| E2E-SEL-9 | | test_selection_run_not_found | [N] | POST /selection/run |
| E2E-SEL-10 | | test_selection_run_invalid_selection | [V] | POST /selection/run |
| E2E-SEL-11 | | test_selection_progress_modal_returns_html | [H] | GET /modal-progress |
| E2E-SEL-12 | | test_selection_cancel | [H] | POST /cancel |
| E2E-SEL-13 | | test_selection_load_not_found | [N] | POST /selection/load |
| E2E-SEL-14 | | test_selection_load_insufficient_permissions | [P] | POST /selection/load |
| E2E-SEL-15 | | test_selection_with_run_redirects | [H] | GET /selection/<run_id> |
| E2E-SEL-16 | | test_selection_with_current_selection_param | [H] | GET /selection?current_selection= |
| E2E-SEL-17 | | test_selection_with_run_not_found | [N] | GET /selection |
| E2E-SEL-18 | | test_view_run_details_exists | [H] | GET /history/<run_id> |
| E2E-SEL-19 | | test_selection_page_shows_history | [H] | GET /selection |
| E2E-SEL-20 | | test_progress_modal_not_found | [N] | GET /modal-progress |
| E2E-SEL-21 | | test_progress_modal_permission_denied | [P] | GET /modal-progress |
| E2E-SEL-22 | | test_progress_modal_no_polling_completed | [E] | GET /modal-progress |
| E2E-SEL-23 | | test_progress_modal_no_polling_failed | [E] | GET /modal-progress |
| E2E-SEL-24 | | test_progress_modal_ownership_validation | [H] | GET /modal-progress |
| E2E-SEL-25 | | test_selection_with_current_renders_modal | [H] | GET /selection |
| E2E-SEL-26 | | test_cancel_invalid_selection_error | [V] | POST /cancel |

---

## Gaps and Recommendations

### Critical Gaps (High Priority)

| ID | Gap | Impact | Recommendation |
|----|-----|--------|----------------|
| GAP-1 | Target category CRUD not tested (SVC-TGT-1,3,4) | Cannot verify target management | Add E2E tests for create/update/delete |
| GAP-2 | Target value CRUD not tested (SVC-TGT-7,8,9) | Cannot verify target values | Add E2E tests for value management |
| GAP-3 | Manage tabs not tested (GS-TAB-1,2) | Cannot verify tab cleanup | Add E2E tests for manage tabs workflow |
| GAP-4 | Replacement workflow limited (GS-REP-2,3,4) | May have bugs in replacement | Expand replacement tests |

### Medium Priority Gaps

| ID | Gap | Impact | Recommendation |
|----|-----|--------|----------------|
| GAP-5 | BO-ASM-6 `update-number-to-select` not tested | Possible regression risk | Add test for HTMX endpoint |
| GAP-6 | BO-TGT-1, BO-RSP-1 view pages not tested | Rendering issues undetected | Add basic render tests |
| GAP-7 | SVC-RSP-5,6,7 respondent attribute functions | Attribute handling issues | Add service-level tests |
| GAP-8 | Large CSV handling | Performance issues undetected | Add load tests |

### Low Priority Gaps

| ID | Gap | Impact | Recommendation |
|----|-----|--------|----------------|
| GAP-9 | DEV-1 to DEV-4 not tested | Dev-only, low risk | Optional: add basic tests |
| GAP-10 | Edge cases (special chars) | Rare issues | Add as regression tests when found |
| GAP-11 | Concurrent operations | Race conditions | Add integration tests |

---

## Test Statistics

```
Total E2E Test Methods: ~117
Total BDD Scenarios: ~74
Total Routes Tested: 34/44 (77%)
Total Service Functions Tested: 26/40 (65%)

Test Type Distribution:
  Happy Path [H]: ~70 tests (60%)
  Permission [P]: ~25 tests (21%)
  Validation [V]: ~15 tests (13%)
  Not Found [N]: ~10 tests (9%)
  Edge Case [E]: ~12 tests (10%)
```

---

## Quick Reference

**ID Prefixes:**
- `BO-` = Backoffice routes
- `GS-` = GSheets routes
- `DEV-` = Dev routes
- `SVC-` = Service functions
- `BDD-` = BDD scenarios
- `E2E-` = E2E test methods
- `GAP-` = Coverage gaps

**Feature Codes:**
- `ASM` = Assembly
- `MEM` = Members
- `DAT` = Data
- `TGT` = Targets
- `RSP` = Respondents
- `CSV` = CSV upload
- `SEL` = Selection
- `REP` = Replacement
- `TAB` = Manage tabs
- `CFG` = GSheet config
- `GEN` = General
- `SC` = Showcase
- `DSH` = Dashboard
- `SRT` = Sortition
- `USR` = User service

---

*Last updated: 2026-03-27*
