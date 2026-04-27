# Multi-Region Ops

Multi-Region Ops owns region configuration, replication status, failover plans, failover plan runs, maintenance windows, and active-window enforcement.

Primary entities include region configs, replication statuses, failover plans, plan runs, and maintenance windows. REST APIs manage regions and execute rehearsed failover plans. Redis stores active maintenance state and failover locks.

Application logic rejects active-active operation; production failover requires super admin authority and approval.
