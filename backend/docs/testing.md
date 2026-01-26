# Testing Strategy

OpenDLP follows a comprehensive testing approach with three levels of testing to ensure code quality and reliability.

## Testing Levels

### Unit Tests (`tests/unit/`)

**Purpose:** Test domain logic in isolation without external dependencies.

**Characteristics:**

- Test plain Python domain objects
- No database, no Flask context
- Fast execution
- Focus on business logic correctness

**Example:**

```python
# tests/unit/domain/test_user.py
def test_user_has_admin_role():
    user = User(id=uuid4(), email="admin@example.com", global_role=GlobalRole.ADMIN)
    assert user.is_admin
```

### Integration Tests (`tests/integration/`)

**Purpose:** Test database operations and service layer interactions.

**Characteristics:**

- Tests involve SQLAlchemy and database
- Uses test database fixtures
- Validates repository patterns
- Tests service layer methods

**Example:**

```python
# tests/integration/test_user_repository.py
def test_user_repository_stores_and_retrieves_user(session):
    user = User(id=uuid4(), email="test@example.com")
    repo = UserRepository(session)
    repo.add(user)
    session.commit()

    retrieved = repo.get(user.id)
    assert retrieved.email == "test@example.com"
```

### End-to-End Tests (`tests/e2e/`)

**Purpose:** Test complete user workflows through the web interface.

**Characteristics:**

- Full Flask application context
- Simulates HTTP requests
- Tests authentication flows
- Validates complete feature workflows

**Example:**

```python
# tests/e2e/test_login.py
def test_user_can_login(client, user):
    response = client.post('/login', data={
        'email': user.email,
        'password': 'test123'  # pragma: allowlist secret
    })
    assert response.status_code == 302  # Redirect after login
```

## BDD Testing

The project includes Behavior-Driven Development (BDD) tests using pytest-bdd and Playwright for end-to-end testing.

### BDD Test Structure

- **`features/`** - Gherkin feature files (.feature)
- **`tests/bdd/`** - BDD test implementation and fixtures
- **`tests/bdd/conftest.py`** - BDD-specific fixtures including server management
- **`tests/bdd/config.py`** - Test configuration (URLs, credentials)
- **`tests/bdd/shared/ui_shared.py`** - Shared step definitions

### Running BDD Tests

```bash
# Run BDD tests (shows browser)
just test-bdd

# Run BDD tests headless (for CI)
just test-bdd-headless

# Install development dependencies (including Playwright browsers)
just install-dev
```

### BDD Test Infrastructure

- Uses `FlaskTestPostgresConfig` (port 54322) for database isolation
- Auto-starts Flask test server on port 5002 (avoids conflict with dev server on 5000)
- Creates admin user and fresh database state for each test
- Service layer integration for creating test data (invites, users)
- Playwright for browser automation with cross-browser support

### Key BDD Fixtures

- `test_database` - PostgreSQL test database setup
- `test_server` - Auto-managed Flask server (session scope)
- `admin_user` - Pre-created admin user for testing
- `user_invite` - Valid invite code generated via service layer
- `clean_database` - Fresh database state per test
- `logged_in_page` - Browser page with admin user logged in

## Running Tests

```bash
# Run all tests with coverage
just test
# or: uv run python -m pytest --tb=short --cov --cov-config=pyproject.toml --cov-report=html

# Watch tests on file changes
just watch-tests

# Run specific test level
uv run pytest tests/unit/
uv run pytest tests/integration/
uv run pytest tests/e2e/
```

## Test Configuration

Test configuration is in `pyproject.toml` under the `[tool.pytest.ini_options]` section.

## Reusable Test Fixtures

The project provides standardized fixtures in `tests/conftest.py` that should be used instead of creating custom fixtures for common tasks.

### Environment Variable Fixtures

**`temp_env_vars`** - Temporarily set environment variables for a test:

```python
def test_requires_encryption_key(temp_env_vars):
    """Test that encryption requires TOTP_ENCRYPTION_KEY to be set."""
    # Set environment variable for this test only
    temp_env_vars(TOTP_ENCRYPTION_KEY="test-key-value")

    # Test code that uses the environment variable
    result = some_function_that_needs_env_var()
    assert result is not None
```

**`clear_env_vars`** - Temporarily clear environment variables for a test:

```python
def test_fails_without_required_env_var(clear_env_vars):
    """Test that function raises error when env var is missing."""
    # Clear the environment variable for this test
    clear_env_vars("TOTP_ENCRYPTION_KEY")

    # Test that missing env var causes expected error
    with pytest.raises(ValueError, match="TOTP_ENCRYPTION_KEY"):
        function_that_requires_env_var()
```

**`set_test_env`** - Automatically sets `FLASK_ENV=testing` for all tests (autouse=True).

### Database Fixtures

**For unit tests:**
- `in_memory_sqlite_db` - Fast in-memory SQLite database
- `sqlite_session_factory` - Session factory with mappers

**For integration/e2e tests:**
- `postgres_engine` - PostgreSQL test database engine (port 54322)
- `postgres_session_factory` - PostgreSQL session factory with mappers
- `postgres_session` - Individual test session with rollback

### Security Fixtures

**`patch_password_hashing`** - Speeds up password hashing in tests (autouse=True):
- Uses only 1 iteration instead of 1 million
- Makes tests run much faster
- Applied automatically to all tests

### Example: Using Fixtures for Environment-Dependent Tests

```python
def _setup_test_encryption_key(temp_env_vars):
    """Helper to set up a test encryption key."""
    raw_key = secrets.token_bytes(32)
    test_key = base64.b64encode(raw_key).decode()
    temp_env_vars(TOTP_ENCRYPTION_KEY=test_key)
    return test_key

def test_encryption_works(temp_env_vars):
    """Test that secret encryption works with valid key."""
    _setup_test_encryption_key(temp_env_vars)

    secret = "test-secret"  # pragma: allowlist secret
    encrypted = encrypt_secret(secret)

    assert encrypted != secret
    assert len(encrypted) > len(secret)

def test_encryption_fails_without_key(clear_env_vars):
    """Test that encryption fails without TOTP_ENCRYPTION_KEY."""
    clear_env_vars("TOTP_ENCRYPTION_KEY")

    with pytest.raises(ValueError, match="TOTP_ENCRYPTION_KEY"):
        encrypt_secret("test-secret")  # pragma: allowlist secret
```

### Benefits of Using Standard Fixtures

- **Consistency:** All tests use the same patterns for common tasks
- **Automatic cleanup:** Fixtures restore original state after tests
- **Readability:** Clear intent from fixture names
- **Maintainability:** Changes to test infrastructure happen in one place

### Pristine Output Policy

**All test output must be pristine to pass.**

This means:

- No warnings in test output
- No deprecation messages
- No logging pollution
- Clean, readable test results

If logs are supposed to contain errors (e.g., testing error handling), those errors must be captured and tested explicitly, not just allowed to pollute the output.

## Test Database

Integration and e2e tests use:

- **Development/Manual Testing:** PostgreSQL on port 54321
- **BDD Tests:** PostgreSQL on port 54322 (isolation from manual testing)
- **Unit Tests:** SQLite in-memory database (fast, no PostgreSQL needed)

## Writing Good Tests

### Test Naming

Use descriptive test names that explain what is being tested:

```python
# Good
def test_user_can_create_assembly_with_organiser_role():
    ...

# Bad
def test_create_assembly():
    ...
```

### Test Structure

Follow the Arrange-Act-Assert pattern:

```python
def test_user_registration_creates_user():
    # Arrange
    email = "newuser@example.com"
    password = "secure123"  # pragma: allowlist secret

    # Act
    user = register_user(email, password)

    # Assert
    assert user.email == email
    assert user.check_password(password)
```

### Test Independence

Each test should be independent and not rely on state from other tests:

```python
# Good - uses fixtures to set up state
def test_user_can_delete_assembly(user, assembly):
    delete_assembly(assembly.id, user.id)
    assert get_assembly(assembly.id) is None

# Bad - assumes assembly exists from previous test
def test_user_can_delete_assembly():
    delete_assembly("some-id", "some-user-id")  # Where did this come from?
```

## Continuous Integration

All tests are run in CI on every pull request. Tests must pass before code can be merged.

The CI pipeline:

1. Runs linting and type checking
2. Runs unit tests
3. Runs integration tests (with PostgreSQL)
4. Runs e2e tests
5. Runs BDD tests (headless mode)
6. Generates coverage reports
