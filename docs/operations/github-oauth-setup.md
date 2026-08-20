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
