"""GitHub issue data contract only. No client, credentials or execution authority.

The existing HTTPS adapter supplies bounded bytes and the approved repository.
Links are verified as data; none are fetched. Extra upstream fields are discarded.
"""
from packages.contracts.tool import GITHUB_API_ORIGIN, checked_data


# Fixed reviewed headers, not operator/model-authored freeform header templates.
HEADERS = ("Accept: application/vnd.github+json\r\n"
    "X-GitHub-Api-Version: 2022-11-28\r\nUser-Agent: ARYN-GitHub-Issue-Reader\r\n")

RAW_SCHEMA = {"type": "object", "properties": {
    "number": {"type": "integer", "minimum": 1, "maximum": 2147483647},
    "title": {"type": "string", "minLength": 1, "maxLength": 256},
    "state": {"enum": ["open", "closed"]},
    "body": {"type": ["string", "null"], "maxLength": 16384},
    "url": {"type": "string", "maxLength": 256},
    "html_url": {"type": "string", "maxLength": 256},
    "repository_url": {"type": "string", "maxLength": 256}},
    "required": ["number", "title", "state", "body", "url", "html_url", "repository_url"],
    "additionalProperties": True, "not": {"required": ["token"]}}


class GitHubResponseError(LookupError):
    """Only fixed error codes cross the transport boundary; upstream text never does."""
    def __init__(self, status):
        self.code = {401: "github_unauthorized", 403: "github_forbidden", 404: "github_issue_not_found",
            429: "github_rate_limited"}.get(status, "github_service_error" if 500 <= status <= 599 else "github_response_rejected")
        super().__init__(self.code)


def request_route(spec, arguments):
    checked_data(arguments, spec.declaration.input_schema)
    number = arguments.get("issue_number")
    if type(number) is not int or not 1 <= number <= 2147483647:
        raise ValueError("A bounded positive issue number is required.")
    return spec.route.replace("{key}", str(number))


def normalize_issue(spec, arguments, raw):
    checked_data(raw, RAW_SCHEMA, spec.max_response_bytes)
    number = arguments["issue_number"]
    repository = spec.repository_owner + "/" + spec.repository_name
    api = "https://api.github.com/repos/" + repository
    page = f"https://github.com/{repository}/issues/{number}"
    # The issues endpoint also returns pull requests: reject every such object.
    if ("pull_request" in raw or type(raw["number"]) is not int or raw["number"] != number
            or raw["repository_url"] != api or raw["url"] != f"{api}/issues/{number}"
            or raw["html_url"] != page):
        raise ValueError("GitHub issue identity could not be verified.")
    body = raw["body"] or ""
    data = {"organization_id": spec.organization_id, "project_id": spec.project_id,
        "repository": repository, "kind": "issue", "issue_number": number, "title": raw["title"],
        "state": raw["state"], "url": page, "body_excerpt": body[:1024], "body_truncated": len(body) > 1024,
        "content_trust": "untrusted", "source": "github_https" if spec.endpoint == GITHUB_API_ORIGIN else "github_https_fixture"}
    return checked_data(data, spec.output_schema, spec.max_response_bytes)
