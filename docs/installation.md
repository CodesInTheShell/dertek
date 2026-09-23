# Installation

Dertek is a Python 3.12+ command-line application. Install it as an isolated user tool with [`uv`](https://docs.astral.sh/uv/concepts/tools/) so the `dertek` command works from any project without activating Dertek's development environment.

## Install from a clone

```bash
git clone https://github.com/CodesInTheShell/dertek.git
cd dertek
uv tool install .
```

If uv reports that its tool executable directory is not on `PATH`, run:

```bash
uv tool update-shell
```

Restart the terminal and verify the installation:

```bash
dertek version
dertek doctor
```

`uv tool install` creates an isolated environment for Dertek. Target projects do not need Dertek in their own dependencies or virtual environments. Dertek implements its own agent loop and ChatGPT transport; users do not need to install the Codex CLI.

## Credentials

An installed tool does not use the `.env` file from the Dertek source directory when it is launched elsewhere. Provide credentials through your shell or an OS credential manager. Do not put them in `~/.dertek/settings.json`.

macOS or Linux:

```bash
export OPENAI_API_KEY="your-openai-key"
export TYPESAFE_API_KEY="your-typesafe-key"
```

Windows PowerShell:

```powershell
$env:OPENAI_API_KEY="your-openai-key"
$env:TYPESAFE_API_KEY="your-typesafe-key"
```

An OpenAI key is required only in API-key mode; ChatGPT authentication is documented below. The TypeSafe key enables Jev; without it, Dertek uses the conservative heuristic decision fallback.

## Use Dertek in another project

Launch Dertek from the project directory so that directory becomes the protected workspace:

```bash
cd /path/to/another-project
dertek doctor
dertek
```

One-shot requests work the same way:

```bash
dertek "explain this project"
dertek "find the authentication code"
dertek "run the tests and investigate failures"
```

You can stay in any directory and select a workspace explicitly:

```bash
dertek --workspace /path/to/another-project
dertek -C /path/to/another-project "explain this project"
```

File tools, patches, shell commands, sessions, and approvals are scoped to that workspace. The target does not need to be a Git repository.

## Update or remove

After pulling newer source code, reinstall the local package:

```bash
cd /path/to/dertek
git pull
uv tool install --force .
```

### Contributor editable installation

When developing Dertek, testing freshly pulled code, or following the latest source from a clone, install the checkout in editable mode using its absolute path:

```bash
uv tool install --force --editable /absolute/path/to/dertek
```

`--force` replaces an older installed tool, while `--editable` loads Python code directly from the checkout. After `git pull`, ordinary source changes are immediately visible; reinstall after dependency or packaging changes. Do not move or delete the checkout while the editable tool is installed.

Remove Dertek with:

```bash
uv tool uninstall dertek-cli
```

The uv tool environment is separate from `~/.dertek/`; uninstalling the executable does not delete saved settings or sessions.

## Troubleshooting: `dertek: command not found`

`uv tool update-shell` and `uv tool install` do different jobs:

- `uv tool install .` installs Dertek and creates the `dertek` executable.
- `uv tool update-shell` only adds uv's executable directory to `PATH`. It does not install Dertek.

First check whether Dertek is installed:

```bash
uv tool list
```

The output should include `dertek-cli` and its `dertek` executable. If it does not, install Dertek from the cloned repository:

```bash
cd /path/to/dertek
uv tool install .
```

If `uv tool list` shows Dertek but the shell still cannot find it, configure `PATH` and restart the terminal:

```bash
uv tool update-shell
```

On macOS or Linux, these commands show the expected executable directory and whether the command is currently discoverable:

```bash
uv tool dir --bin
command -v dertek
```

On Windows PowerShell:

```powershell
uv tool dir --bin
Get-Command dertek
```

After installation or a source update, verify the command directly:

```bash
dertek version
dertek doctor
```

If an older or incomplete installation exists, recreate it from the current checkout:

```bash
cd /path/to/dertek
uv tool install --force .
```

## Troubleshooting: stale code after an update

A normal uv tool installation contains a built copy of Dertek rather than loading Python files directly from the clone. If recently pulled fixes are not taking effect, uv may have reused a cached build with the same package version. Clean that cached package and force a fresh non-editable installation:

```bash
uv cache clean dertek-cli
uv tool install --force --refresh /absolute/path/to/dertek
```

For example, if the clone is under your Documents directory:

```bash
uv cache clean dertek-cli
uv tool install --force --refresh /home/your-name/Documents/REPO/dertek
```

Start a new `dertek` process after reinstalling. `--force` replaces the installed tool, while `--refresh` prevents uv from relying on stale cached package metadata or artifacts. Contributors making frequent source edits can instead use the editable installation described above.

## ChatGPT subscription authentication

Instead of exporting `OPENAI_API_KEY`, sign in through a browser:

```bash
dertek auth login
```

For SSH, containers, or headless systems:

```bash
dertek auth login --device-code
```

Then run `dertek --auth chatgpt`, or rely on the saved `openai_auth` setting created by login. Use `dertek --auth api-key` with an exported `OPENAI_API_KEY` to switch for one run. Switching modes leaves the owner-only ChatGPT credentials available for later use; `dertek auth logout` removes them but does not change the saved non-secret mode setting. Check with `dertek auth status` and `dertek doctor`. ChatGPT mode uses subscription limits, API-key mode uses API billing, and Dertek never silently falls back between them.

Browser login uses the registered local callback ports `1455` and `1457`. If both ports are already in use, close the processes using them or use the device-code flow. An `invalid_authorize_request` immediately after opening the browser usually means an older Dertek installation is still generating the authorization URL; refresh a normal installation with `uv tool install --force .`, or switch the clone to `uv tool install --force --editable /absolute/path/to/dertek`, and retry.
