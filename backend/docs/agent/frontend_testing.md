# Frontend Testing and Debugging

## Using Playwright MCP Server

When troubleshooting HTML, CSS, and JavaScript issues in the application frontend, use the Playwright MCP server tools.

## Accessing Frontend Pages

- Navigate to `http://localhost:5000/` or the configured port
- Use `mcp__playwright__browser_navigate` to open pages
- Use `mcp__playwright__browser_snapshot` to capture the current page state
- Use `mcp__playwright__browser_console_messages` to view JavaScript console output

## Common Debugging Workflows

### HTML/CSS Issues

Use `mcp__playwright__browser_snapshot` to inspect the DOM structure and element layout.

**Example workflow:**
1. Navigate to the page with the issue
2. Take a snapshot to see current DOM structure
3. Identify the problematic elements and their classes
4. Review the corresponding SCSS/CSS files
5. Make changes and reload to verify

### JavaScript Errors

Check `mcp__playwright__browser_console_messages` for error logs and JavaScript runtime issues.

**Example workflow:**
1. Navigate to the page
2. Trigger the action that causes the error
3. Check console messages for error details
4. Review the JavaScript code in templates or static files
5. Fix the issue and verify in console

### Interactive Debugging

Use `mcp__playwright__browser_evaluate` to run JavaScript in the page context for testing and debugging.

**Example workflow:**
1. Navigate to the page
2. Use evaluate to test JavaScript expressions
3. Inspect variables, DOM elements, or test functions
4. Verify fixes by running code snippets

### Network Issues

Monitor API calls with `mcp__playwright__browser_network_requests` to debug AJAX/fetch requests.

**Example workflow:**
1. Navigate to the page
2. Trigger the network request (form submission, HTMX action, etc.)
3. Check network requests for status codes and responses
4. Verify request/response payloads
5. Debug server-side code if needed

## Tips

- Always start with a snapshot to understand the current page state
- Check console messages early to catch JavaScript errors
- Use the network monitoring for HTMX interactions
- Test across different viewport sizes for responsive issues
