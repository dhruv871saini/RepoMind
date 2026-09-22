# agent/graph/state.py
from typing import TypedDict, Optional

class AgentState(TypedDict):
    # Input
    problem:       str           # "the login function crashes when..."
    repo_id:       str           # UUID of the repo in your DB
    repo_path:     str           # "repositories/org__reponame"

    # After retrieve node
    context:       list[dict]    # chunks from /retriver/ endpoint
    located_files: list[str]     # file paths relevant to the problem

    # After verify node
    problem_is_real:  bool
    verify_reasoning: str        # LLM's explanation

    # After coder node
    patch:         str           # unified diff
    changed_files: list[str]     # which files the patch touches

    # After sandbox node
    sandbox_passed:  bool
    sandbox_log:     str         # stdout/stderr from test run
    retry_count:     int

    # After open_pr node
    branch_name:   str
    pr_url:        str

    # Final output
    final_report:  str