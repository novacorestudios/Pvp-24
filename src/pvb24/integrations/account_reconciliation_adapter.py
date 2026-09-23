"""Fail-closed runtime boundary for account/position reconciliation."""

from dataclasses import dataclass
from datetime import timedelta

from pvb24.accounting.reconciliation import OpenReconciler


@dataclass(frozen=True)
class ReconciliationPolicy:
    max_account_age: timedelta
    max_mark_age: timedelta
    require_verified: bool = True

    def __post_init__(self):
        if (
            not isinstance(self.max_account_age, timedelta)
            or self.max_account_age < timedelta(0)
            or not isinstance(self.max_mark_age, timedelta)
            or self.max_mark_age < timedelta(0)
            or type(self.require_verified) is not bool
        ):
            raise ValueError("Explicit nonnegative reconciliation policy required")


class AccountReconciliationAdapter:
    """Reconcile only shared-core owned positions; never mutate foreign positions."""

    def __init__(self, journal, scope, policy: ReconciliationPolicy):
        if not scope or not isinstance(policy, ReconciliationPolicy):
            raise ValueError("Explicit reconciliation scope and policy required")
        self.reconciler = OpenReconciler(journal, scope)
        self.policy = policy

    def reconcile(self, observed, now, *, reduction_models=None):
        return self.reconciler.reconcile(
            observed,
            now,
            max_account_age=self.policy.max_account_age,
            max_mark_age=self.policy.max_mark_age,
            require_verified=self.policy.require_verified,
            reduction_models=reduction_models,
        )
