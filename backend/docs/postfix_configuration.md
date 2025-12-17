# Postfix Email Relay Configuration

## Overview

The production deployment includes a Postfix container that acts as an SMTP relay. This allows the application to send emails through a trusted upstream SMTP service (like SendGrid, AWS SES, Mailgun, etc.) without embedding those credentials directly in the application code.

## Architecture

```
OpenDLP App → Postfix Container → Upstream SMTP Service → Recipients
```

The application sends emails to the local Postfix container on port 25, and Postfix relays them to your configured upstream SMTP service.

## Environment Variables

### Application Configuration

Add these to your `.env.prod` file:

```bash
# Email adapter type
EMAIL_ADAPTER=smtp

# SMTP connection settings (already set in compose.production.yaml)
# SMTP_HOST=postfix
SMTP_PORT=25
SMTP_USE_TLS=false

# Sender information
SMTP_FROM_EMAIL=noreply@yourdomain.com
SMTP_FROM_NAME=OpenDLP

# No username/password needed for internal relay
SMTP_USERNAME=
SMTP_PASSWORD=
```

### Postfix Relay Configuration

Add these to your `.env.prod` file:

```bash
# Upstream SMTP relay host (with port)
# Examples:
#   SendGrid: smtp.sendgrid.net:587
#   AWS SES: email-smtp.us-east-1.amazonaws.com:587
#   Mailgun: smtp.mailgun.org:587
RELAYHOST=smtp.example.com:587

# Authentication for upstream SMTP service
RELAYHOST_USERNAME=your-smtp-username
RELAYHOST_PASSWORD=your-smtp-password

# Domains allowed to send through this relay
ALLOWED_SENDER_DOMAINS=yourdomain.com

# Domain masquerading (optional)
MASQUERADE_DOMAINS=yourdomain.com
```

## Example Configurations

### SendGrid

```bash
RELAYHOST=smtp.sendgrid.net:587
RELAYHOST_USERNAME=apikey
RELAYHOST_PASSWORD=SG.your-api-key-here
ALLOWED_SENDER_DOMAINS=yourdomain.com
MASQUERADE_DOMAINS=yourdomain.com
```

### AWS SES

```bash
RELAYHOST=email-smtp.us-east-1.amazonaws.com:587
RELAYHOST_USERNAME=your-aws-access-key-id
RELAYHOST_PASSWORD=your-aws-secret-access-key
ALLOWED_SENDER_DOMAINS=yourdomain.com
MASQUERADE_DOMAINS=yourdomain.com
```

### Mailgun

```bash
RELAYHOST=smtp.mailgun.org:587
RELAYHOST_USERNAME=postmaster@yourdomain.com
RELAYHOST_PASSWORD=your-mailgun-smtp-password
ALLOWED_SENDER_DOMAINS=yourdomain.com
MASQUERADE_DOMAINS=yourdomain.com
```

## Testing

### Test Postfix Container Health

```bash
docker compose -f compose.production.yaml ps postfix
```

The status should show as "healthy".

### Test Email Sending

1. Access the Flask shell in the running container:
   ```bash
   docker compose -f compose.production.yaml exec app flask shell
   ```

2. Send a test email:
   ```python
   from opendlp.bootstrap import get_email_adapter

   adapter = get_email_adapter()
   result = adapter.send_email(
       to=["test@example.com"],
       subject="Test Email",
       text_body="This is a test email from OpenDLP."
   )
   print(f"Email sent: {result}")
   ```

### View Postfix Logs

```bash
docker compose -f compose.production.yaml logs -f postfix
```

Look for successful relay messages or any authentication/connection errors.

## Troubleshooting

### Email Not Sending

1. **Check Postfix is healthy:**
   ```bash
   docker compose -f compose.production.yaml ps
   ```

2. **Verify environment variables are set:**
   ```bash
   docker compose -f compose.production.yaml config | grep -A 10 postfix
   ```

3. **Check Postfix logs:**
   ```bash
   docker compose -f compose.production.yaml logs postfix
   ```

### Common Issues

- **"relay access denied"**: Check `ALLOWED_SENDER_DOMAINS` matches your `SMTP_FROM_EMAIL` domain
- **"authentication failed"**: Verify `RELAYHOST_USERNAME` and `RELAYHOST_PASSWORD` are correct
- **"connection refused"**: Check `RELAYHOST` is correct and accessible from the container

### Manual Testing from Container

Execute a shell in the Postfix container:

```bash
docker compose -f compose.production.yaml exec postfix sh
```

Check Postfix configuration:

```bash
postconf | grep relayhost
postconf | grep smtp_sasl
```

## Security Considerations

1. **Credentials**: Never commit `.env.prod` to version control. Store sensitive credentials securely (e.g., AWS Secrets Manager, HashiCorp Vault).

2. **SPF/DKIM/DMARC**: Configure DNS records for your sending domain to improve deliverability and prevent spoofing.

3. **Rate Limiting**: Monitor your upstream SMTP service for rate limits and adjust application sending patterns accordingly.

4. **Internal Communication**: The app → Postfix communication uses unencrypted SMTP on port 25 since it's within the Docker network. This is acceptable for internal container communication.

## Resource Limits

The default memory limits for Postfix in `compose.production.yaml` are commented out:

```yaml
# mem_limit: 256m
# mem_reservation: 128m
```

Uncomment and adjust these in `compose.production.override.yaml` based on your email volume:
- Light usage (< 100 emails/day): 128MB limit
- Medium usage (100-1000 emails/day): 256MB limit
- Heavy usage (> 1000 emails/day): 512MB limit
