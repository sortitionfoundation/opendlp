# Google OAuth Setup

This guide explains how to configure Google OAuth authentication for OpenDLP, allowing users to sign in and register using their Google accounts.

## Overview

Google OAuth integration provides:

- **Sign in with Google**: Users can authenticate using their existing Google accounts
- **Register with Google**: New users can create OpenDLP accounts using Google authentication (still requires an invite code)
- **Account linking**: Users with existing password-based accounts can link their Google account for additional authentication flexibility
- **Multiple authentication methods**: Users can maintain both password and Google OAuth authentication simultaneously

## Prerequisites

- A Google Cloud Project (or ability to create one)
- Admin access to the Google Cloud Console
- Your OpenDLP instance's public URL (for configuring redirect URIs)

## Step 1: Create or Select a Google Cloud Project

You can create a new project or use an existing one.

### Using the Web Console

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Click on the project dropdown in the top navigation bar (or press `Ctrl-O`)
3. Either:
   - Select an existing project
   - Click "New Project" to create one

### Using gcloud CLI

```sh
# List existing projects
gcloud projects list

# Create a new project
gcloud projects create [PROJECT_ID] --name="OpenDLP OAuth"

# Switch to the project
gcloud config set project [PROJECT_ID]

# Confirm
gcloud config list
```

## Step 2: Configure OAuth Consent Screen

Before creating credentials, you must configure the OAuth consent screen.

1. Go to [APIs & Services > OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent)
2. Choose user type:
   - **Internal**: Only users within your Google Workspace organization can authenticate (recommended for organizational deployments)
   - **External**: Any Google account can authenticate (required for public instances)
3. Click "Create"
4. Fill in the required information:
   - **App name**: OpenDLP (or your organization's name)
   - **User support email**: Your support email address
   - **Developer contact information**: Your admin email address
5. Click "Save and Continue"
6. **Scopes**: Under "Data Access", click "Add or Remove Scopes"
   - Select these three scopes:
     - `openid`
     - `email` (`.../auth/userinfo.email`)
     - `profile` (`.../auth/userinfo.profile`)
   - These are all "non-sensitive" scopes and don't require app verification
7. Click "Save and Continue"
8. Review and click "Back to Dashboard"

**Note**: If you selected "External" user type, your app will start in "Testing" mode. For production use with external users, you'll need to publish the app (click "Publish App" on the OAuth consent screen page). Apps with only non-sensitive scopes don't require Google verification.

## Step 3: Create OAuth 2.0 Credentials

1. Go to [APIs & Services > Credentials](https://console.cloud.google.com/apis/credentials)
2. Click "Create Credentials" > "OAuth client ID"
3. Select Application type: **Web application**
4. Enter a name: "OpenDLP" (or something descriptive)
5. Under "Authorized redirect URIs", add your callback URLs:
   - For production: `https://yourdomain.com/auth/login/google/callback`
   - For production (account linking): `https://yourdomain.com/profile/link-google/callback`
   - For local development: `http://localhost:5000/auth/login/google/callback`
   - For local development (account linking): `http://localhost:5000/profile/link-google/callback`

   **Important**: The redirect URIs must exactly match the URLs your application uses. Include both login and profile linking callbacks.

6. Click "Create"
7. A dialog will appear showing your **Client ID** and **Client Secret**
8. **Save these credentials securely** - you'll need them to configure OpenDLP

## Step 4: Configure OpenDLP

Add the OAuth credentials to your OpenDLP configuration.

### Using Environment Variables

Set these environment variables in your deployment:

```bash
OAUTH_GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com"
OAUTH_GOOGLE_CLIENT_SECRET="your-client-secret"  # pragma: allowlist secret
```

### Using .env File (Development)

For local development, add these to your `.env` file:

```bash
# Google OAuth
OAUTH_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
OAUTH_GOOGLE_CLIENT_SECRET=your-client-secret
```

**Security Warning**: Never commit `.env` files or OAuth secrets to version control.

### Using Docker Compose

Add the environment variables to your `docker-compose.yml`:

```yaml
services:
  web:
    environment:
      - OAUTH_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
      - OAUTH_GOOGLE_CLIENT_SECRET=your-client-secret
```

Or use an environment file:

```yaml
services:
  web:
    env_file:
      - .env
```

## Step 5: Restart OpenDLP

After configuring the credentials, restart your OpenDLP application to load the new configuration:

```bash
# Docker Compose
docker-compose restart web

# Systemd service
sudo systemctl restart opendlp

# Local development
# Stop the Flask dev server (Ctrl-C) and restart with:
just run
```

## Step 6: Verify the Setup

1. Navigate to your OpenDLP instance
2. Go to the login page
3. You should see a "Sign in with Google" button
4. On the registration page, you should see a "Register with Google" button
5. Click "Sign in with Google" and verify:
   - You're redirected to Google's login page
   - After signing in with Google, you're redirected back to OpenDLP
   - You're successfully authenticated

## Security Considerations

### Client Secret Protection

- **Never commit** OAuth credentials to version control
- Store the client secret securely (environment variables, secrets management systems)
- Rotate credentials periodically
- Restrict access to production credentials

### Redirect URI Security

- Only add redirect URIs for domains you control
- Use HTTPS for production redirect URIs (required by Google for non-localhost URLs)
- Be specific - don't use wildcards in redirect URIs

### Session Security

OpenDLP uses Redis-backed sessions for OAuth state management:

- Ensure Redis is properly secured (authentication, network isolation)
- OAuth state tokens are stored in the session to prevent CSRF attacks
- Sessions should use secure, httponly cookies (configured in OpenDLP's session settings)

### User Privacy

- Only request the minimum required OAuth scopes (`openid`, `email`, `profile`)
- Users can revoke OpenDLP's access at any time via [Google Account permissions](https://myaccount.google.com/permissions)
- Clearly communicate what data is accessed in your privacy policy

## Troubleshooting

### "Sign in with Google" button doesn't appear

**Cause**: OAuth credentials not configured

**Solution**: Verify that `OAUTH_GOOGLE_CLIENT_ID` is set in your environment. Check the application logs for any configuration errors.

### Redirect URI mismatch error

**Error**: `redirect_uri_mismatch` or "Error 400: redirect_uri_mismatch"

**Cause**: The redirect URI used by your application doesn't match the URIs configured in Google Cloud Console

**Solution**:

1. Check your application's URL in the error message
2. Go to [Google Cloud Console > Credentials](https://console.cloud.google.com/apis/credentials)
3. Edit your OAuth client
4. Add the exact redirect URI from the error message to "Authorized redirect URIs"
5. Remember to add both `/auth/login/google/callback` and `/profile/link-google/callback` endpoints

### "Access blocked: This app's request is invalid"

**Cause**: OAuth consent screen not configured or missing required scopes

**Solution**:

1. Go to [OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent)
2. Ensure the consent screen is fully configured
3. Verify the required scopes are added: `openid`, `email`, `profile`

### "This app is blocked" or verification required

**Cause**: Your app is in "Testing" mode and the user is not added as a test user, or Google requires app verification

**Solution**:

- **For internal use**: Set OAuth consent screen to "Internal" user type (Google Workspace organizations only)
- **For testing**: Add test users on the OAuth consent screen page
- **For production with external users**: Publish the app (click "Publish App" on the OAuth consent screen). Apps using only non-sensitive scopes (openid, email, profile) don't require verification.

### Users can't link Google account to existing password account

**Cause**: Email mismatch - the Google account email must match the OpenDLP account email

**Solution**: Ensure users are trying to link a Google account that uses the same email address as their OpenDLP account. If the emails don't match, the linking will fail with an error message.

### OAuth state validation errors

**Error**: Flash message about "Invalid OAuth state" or "OAuth linking request"

**Cause**: Session cookie issues, or attempting to complete an OAuth flow without initiating it properly

**Solution**:

1. Ensure cookies are enabled in the browser
2. Verify Redis is running and accessible for session storage
3. Check that `SECRET_KEY` is configured (required for session signing)
4. Clear browser cookies and try again

### Development with localhost

When developing locally:

- Use `http://localhost:5000` (or your local port) for redirect URIs
- Google allows `http://` for localhost, but production must use `https://`
- Ensure your local environment has the OAuth credentials configured in `.env`

## Monitoring and Maintenance

### Logs

OpenDLP logs OAuth-related events. Check application logs for:

- OAuth authentication attempts
- Linking/unlinking operations
- Error messages with details about failures

### Credential Rotation

Best practice: Rotate OAuth credentials periodically

1. Create new credentials in Google Cloud Console
2. Update OpenDLP configuration with new credentials
3. Restart OpenDLP
4. Verify the new credentials work
5. Delete old credentials from Google Cloud Console

### User Management

Administrators can view which users are using OAuth authentication:

- Check the `oauth_provider` field in the users table
- Users can have both password and OAuth authentication enabled simultaneously

## Additional Resources

- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [OpenID Connect](https://openid.net/connect/)
- [Authlib Documentation](https://docs.authlib.org/en/latest/client/flask.html)
- [OpenDLP Configuration Guide](configuration.md)
