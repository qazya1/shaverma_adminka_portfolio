"""New-service provisioning: turning an admin's form submission into a
fully deployed shaverma instance (DB row, instance directory, uploaded
code, generated .env, built frontend, nginx entry, systemd unit).

Each step is its own API endpoint / function here, deliberately not
wrapped in one all-or-nothing transaction -- see app/api/provisioning.py
and the README for why (heterogeneous side effects across the DB,
filesystem, an external project's own database writes, nginx, and
systemd can't be rolled back atomically as a group). Every step is
instead safe to re-run: it either checks live reality before acting, or
overwrites/replaces rather than blindly appending.
"""
