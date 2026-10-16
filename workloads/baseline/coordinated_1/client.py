"""Compatibility surface: synchronous imports retain list-of-issues output."""


class ImportClient:
    def __init__(self, tracker, tenant="default"):
        self.tracker = tracker
        self.tenant = tenant

    def submit(self, request_key, csv_text):
        return self.tracker.submit_import(self.tenant, request_key, csv_text)

    def import_csv(self, csv_text, request_key="legacy"):
        job_id = self.submit(request_key, csv_text)
        if self.tracker.status(self.tenant, job_id)["status"] not in ("complete", "cancelled"):
            self.tracker.process_batch(self.tenant, job_id)
        if self.tracker.status(self.tenant, job_id)["status"] == "cancelled":
            raise ValueError("import was cancelled")
        return self.tracker.list_issues(self.tenant)
