from dertek.security.policy import CommandPolicy


def test_safe_command_allowed() -> None:
    decision = CommandPolicy().evaluate_shell("git diff", "on-request")
    assert decision.action == "allow"
    assert decision.argv == ("git", "diff")


def test_unknown_command_asks() -> None:
    decision = CommandPolicy().evaluate_shell("python script.py", "on-request")
    assert decision.action == "ask"


def test_unknown_command_is_denied_in_never_mode() -> None:
    decision = CommandPolicy().evaluate_shell("python script.py", "never")
    assert decision.action == "deny"


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


def test_auto_approves_commands_that_would_ask() -> None:
    policy = CommandPolicy()
    for command in (
        "python script.py",
        "git diff | less",
        "git diff > diff.txt",
        "git diff $(pwd)",
        "find . -exec echo {} \\;",
        "pytest",
        "touch created.txt",
    ):
        decision = policy.evaluate_shell(command, "auto")
        assert decision.action == "allow"
        assert decision.auto_approved is True
        assert decision.argv is None


def test_auto_never_bypasses_dangerous_command_denials() -> None:
    policy = CommandPolicy()
    for command in (
        "sudo reboot",
        "rm -rf /",
        "mkfs.ext4 /dev/sda",
        "shutdown now",
        "dd if=/dev/zero of=/dev/sda",
    ):
        decision = policy.evaluate_shell(command, "auto")
        assert decision.action == "deny"
        assert decision.auto_approved is False


def test_read_only_command_in_auto_retains_direct_argv() -> None:
    decision = CommandPolicy().evaluate_shell("git diff", "auto")
    assert decision.action == "allow"
    assert decision.argv == ("git", "diff")
    assert decision.auto_approved is False
