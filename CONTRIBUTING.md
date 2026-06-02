# Contributing

Working agreements for Team 4 during the IADS Hackathon.

## Branching

- `main` is protected — no direct pushes
- One branch per person: `feat/asad-sql-generator`, `feat/omar-orchestrator`, etc.
- Pull requests merge to `main` after a quick review (any teammate)

## Commit messages

Use Conventional Commits:

```
feat(agents): add SQL validator with sqlglot checks
fix(database): handle connection timeout gracefully
docs(architecture): document the retry loop
test(validator): add cases for hallucinated columns
```

Prefixes: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`.

## Ownership

Each person owns specific files (see README). If you need to change someone else's file:

1. Talk to them first
2. Make the change on your branch
3. Tag them in the PR

This prevents merge conflicts and keeps the team aligned.

## Pydantic models are sacred

The models in `src/sql_agent/core/models.py` are the interfaces between every component. If you change one, you break everyone else's code. So:

- Discuss in the group chat before changing
- Update every consumer in the same PR
- Mention it in standup

## Day 1 priorities (2 June)

1. First 30 min: everyone clones the repo, gets it running locally
2. Next 2 hours: as a team, agree on the Pydantic model shapes — these are the interfaces
3. Then: parallel work begins on owned modules

## Standups

Every 4 hours during the hackathon. 5 minutes max. Each person:

- What I just did
- What I'm about to do
- What's blocking me

## Code quality

- Run `make lint` before pushing
- Run `make test` before pushing
- If CI fails, fix it before going to bed
- Don't merge broken code into `main` even at 3 AM
