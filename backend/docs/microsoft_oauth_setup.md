# Microsoft OAuth Setup

This guide explains how to configure Microsoft OAuth authentication for OpenDLP, allowing users to sign in and register using their Microsoft accounts (both personal and work/school accounts).

## Overview

Microsoft OAuth integration provides:

- **Sign in with Microsoft**: Users can authenticate using their existing Microsoft accounts
- **Register with Microsoft**: New users can create OpenDLP accounts using Microsoft authentication (still requires an invite code)
- **Account linking**: Users with existing password-based accounts can link their Microsoft account for additional authentication flexibility
- **Single OAuth provider**: Users can have either Google OR Microsoft linked (not both). Linking a new provider automatically replaces the existing one
- **Supports both account types**: Personal Microsoft accounts (outlook.com, hotmail.com) and work/school accounts (Office 365, Azure AD)

## Prerequisites

- An Azure account (or ability to create one)
- Admin access to the Azure Portal
- Your OpenDLP instance's public URL (for configuring redirect URIs)

## Step 1: Sign in to Azure Portal

1. Go to the [Azure Portal](https://portal.azure.com/)
2. Sign in with your Microsoft account

If you don't have an Azure account, you can create one for free at [azure.microsoft.com/free](https://azure.microsoft.com/free/).

## Step 2: Register an Application

1. In the Azure Portal, search for **"App registrations"** in the top search bar
2. Click on **App registrations** in the results
3. Click **+ New registration**
4. Configure the app registration:
   - **Name**: OpenDLP (or your organization's name)
   - **Supported account types**: Select **"Accounts in any organizational directory (Any Azure AD directory - Multitenant) and personal Microsoft accounts (e.g. Skype, Xbox)"**
     - This option allows both personal Microsoft accounts AND work/school accounts
   - **Redirect URI**: Select **Web** from the dropdown, then add:
     - For production: `https://yourdomain.com/auth/login/microsoft/callback`
     - For local development: `http://localhost:5000/auth/login/microsoft/callback`
5. Click **Register**

After registration, you'll be taken to the app's Overview page.

## Step 3: Note Your Application (Client) ID

On the Overview page, you'll see important identifiers:

1. Copy the **Application (client) ID** - you'll need this for the `OAUTH_MICROSOFT_CLIENT_ID` environment variable
2. Note the **Directory (tenant) ID** - this identifies your Azure AD tenant (not needed for OpenDLP configuration)

## Step 4: Create a Client Secret

1. In the left sidebar, click **Certificates & secrets**
2. Click the **Client secrets** tab
3. Click **+ New client secret**
4. Add a description: "OpenDLP OAuth"
5. Select an expiry period:
   - **180 days (6 months)**
   - **365 days (12 months)**
   - **730 days (24 months)**
   - **Custom** - specify your own date

   **Note**: You'll need to create a new secret before the current one expires

6. Click **Add**
7. **IMMEDIATELY copy the Value** - this is your client secret
   - **Important**: The secret value is only shown once. If you navigate away, you'll need to create a new secret
   - Save this securely - you'll use it for the `OAUTH_MICROSOFT_CLIENT_SECRET` environment variable

## Step 5: Configure Redirect URIs for Account Linking

You need to add additional redirect URIs for the account linking feature:

1. In the left sidebar, click **Authentication**
2. Under **Platform configurations**, find the **Web** platform you added earlier
3. Click **Add URI** to add more redirect URIs:
   - For production account linking: `https://yourdomain.com/profile/link-microsoft/callback`
   - For local development account linking: `http://localhost:5000/profile/link-microsoft/callback`
4. Click **Save** at the bottom of the page

Your complete list of redirect URIs should be:

- `https://yourdomain.com/auth/login/microsoft/callback` (login)
- `https://yourdomain.com/profile/link-microsoft/callback` (account linking)
- `http://localhost:5000/auth/login/microsoft/callback` (local dev login)
- `http://localhost:5000/profile/link-microsoft/callback` (local dev linking)

## Step 6: Configure Token Settings (Optional)

The default settings usually work fine, but you may want to review:

1. In the left sidebar, click **Token configuration**
2. Review the optional and additional claims
3. The default configuration includes:
   - `email` - User's email address
   - `name` - User's display name
   - `preferred_username` - User's username

These claims are automatically included in the ID token and are sufficient for OpenDLP.

## Step 7: Configure OpenDLP

Add the OAuth credentials to your OpenDLP configuration.

### Using Environment Variables

Set these environment variables in your deployment:

```bash
OAUTH_MICROSOFT_CLIENT_ID="your-application-client-id"
OAUTH_MICROSOFT_CLIENT_SECRET="your-client-secret"  # pragma: allowlist secret
```

### Using .env File (Development)

For local development, add these to your `.env` file:

```bash
# Microsoft OAuth
OAUTH_MICROSOFT_CLIENT_ID=your-application-client-id
OAUTH_MICROSOFT_CLIENT_SECRET=your-client-secret
```

**Security Warning**: Never commit `.env` files or OAuth secrets to version control.

### Using Docker Compose

Add the environment variables to your `docker-compose.yml`:

```yaml
services:
  web:
    environment:
      - OAUTH_MICROSOFT_CLIENT_ID=your-application-client-id
      - OAUTH_MICROSOFT_CLIENT_SECRET=your-client-secret
```

Or use an environment file:

```yaml
services:
  web:
    env_file:
      - .env
```

## Step 8: Restart OpenDLP

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

## Step 9: Verify the Setup

1. Navigate to your OpenDLP instance
2. Go to the login page
3. You should see a "Sign in with Microsoft" button (alongside "Sign in with Google" if configured)
4. On the registration page, you should see a "Register with Microsoft" button
5. Click "Sign in with Microsoft" and verify:
   - You're redirected to Microsoft's login page
   - After signing in with Microsoft, you're redirected back to OpenDLP
   - You're successfully authenticated

## Step 10: Publisher Verification (Optional but Recommended)

### What is Publisher Verification?

When users try to sign in with an **unverified publisher** app, they see a warning screen stating:

> "This app is not verified. This app was created by an unverified publisher. Unverified apps may be risky to use."

**Publisher verification** adds a blue verified badge to your app's consent screen, providing:

- **Increased trust**: Users see your organization is verified by Microsoft
- **Smoother adoption**: Admins can set policies allowing only verified publishers
- **Professional branding**: Blue verified badge across Microsoft consent screens

Beginning **November 2020**, users **cannot consent** to most newly registered multitenant apps from unverified publishers. This particularly affects apps requiring permissions beyond basic sign-in.

### Should You Complete Publisher Verification?

**Yes, if:**
- Your OpenDLP instance is used by external organizations
- Users from multiple tenants need to sign in
- You want to maximize trust and adoption
- You need to comply with organizational policies requiring verified publishers

**Maybe not immediately, if:**
- You're only using OpenDLP internally within your own organization
- Your IT admin can grant tenant-wide admin consent
- You're still testing the integration

**Note**: There is **no cost** to complete publisher verification. Microsoft provides this free to developers.

### Prerequisites for Publisher Verification

Before you can verify your publisher, you must meet these requirements:

#### 1. Microsoft AI Cloud Partner Program Account

You need a verified **Microsoft AI Cloud Partner Program (CPP)** account (formerly Microsoft Partner Network/MPN):

- **Enrollment**: Free to join at [partner.microsoft.com](https://partner.microsoft.com/cloud-partner-program)
- **Account type**: Must be the **Partner Global Account (PGA)** for your organization
- **Verification**: Account must complete Microsoft's verification process (typically 3-5 business days)
- **Email requirement**: Valid business email (not personal accounts like hotmail.com, outlook.com)

**Important**: The domain of the email address used during CPP verification must either:
- Match the publisher domain you set for the app, OR
- Be a DNS-verified custom domain added to your Microsoft Entra tenant

#### 2. App Registration Requirements

- App must be registered using a **Microsoft Entra work or school account** (not a personal Microsoft account)
- Apps registered in **Azure AD B2C tenants are NOT supported**
- App must have a **publisher domain configured** (cannot be `*.onmicrosoft.com`)

#### 3. User Permissions

The user performing verification must have specific roles in both systems:

**In Azure Portal (Microsoft Entra ID)**:
- Application Administrator, OR
- Cloud Application Administrator

**In Partner Center**:
- Microsoft AI Cloud Partner Program Admin, OR
- Accounts Admin

#### 4. Additional Requirements

- **Multifactor authentication (MFA)** must be enabled on your organizational account
- Must consent to the **Microsoft identity platform for developers Terms of Use**

### Step-by-Step: Enroll in Microsoft AI Cloud Partner Program

If you don't already have a Partner Program account:

1. **Go to Partner Center**:
   - Visit [partner.microsoft.com/partnership](https://partner.microsoft.com/en-US/partnership)
   - Click **"Become a partner"** or **"Enroll now"**

2. **Sign in or Create Account**:
   - Use a valid business email address (not personal)
   - Email cannot contain generic terms like "info", "admin", or "marketing"
   - You'll receive a verification code by email

3. **Provide Company Information**:
   - Legal business name and details
   - Business address
   - Primary contact information
   - You must have authorization to sign legal agreements on behalf of your organization

4. **Submit for Verification**:
   - Microsoft will verify your email address
   - Identity verification may be required (government ID like passport or driver's license)
   - Verification typically takes **3-5 business days**

5. **Monitor Verification Status**:
   - Go to **Legal Info** in Partner Center
   - Check the **Verification summary** page
   - You'll receive email notifications about verification progress

6. **Note Your Partner ID**:
   - Once verified, locate your **Partner ID** (also called MPN ID or Location MPN ID)
   - You'll need this when marking your app as verified
   - Ensure you use the **Partner Global Account (PGA)** ID, not a location ID

**Reference**: [Create a Microsoft AI Cloud Partner Program account](https://learn.microsoft.com/en-us/partner-center/enroll/mpn-create-a-partner-center-account)

### Step-by-Step: Mark Your App as Publisher Verified

Once your Partner Program account is verified:

1. **Sign in to Azure Portal**:
   - Go to [portal.azure.com](https://portal.azure.com/)
   - Use an account with Application Administrator or Cloud Application Administrator role
   - Ensure MFA is enabled on your account

2. **Navigate to Your App**:
   - Go to **App registrations**
   - Select your OpenDLP app registration

3. **Configure Publisher Domain** (if not already set):
   - Go to **Branding & properties**
   - Set the **Publisher domain** to match your organization's verified domain
   - This domain must match the email domain used in your CPP account verification

4. **Add Publisher Domain to Tenant** (if needed):
   - Go to **Microsoft Entra ID** > **Custom domain names**
   - Add your domain and complete DNS verification
   - Follow Microsoft's domain verification process

5. **Start Verification Process**:
   - Return to your app's **Branding & properties** blade
   - Scroll to the bottom
   - Click **"Add Partner ID to verify publisher"**

6. **Review Requirements**:
   - A dialog will show the verification requirements
   - Ensure all prerequisites are met

7. **Enter Partner ID**:
   - Input your **Partner ID** from Partner Center
   - Use the Partner Global Account (PGA) ID
   - Click **"Verify and save"**

8. **Wait for Processing**:
   - Verification may take a few minutes
   - Upon success, you'll see a blue verified badge next to your **Publisher display name**

9. **Test the Verification**:
   - Sign out and try signing in to OpenDLP with Microsoft OAuth
   - The consent screen should now show the blue verified badge
   - To force a consent prompt for testing: add `?prompt=consent` to your authorization URL (testing only)

10. **Verification Complete**:
    - The verified badge will appear to all users
    - Badge replication across Microsoft systems may take some time
    - Repeat steps 2-8 for any additional app registrations

**Reference**: [Mark an app as publisher verified](https://learn.microsoft.com/en-us/entra/identity-platform/mark-app-as-publisher-verified)

### Alternatives to Publisher Verification

If you cannot complete publisher verification immediately, these alternatives may help:

#### 1. Tenant-Wide Admin Consent

If OpenDLP is used primarily within a single organization:

- IT admin can grant **tenant-wide admin consent** for the app
- This allows all users in that organization to use the app without individual consent
- Does not require publisher verification
- **How**: Azure Portal > App registrations > [Your App] > API permissions > Grant admin consent

#### 2. Admin Consent Workflow

Organizations can enable an **admin consent workflow**:

- Users request admin approval when they encounter an unverified app
- Admins receive notifications and can approve/deny requests
- Provides a middle ground between blocking unverified apps and allowing all access

#### 3. Custom App Consent Policies

Organizations can create **custom consent policies** to:

- Allow specific unverified apps
- Set conditions for when users can consent
- Managed through Microsoft Graph API

### Important Limitations

Publisher verification does **NOT** indicate:

- ✗ Specific security certifications or compliance standards
- ✗ App quality criteria or code review
- ✗ Industry standard adherence
- ✗ Specific best practices compliance

It only verifies the **authenticity of the publisher's organization**, not the app itself.

### Troubleshooting Publisher Verification

**Problem**: "Domain doesn't match"

- **Solution**: Ensure your CPP account email domain matches your app's publisher domain or is a verified custom domain in your tenant

**Problem**: "Partner ID not found"

- **Solution**: Verify you're using the Partner Global Account (PGA) ID, not a location-specific ID

**Problem**: "Insufficient permissions"

- **Solution**: Ensure you have the required roles in both Azure Portal and Partner Center

**Problem**: Verification badge not appearing

- **Solution**: Wait a few hours for replication, clear browser cache, or check you're testing with the correct tenant

For more troubleshooting, see [Microsoft's troubleshooting guide](https://learn.microsoft.com/en-us/entra/identity-platform/troubleshoot-publisher-verification).

### Additional Resources

- [Publisher verification overview](https://learn.microsoft.com/en-us/entra/identity-platform/publisher-verification-overview)
- [Microsoft AI Cloud Partner Program](https://partner.microsoft.com/cloud-partner-program)
- [Verify your account information](https://learn.microsoft.com/en-us/partner-center/enroll/verification-responses)

## Security Considerations

### Client Secret Protection

- **Never commit** OAuth credentials to version control
- Store the client secret securely (environment variables, secrets management systems)
- Rotate credentials periodically (before expiry)
- Restrict access to production credentials
- Use Azure Key Vault for enhanced secret management in production

### Redirect URI Security

- Only add redirect URIs for domains you control
- Use HTTPS for production redirect URIs (required by Microsoft for non-localhost URLs)
- Be specific - don't use wildcards in redirect URIs
- Review and audit redirect URIs regularly

### Session Security

OpenDLP uses Redis-backed sessions for OAuth state management:

- Ensure Redis is properly secured (authentication, network isolation)
- OAuth state tokens are stored in the session to prevent CSRF attacks
- Sessions should use secure, httponly cookies (configured in OpenDLP's session settings)

### User Privacy

- Only request the minimum required OAuth scopes (`openid`, `email`, `profile`)
- Users can revoke OpenDLP's access at any time via [Microsoft Account permissions](https://account.microsoft.com/privacy/app-access)
- Clearly communicate what data is accessed in your privacy policy

### Account Types

The recommended configuration supports both:

- **Personal Microsoft accounts** (outlook.com, hotmail.com, live.com, msn.com)
- **Work or school accounts** (Office 365, Azure AD organizational accounts)

If you only want to support organizational accounts, change the supported account types during app registration to "Accounts in this organizational directory only".

## Troubleshooting

### "Sign in with Microsoft" button doesn't appear

**Cause**: OAuth credentials not configured

**Solution**: Verify that `OAUTH_MICROSOFT_CLIENT_ID` is set in your environment. Check the application logs for any configuration errors.

### Redirect URI mismatch error

**Error**: `AADSTS50011: The redirect URI specified in the request does not match the redirect URIs configured for the application`

**Cause**: The redirect URI used by your application doesn't match the URIs configured in Azure Portal

**Solution**:

1. Check your application's URL in the error message
2. Go to [Azure Portal > App registrations](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)
3. Select your OpenDLP app
4. Click **Authentication** in the left sidebar
5. Add the exact redirect URI from the error message to the list
6. Remember to add both `/auth/login/microsoft/callback` and `/profile/link-microsoft/callback` endpoints
7. Click **Save**

### "Need admin approval" message

**Error**: User sees "Need admin approval" after signing in

**Cause**: Your Azure AD tenant requires admin consent for applications

**Solution**:

- **For testing**: Add test users explicitly in Azure AD
- **For production**: Have an Azure AD admin grant tenant-wide consent:
  1. Go to your app registration in Azure Portal
  2. Click **API permissions** in the left sidebar
  3. Click **Grant admin consent for [Your Organization]**
  4. Confirm the action

### Client secret expired

**Error**: Authentication fails with error about invalid client credentials

**Cause**: Your client secret has expired

**Solution**:

1. Go to [Azure Portal > App registrations](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)
2. Select your OpenDLP app
3. Click **Certificates & secrets**
4. Create a new client secret (see Step 4 above)
5. Update `OAUTH_MICROSOFT_CLIENT_SECRET` in your OpenDLP configuration
6. Restart OpenDLP

### OAuth state validation errors

**Error**: Flash message about "Invalid OAuth state" or "OAuth linking request"

**Cause**: Session cookie issues, or attempting to complete an OAuth flow without initiating it properly

**Solution**:

1. Ensure cookies are enabled in the browser
2. Verify Redis is running and accessible for session storage
3. Check that `SECRET_KEY` is configured (required for session signing)
4. Clear browser cookies and try again
5. Check that your OpenDLP instance is using HTTPS in production (required for secure cookies)

### Users can't link Microsoft account to existing password account

**Cause**: Email mismatch - the Microsoft account email must match the OpenDLP account email

**Solution**: Ensure users are trying to link a Microsoft account that uses the same email address as their OpenDLP account. If the emails don't match, the linking will fail with an error message.

### Development with localhost

When developing locally:

- Use `http://localhost:5000` (or your local port) for redirect URIs
- Microsoft allows `http://` for localhost, but production must use `https://`
- Ensure your local environment has the OAuth credentials configured in `.env`

### Personal vs. Work Account Issues

If users report they can only sign in with work accounts (or vice versa):

1. Go to your app registration in Azure Portal
2. Click **Authentication**
3. Check the **Supported account types** setting
4. Ensure it's set to "Accounts in any organizational directory (Any Azure AD directory - Multitenant) and personal Microsoft accounts"
5. If you changed it, click **Save**

## Monitoring and Maintenance

### Logs

OpenDLP logs OAuth-related events. Check application logs for:

- OAuth authentication attempts
- Linking/unlinking operations
- Error messages with details about failures

### Credential Rotation

Best practice: Rotate OAuth credentials before they expire

1. Create new client secret in Azure Portal
2. Update OpenDLP configuration with new secret
3. Restart OpenDLP
4. Verify the new credentials work
5. Delete old secret from Azure Portal

**Tip**: Set a calendar reminder 30 days before your secret expires.

### Expiry Monitoring

OpenDLP can monitor your Microsoft OAuth client secret expiry date and provide automated alerting through the health check endpoint.

#### Configuration

Add the expiry date to your OpenDLP configuration:

```bash
OAUTH_MICROSOFT_CLIENT_SECRET_EXPIRY=2026-06-15
```

**Format**: `YYYY-MM-DD` (ISO 8601 date format)

**Where to find the expiry date**:

1. Go to [Azure Portal > App registrations](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)
2. Select your OpenDLP app
3. Click **Certificates & secrets**
4. View the **Expires** column for your client secret

#### Health Check Integration

When configured, the `/health` endpoint includes two Microsoft OAuth expiry fields:

```json
{
  "oauth_microsoft_days_to_expiry": 45,
  "oauth_microsoft_expiry_status": "OK"
}
```

**Status levels**:

- **OK**: More than 30 days remaining until expiry (HTTP 200)
- **WARNING**: 30 days or less until expiry (HTTP 200 by default)
- **EXPIRED**: Secret has expired (HTTP 500)
- **UNKNOWN**: Expiry date not configured (HTTP 200 by default)

The `oauth_microsoft_days_to_expiry` field shows the exact number of days remaining (negative if expired, `null` if not configured).

#### Monitoring Configuration

**Basic monitoring** (default):

```bash
curl https://yourdomain.com/health
```

Returns HTTP 500 only when the secret has **EXPIRED**.

**Strict monitoring** (alerts on warning):

```bash
curl https://yourdomain.com/health?fail_on_warning=true
```

Returns HTTP 500 when the status is **WARNING**, **EXPIRED**, or **UNKNOWN**.

**Recommended setup**:

1. Configure monitoring system (Nagios, Prometheus, etc.) to check `/health?fail_on_warning=true`
2. Set up alerts when the endpoint returns HTTP 500
3. Configure OpenDLP with the correct expiry date
4. Rotate credentials before receiving alerts

**Example monitoring script**:

```bash
#!/bin/bash
RESPONSE=$(curl -s -w "%{http_code}" https://yourdomain.com/health?fail_on_warning=true)
HTTP_CODE="${RESPONSE: -3}"

if [ "$HTTP_CODE" -ne 200 ]; then
    echo "CRITICAL: Microsoft OAuth secret expiring soon or expired"
    exit 2
fi

echo "OK: Microsoft OAuth secret valid"
exit 0
```

#### Rotation Workflow with Monitoring

1. **30 days before expiry**: WARNING status triggers alert
2. **Create new secret** in Azure Portal
3. **Update configuration** with new secret and new expiry date
4. **Restart OpenDLP**
5. **Verify** health check returns OK status
6. **Delete old secret** from Azure Portal

This gives you a 30-day window to rotate credentials before they expire.

### User Management

Administrators can view which users are using OAuth authentication:

- Check the `oauth_provider` field in the users table
- Users can have either password OR OAuth authentication, or both
- When a user links a different OAuth provider, the previous one is automatically replaced (single provider choice model)

### Monitoring Sign-ins

In Azure Portal:

1. Go to your app registration
2. Click **Monitoring** in the left sidebar
3. View sign-in logs and usage statistics

## Differences from Google OAuth

If you're familiar with Google OAuth, key differences:

- **Azure Portal** instead of Google Cloud Console
- **App Registration** instead of OAuth Client
- **Client Secret** with expiry (Google secrets don't expire)
- **Supports both personal and work accounts** by default (single configuration)
- **Tenant isolation** options available for enterprise deployments

## Additional Resources

- [Microsoft identity platform documentation](https://docs.microsoft.com/en-us/azure/active-directory/develop/)
- [Microsoft Authentication Library (MSAL)](https://docs.microsoft.com/en-us/azure/active-directory/develop/msal-overview)
- [Azure AD App registration documentation](https://docs.microsoft.com/en-us/azure/active-directory/develop/quickstart-register-app)
- [Supported account types explained](https://docs.microsoft.com/en-us/azure/active-directory/develop/supported-accounts-validation)
- [OpenDLP Configuration Guide](configuration.md)
- [Google OAuth Setup](google_oauth_setup.md) - for comparison
