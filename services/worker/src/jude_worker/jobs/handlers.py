"""Registered job handlers: job type (e.g. ``regenerate.v1``) -> handler (FN-JOB-02 step 3).

Each handler takes the job payload (DS-17, job/1) and returns the kernel's OpResult. Handlers
arrive with the tasks that own each job type (FN-SCN, FN-DES, FN-EXP ...); a job whose type has
no handler fails with JOB_TYPE_UNKNOWN.
"""

from collections.abc import Mapping
from types import MappingProxyType

from jude_worker.jobs.executor import Handler

HANDLERS: Mapping[str, Handler] = MappingProxyType({})
