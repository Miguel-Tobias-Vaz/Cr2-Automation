"""Estado compartilhado do servidor (JobManager singleton)."""

from backend.jobs import JobManager

jobs = JobManager()
