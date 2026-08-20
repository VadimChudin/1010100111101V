# ADR 010: Desktop Project Source Chooser

**Status:** Accepted

## Context

Agent Room Desktop initially accepts only a local Git workspace chosen through the native folder picker. Users need an equally explicit second path: choose a repository from the GitHub account already authorized for Agent Room, then create or open a local working copy on the paired PC. The implementation must continue to support large local projects without uploading source code, must not expose GitHub access tokens to the renderer, and must not create a generic shell interface.

## Decision

Desktop onboarding presents two mutually exclusive project sources after GitHub authorization.

| Source | User action | Local outcome | Cloud visibility |
|---|---|---|---|
| **Local folder** | Select any local directory using the native picker | That directory becomes the runtime workspace; a Git repository is required before pairing | Opaque workspace identity and Git-derived metadata only |
| **GitHub repository** | Choose a repository returned by the authenticated cloud API and select a local destination directory | Desktop main process performs a fixed `git clone` operation into a validated empty destination, then makes the clone the runtime workspace | Repository identity and Git-derived metadata only |

The cloud API lists repositories using the GitHub OAuth credential stored encrypted at rest in the cloud database. The renderer receives only a bounded repository projection: `id`, `full_name`, `private`, `default_branch`, `html_url`, and clone URL. It never receives the OAuth credential.

For cloning, the Electron main process requests a fresh, server-validated clone source over the authenticated desktop session for each operation. The GitHub credential is delivered only to the main process and used through a temporary `GIT_ASKPASS` helper with environment variables. It is never interpolated into a command line, persisted in the desktop state, exposed through preload, or delivered to the renderer. The helper is removed immediately after the fixed `git clone --origin origin -- <clone_url> <destination>` operation completes. The destination must be a user-selected empty directory from the native picker.

## Security Boundaries

1. The cloud remains the authority for the authenticated GitHub account and repository eligibility.
2. The desktop renderer receives a narrow IPC allow-list only: list repositories, choose destination, select a repository, and begin controlled clone.
3. The desktop main process validates repository IDs against a fresh cloud lookup rather than trusting a renderer-supplied clone URL.
4. Clone operations use `execFile` with fixed arguments. There is no generic command or raw shell API.
5. The runtime receives a workspace path only after local filesystem and Git validation succeed.
6. Private source code stays local. Runtime sync continues to send opaque workspace IDs, Git metadata, and explicitly approved operation results only.

## Consequences

The user can choose either a pre-existing local project or a GitHub project from one onboarding surface. Private repositories require the expanded GitHub OAuth `repo` scope and a re-authorization once. GitHub OAuth credentials are handled as an integration credential, separate from opaque Agent Room sessions and encrypted in the cloud database.

## Alternatives Rejected

| Alternative | Reason rejected |
|---|---|
| Send OAuth token to renderer | Violates renderer isolation and enlarges the token theft surface |
| Embed token in clone URL | Exposes credential in process lists, logs, and Git remote configuration |
| Clone arbitrary renderer-supplied URL | Allows uncontrolled network access and bypasses account/project binding |
| Full Git mirror/sync of local projects to cloud | Incompatible with large private workspaces and local-first source boundaries |
| Generic shell tool for clone and setup | Unnecessarily expands remote command execution surface |
