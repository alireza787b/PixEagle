# Terminal retarget admission

Independent recovery review reproduced a supervisor state gap: a retarget could
change `HANDOFF_PENDING` back to recovery while retaining the pending handoff
record. Native transport abort/acquisition guards already prevented this from
establishing renewed aircraft authority; no such escape is demonstrated.

One supervisor predicate now permits retarget only during active or bounded
recovery authority without a pending handoff. The controller reuses it before
follower preparation, carryover submission or tracker mutation. The supervisor
also applies it at target-generation commit. Pending, failed and completed
handoffs cannot reopen; ordinary MC/FW retargets retain their original budgets.

Eight new MC/FW regressions fail before the fix and pass afterward. The focused
continuity/admission suite passes 72 checks; all 2,094 core-application tests and
95 API inventory/documentation checks pass, with no fatal Python lint findings.
Actual native lifecycle qualification remains separate. No configuration,
timing, limit, hardware or firmware change is made.
