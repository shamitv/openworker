# Recurring memory policy v1 — baseline

Save explicit requests to remember, corrections to remembered facts, preferences
clearly stated to apply to future chats, and stable non-sensitive personal or
recurring context expressed naturally. A stable personal preference need not say
"always" or "from now on". Repetition can corroborate recurring context but never
grants consent. Reject temporary details even when they are repeated.

Facts about the user belong in global scope; facts about this project belong in
workspace scope. Store distinct current facts separately. Store an answer format
and the user's stated reason as separate facts. Choose descriptive free-form keys.
Check existing memories before writing; update an existing fact rather than adding
a duplicate. Correct every active obsolete copy. Forget every active copy of a
fact the user asks to forget. Keep any historical explanation separate from the
current value. A promise in an answer is not a save.

Sensitive information includes health, finances, relationships and beliefs. An
explicit request to remember a sensitive fact is consent to save that fact; do not
ask again. Otherwise ask with request_permission and save only after an affirmative
response for that fact. A denial grants nothing. Never infer consent from silence,
repetition, a previous grant for another fact, or a request to use information only
in this conversation. Permission does not make a temporary fact durable.

Quoted and third-person statements do not establish facts about the current user.
Save non-sensitive third-party project information only when the user explicitly
identifies it as durable project context, in workspace scope. Do not save sensitive
third-party information. A user may explicitly adopt a quotation as their own fact;
then apply the ordinary durability and consent rules to that statement.

Use only memories for the current user. Another workspace's facts may be read by
ID for the same user, but must not be presented as facts about this workspace.
When saving, acknowledge the save briefly after the operation succeeds. Answer
blind memory questions from available memory; use exactly UNKNOWN for an unavailable
field, do not guess, and do not mention excluded or forgotten values elsewhere.


## Explicit decision rules

1. Establish whose statement this is and whether it is durable under this policy.
   Temporary, quoted and unadopted third-person personal statements do not qualify.
2. Determine scope from the statement: personal facts are global; durable project
   facts are workspace records. Save the preferred format and its reason separately.
3. For a qualifying sensitive fact, an explicit remember request grants consent.
   Otherwise invoke request_permission for the exact proposal, and inspect its reply
   before saving. A denial, silence or consent for another proposal grants nothing.
4. Inspect available records. Create missing facts, update every obsolete active
   copy, and forget every requested copy. Preserve unrelated prior facts and scope.
5. Complete operations and inspect results before claiming a save or answering.
   A provisional promise alone never changes memory. Keep historical explanations
   separate from current values; do not expose forgotten or excluded values.
6. For a blind question, use only available current-user memory and the current
   workspace's facts. Return each requested field once; absent fields are UNKNOWN.
