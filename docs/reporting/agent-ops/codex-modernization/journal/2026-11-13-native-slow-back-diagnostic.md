# Native back-transition duration diagnostic

The matched Gazebo runs with and without patch0003 both fail the existing 2 m
altitude gate and show the same back-transition climb. One source-supported
contrast now selects `VT_B_TRANS_DUR=10` instead of the stock airframe's 5 s.
The existing canonical runner admits this native parameter through its fixture
allowlist; pinned YAML bounds, startup environment and pre-arm readback remain
the authority. A named stock measured-model fixture changes only that value.

Focused tests cover the single fixture difference, invalid values, both native
bounds and mismatched readback. No controller, gains, default configuration,
capture timing, ownership rules or acceptance gates change. This code-only
slice performs no native build, Docker or flight action. The one diagnostic run
requires separate review and preserved evidence; S7 remains blocked by the
retained native response failures.
