---
description: Independent review of a finished milestone (for example /review M3)
argument-hint: M0 .. M11
---
Use the spec-reviewer subagent to review milestone $ARGUMENTS against `plan/$ARGUMENTS.md` and the docs it lists. For milestones with UI, also use the ui-checker subagent on fresh snapshots. Report only real problems with file and line, and a pass or fail for every acceptance criterion. Then fix the problems that are clearly within the milestone's scope and list the rest for me.
