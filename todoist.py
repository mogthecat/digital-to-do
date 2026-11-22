"""Minimal Todoist API v1 client for MicroPython."""

import gc
import requests

_BASE = "https://api.todoist.com/api/v1"


class TodoistError(Exception):
    pass


class Todoist:
    def __init__(self, token, timeout=15):
        self._headers = {"Authorization": "Bearer " + token}
        self._timeout = timeout
        self._inbox_id = None

    def _request(self, method, path):
        gc.collect()
        try:
            r = requests.request(method, _BASE + path, headers=self._headers,
                                 timeout=self._timeout)
        except OSError as e:
            raise TodoistError("Network error: %s" % e)
        try:
            if not 200 <= r.status_code < 300:
                raise TodoistError("HTTP %d" % r.status_code)
            data = r.json() if r.status_code != 204 else None
        finally:
            r.close()
        gc.collect()
        return data

    def get_inbox_id(self):
        """ID of the Inbox project (looked up once, then cached)."""
        if self._inbox_id is None:
            for p in self._request("GET", "/projects?limit=200")["results"]:
                if p.get("inbox_project"):
                    self._inbox_id = p["id"]
                    break
            else:
                raise TodoistError("Inbox not found")
        return self._inbox_id

    def get_tasks(self, project_id):
        """Return a list of (id, content) tuples in Todoist's order."""
        tasks = []
        cursor = None
        while True:
            path = "/tasks?limit=50&project_id=" + project_id
            if cursor:
                path += "&cursor=" + cursor
            data = self._request("GET", path)
            for t in data["results"]:
                tasks.append((t.get("child_order", 0), t["id"], t["content"]))
            cursor = data.get("next_cursor")
            del data  # free this page before fetching the next (saves RAM)
            if not cursor:
                break
        tasks.sort(key=lambda t: t[0])
        return [(tid, content) for _, tid, content in tasks]

    def close_task(self, task_id):
        """Mark a task complete."""
        self._request("POST", "/tasks/%s/close" % task_id)
