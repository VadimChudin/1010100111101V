# GitHub OAuth Activation

The platform contains the authorization-code web flow with PKCE, one-time state records, opaque seven-day sessions, project roles, and strict credentialed CORS. The feature is intentionally not enforced until secrets are configured in Railway.

## Register the OAuth app

Create a GitHub OAuth App under the owner account or organization. Use the production frontend URL as the homepage and register the exact callback URL below.

| GitHub field | Production value |
|---|---|
| Application name | Agent Room Beta |
| Homepage URL | `https://frontend-swart-alpha-20.vercel.app` |
| Authorization callback URL | `https://app-production-cc16.up.railway.app/v1/auth/github/callback` |

## Configure Railway variables

Set the following backend service variables. The secret must remain only in Railway; it must never be committed or exposed to the Vercel client.

| Variable | Required value |
|---|---|
| `GITHUB_OAUTH_CLIENT_ID` | Client ID shown by GitHub after OAuth App registration |
| `GITHUB_OAUTH_CLIENT_SECRET` | Generated client secret |
| `SESSION_SECRET` | A new high-entropy secret reserved for session-related cryptographic operations |
| `AUTH_REQUIRED` | `true`, only after the first successful OAuth sign-in is ready to claim the default workspace |
| `FRONTEND_ORIGINS` | `https://frontend-swart-alpha-20.vercel.app` (add any approved staging origin explicitly) |

## Activation order

Keep `AUTH_REQUIRED=false` while registering the app and setting the two GitHub variables. Confirm that `GET /v1/auth/status` reports `github_configured: true`, then open `/v1/auth/github/login` and complete one successful sign-in. That first account claims ownership of the existing default workspace. Finally set `AUTH_REQUIRED=true`, redeploy, and validate that unauthenticated access is rejected.

> GitHub recommends a random `state` value to protect the authorization request from CSRF and recommends PKCE for the code exchange. This implementation uses both and requests only identity scopes: `read:user`, `user:email`, and `offline_access`.[1][2]

## References

[1]: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps "GitHub — Authorizing OAuth apps"
[2]: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps "GitHub — OAuth app scopes"

## Smoke-test consent review

The production consent page was reviewed on 20 August 2026. It identifies **Agent Room Beta** as the requesting app and limits access to read-only profile and verified email data. It redirects only to the configured Railway callback URL. The authorization confirmation was explicitly approved by the workspace owner before submission.

The first consent submission attempt did not leave the GitHub authorization page, so no callback or session was created. The visible requested access remained unchanged: read-only profile and email data.

A browser snapshot refresh restored a stable consent button after a stale interaction error. No authorization result or callback had occurred at this checkpoint.

The production smoke test completed successfully. The OAuth callback returned to the Vercel frontend, created a session, and the header rendered the authenticated GitHub identity `VADIMCHUDIN`. The default workspace remained available after the authenticated redirect.

## Production enforcement result

After the owner session was established, `AUTH_REQUIRED=true` was enabled in Railway. A request without a session to `/v1/projects` returned `401`, an unapproved CORS origin was blocked, and a browser refresh retained the authenticated `VADIMCHUDIN` identity and workspace access. The GitHub OAuth/RBAC rollout is therefore active in production.
