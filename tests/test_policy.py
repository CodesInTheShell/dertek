from dertek.security.policy import CommandPolicy


def test_safe_command_allowed() -> None:
    decision = CommandPolicy().evaluate_shell("git diff", "on-request")
    assert decision.action == "allow"
    assert decision.argv == ("git", "diff")


def test_unknown_command_asks() -> None:
    decision = CommandPolicy().evaluate_shell("python script.py", "on-request")
    assert decision.action == "ask"


def test_dangerous_command_denied() -> None:
    decision = CommandPolicy().evaluate_shell("sudo reboot", "on-request")
    assert decision.action == "deny"


def test_compound_safe_prefix_requires_approval() -> None:
    assert CommandPolicy().evaluate_shell("git diff; touch unexpected").action == "ask"


def test_pipe_redirect_substitution_and_find_require_approval() -> None:
    policy = CommandPolicy()
    for command in ("git diff | less", "git diff > diff.txt", "git diff $(pwd)", "find . -exec rm {} \\;"):
        assert policy.evaluate_shell(command).action == "ask"


def test_rg_preprocessor_requires_approval() -> None:
    assert CommandPolicy().evaluate_shell("rg --pre executable needle").action == "ask"
