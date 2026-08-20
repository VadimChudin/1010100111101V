# ADR 005: Git-derived project map with durable agent context

**Status:** Accepted

## Context

The initial workspace canvas was populated by a static module registry. It made the interface demonstrable but did not represent the deployed repository, its tracked files, dependency manifests, or source relationships. The product requirement is that the dashboard is a current-project control surface rather than a status page for the agent.

## Decision

Git is the source of truth for code. The backend indexes only Git-tracked paths from the controlled `/workspace` checkout, records a typed file tree, parses `pyproject.toml` and `package.json`, and derives stable module identifiers from source scopes. Internal source imports become graph edges where they can be resolved safely. The API exposes the index, tracked files, and an editor-authorized refresh operation.

The workspace SQLite database is not a second code store. It retains agent-added notes, tasks, and markers. Re-indexing updates Git-derived modules in place using stable identifiers and never deletes modules that still have attached notes or tasks; removed code scopes with retained context are marked `orphaned` instead.

The production image contains a read-only repository snapshot initialized as a local Git repository. Git metadata, environment files, and build artifacts are excluded from the Docker build context. The runtime does not receive arbitrary filesystem paths from the API.

## Consequences

The dashboard now has a reproducible map of the deployed project revision and retains conversation-derived context across refreshes. File and dependency data are bounded to tracked repository content, preserving the existing typed-tool and authorization model. The index reflects the production build snapshot; synchronizing a private remote repository at runtime remains a separate future integration requiring explicit GitHub authorization and worker isolation.
