# Runbook: first clinic admin (FN-IAM-05, TSK-IAM-05-B)

Only a clinic admin can create accounts (FN-IAM-05), so a new deployment needs its first admin from outside the API. `jude-admin create-first-admin` creates it.

## When it works

The command only works while **no active clinic admin exists**. That covers two cases:
- a fresh database;
- recovery after every admin account was deactivated outside the API. The API itself refuses to deactivate or demote the last admin (409 `LAST_ADMIN`).

When an active admin exists, the command refuses. New accounts are then created in the app.

## Steps

1. Run inside the api container. That container has `JUDE_DATABASE_URL` set to a login user that is a member of `app_rw` and `audit_append`.
2. Run the command in an interactive terminal:
   ```sh
   docker compose exec api jude-admin create-first-admin --login <login> --display-name "<full name>"
   ```
   It prompts `Password:` and does not echo what you type.
   - The password is never an argument, because arguments end up in shell history and the process list.
   - Without a terminal, for example in a script, the first line of standard input is used.
3. Exit 0 prints the new account id. Exit 1 prints `refused: …` (an admin exists, password shorter than 12 characters, `LOGIN_TAKEN`, `NAME_REQUIRED`). Exit 2 means a usage error.

## What gets recorded

- One `governance."user"` row: role `clinic_admin`, `created_by` NULL, password as argon2id only.
- One audit event `user.created` with `user_id` NULL and role `system`. Its summary is `{role, active}`.
- Neither the login nor the password appears in any log.

## Rules the command follows

- The account must belong to a named person (SEC-01), as for every account. Do not create shared or generic admin accounts.
- Record the creation in the quarterly account review (FN-IAM-06).
