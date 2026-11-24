# The registration auto-reply could be queued by an event

## Background

When a member of the public registers, the route sends them an auto-reply
email. `entrypoints/blueprints/registration.py` does it by hand, after the
block that saved the registration has committed:

```python
if result.is_valid:
    _record_submission(ip_address, email)
    _send_registration_auto_reply(result.respondent)
    return redirect(url_for("registration.thank_you", url_slug=url_slug), 302)
```

`_send_registration_auto_reply` opens a second UnitOfWork, calls
`email_send_service.send_registration_auto_reply` with the email adapter and
the request's locale, and swallows any exception so a failed send never blocks
the thank-you page.

Found while planning domain events (`docs/agent/event-message-bus/plan.md`,
decision D8). It was left as it is.

## Why it looks like an event

It is a reaction to "a respondent registered" that must only happen if the
registration committed, and that must never fail the registration. That is the
shape `uow.after_commit` exists for, and the same shape as the automatic
export, which is now scheduled by the handler for `RespondentsChanged`.

## Why it was not moved

An after-commit callback must not touch the database, and it runs in the
request. The auto-reply does not fit either rule as it stands:

- It reads the registration page and the email template, and writes a
  `RespondentEmailSendRecord`. That is database work.
- It needs the request's locale, so the email is in the language the
  respondent registered in.
- It needs the email adapter, which the entrypoint builds.
- It makes an SMTP send, which is slow and can hang.

## What the change would be

1. Record a `RespondentRegistered(assembly_id, respondent_id, locale)` event in
   `registration_submission_service`. The locale has to travel on the event,
   because the handler has no request.
2. A handler registers an after-commit callback that queues a new Celery task.
3. The task opens its own UnitOfWork and calls `send_registration_auto_reply`
   with the worker's email adapter and the locale from the event.
4. The route loses `_send_registration_auto_reply`.

## What it would buy

- The SMTP send leaves a public request. Today a slow mail server holds a
  gunicorn thread for every registration, on the one page the public can load
  us with.
- A failed send could be retried by Celery. Today it is logged and lost.
- The route stops needing to know that an email exists.

## What to check first

- The auto-reply would arrive a little later, and not at all while the workers
  are down. Decide whether that is acceptable.
- A retried task must not send twice. `RespondentEmailSendRecord` is the place
  to check before sending.
- `RespondentRegistered` would be a second event for the same change that
  already records `RespondentsChanged`. That is fine - they answer different
  questions - but the activity log plan (sc-922) should decide which one it
  listens to.
