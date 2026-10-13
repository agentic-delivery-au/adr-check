<!--
A reviewer, human or LLM, reads this before your diff.

The PR title becomes the commit subject on the trunk: Conventional Commits,
lowercase, 72 characters or fewer. The description becomes the commit body, so
everything below is permanent. AGENTS.md has the full conventions.
-->

## What

<!--
One paragraph, readable without opening the diff. Add why the change was needed,
and anything about the approach that would surprise a reviewer, where those are
not already obvious from the diff or the linked issue. A typo fix needs a
sentence; a change of approach needs the reasoning.
-->

## Testing

<!--
How you verified this. "Tested manually" is not enough. Say what you tested and
how. Write "None" if you did not verify it, because an empty field reads as an
oversight rather than a decision.

For a skill change, the useful evidence is that you loaded the skill and ran it
against something real, not that the markdown renders.
-->

Fixes: #

<!--
Fixes closes the issue on merge. Use Refs: instead where this is one of several
PRs against the same issue, so only the last one closes it.
-->
