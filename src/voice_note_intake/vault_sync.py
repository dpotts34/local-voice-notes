from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from urllib.parse import urlsplit

from .spool import open_private_directory, _fsync_directory


class VaultSyncError(RuntimeError):
    pass


class VaultSync:
    """Restricted publication using the original stash/fast-forward/lint/read-back flow."""

    def __init__(self, vault: Path, state_dir: Path, repo: Path, remote: str,
                 branch: str = "main", ssh_key: Path | None = None) -> None:
        self.vault, self.state_dir, self.repo = vault, state_dir, repo
        self.remote, self.branch = remote, branch
        self.recovery = state_dir / "vault-sync-recovery.json"
        # Never let ambient Git overrides select a different worktree/index/config.
        self.git_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.git_env.update(GIT_TERMINAL_PROMPT="0", GIT_LITERAL_PATHSPECS="1",
                            GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        if ssh_key is not None:
            if not ssh_key.is_absolute() or ssh_key.resolve() != ssh_key or not ssh_key.is_file():
                raise VaultSyncError("SSH key boundary must be an explicit canonical regular file")
            self.git_env["GIT_SSH_COMMAND"] = f"ssh -F /dev/null -i {shlex.quote(str(ssh_key))} -o IdentitiesOnly=yes -o BatchMode=yes"
        self._boundary()
        self.prefix = vault.relative_to(repo)

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", "-C", str(self.repo), *args],
            capture_output=True, env=self.git_env, timeout=60,
        )
        result = subprocess.CompletedProcess(result.args, result.returncode,
                                             result.stdout.decode("utf-8", "surrogateescape"),
                                             result.stderr.decode("utf-8", "surrogateescape"))
        if check and result.returncode:
            raise VaultSyncError(f"git {' '.join(args)} failed: {(result.stderr or result.stdout).strip()}")
        return result

    def _boundary(self) -> None:
        for path in (self.repo, self.vault):
            if (not path.is_absolute() or '..' in path.parts or path == Path(path.anchor)
                    or path.resolve() != path or not path.is_dir()):
                raise VaultSyncError("repository/vault boundary must be existing absolute canonical directories")
        if (not self.vault.is_relative_to(self.repo) or '.git' in self.vault.parts
                or any(part.startswith('.') for part in self.vault.relative_to(self.repo).parts)):
            raise VaultSyncError("vault boundary must be within the repository, outside hidden/Git metadata")
        if ((self.repo / 'src/voice_note_intake').exists()
                or Path(__file__).resolve().is_relative_to(self.repo)):
            raise VaultSyncError("source checkout is not a vault publication boundary")
        metadata = self.repo / '.git'
        if not metadata.is_dir() or metadata.is_symlink():
            raise VaultSyncError("repository boundary must be an ordinary checkout with a real .git directory")
        if self._git('rev-parse', '--show-toplevel').stdout.strip() != str(self.repo):
            raise VaultSyncError("repository boundary is not the Git checkout root")
        for parent in (self.vault, *self.vault.parents):
            if parent == self.repo:
                break
            if (parent / '.git').exists():
                raise VaultSyncError("nested Git checkout is not a vault boundary")
        for name in ('Voice Inbox', 'Voice Threads'):
            directory = self.vault / name
            if directory.exists() and (directory.resolve() != directory or not directory.is_dir()
                                       or (directory / '.git').exists()):
                raise VaultSyncError("generated output boundary must be canonical directories, not nested Git checkouts")
        if self._git('check-ref-format', '--branch', self.branch, check=False).returncode:
            raise VaultSyncError("branch boundary must be a valid branch name")
        remote_path = Path(self.remote)
        if remote_path.is_absolute():
            if ('..' in remote_path.parts or remote_path.resolve() != remote_path
                    or not remote_path.is_dir() or remote_path.is_relative_to(self.repo)):
                raise VaultSyncError("local remote boundary must be a canonical bare repository outside the checkout")
            result = subprocess.run(['git', '-C', str(remote_path), 'rev-parse', '--is-bare-repository'],
                                    env=self.git_env, capture_output=True, text=True, timeout=60)
            if result.returncode or result.stdout.strip() != 'true':
                raise VaultSyncError("local remote boundary must be a bare repository")
        else:
            url = urlsplit(self.remote)
            if (url.scheme not in {'https', 'ssh'} or not url.hostname or not url.path
                    or url.password is not None or url.query or url.fragment):
                raise VaultSyncError("remote boundary must be an explicit https/ssh URL or absolute local bare path")

    def _changed_paths(self) -> list[str]:
        entries = self._git('status', '--porcelain=v1', '-z', '--untracked-files=all').stdout.split('\0')
        paths, index = [], 0
        lock = (self.prefix / 'Voice Inbox/.write.lock').as_posix()
        while index < len(entries) and entries[index]:
            entry = entries[index]
            if not (entry[:2] == '??' and entry[3:] == lock):
                paths.append(entry[3:])
            if 'R' in entry[:2] or 'C' in entry[:2]:
                index += 1
                paths.append(entries[index])
            index += 1
        return paths

    def _scope(self, paths: list[str]) -> None:
        outside = []
        for path in paths:
            p = Path(path)
            try:
                relative = p.relative_to(self.prefix)
            except ValueError:
                outside.append(path)
                continue
            if (relative.parent not in {Path('Voice Inbox'), Path('Voice Threads')}
                    or relative.suffix != '.md' or relative.name.startswith('.') or '..' in p.parts):
                outside.append(path)
        if outside:
            raise VaultSyncError('changes outside generated voice paths: ' + ', '.join(outside))

    def _history_scope(self, start: str, end: str) -> None:
        # Inspect every commit, not a net diff that can hide unrelated changes followed by a revert.
        for commit in self._git('rev-list', f'{start}..{end}').stdout.splitlines():
            paths = self._git('diff-tree', '--root', '-m', '--no-commit-id', '--name-only', '-r', '-z', commit).stdout.split('\0')
            self._scope([p for p in paths if p])

    def _lint(self) -> None:
        result = subprocess.run([sys.executable, '-m', 'voice_note_intake.lint_vault', '--vault', str(self.vault)],
                                text=True, capture_output=True, env=self.git_env, timeout=60)
        if result.returncode:
            raise VaultSyncError('vault lint failed: ' + (result.stdout + result.stderr).strip())

    def _generated(self, paths: list[str]) -> None:
        for path in paths:
            target = self.repo / path
            if target.resolve() != target or not target.is_file():
                raise VaultSyncError('generated publication requires canonical regular notes; deletion is refused: ' + path)
            relative = target.relative_to(self.vault)
            text = target.read_text(encoding='utf-8')
            field = 'request_id' if relative.parent == Path('Voice Inbox') else 'thread_id'
            if not re.match(r'---\n' + field + r': "[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"\n', text):
                raise VaultSyncError('unrelated note lacks generated identity: ' + path)

    def _journal(self, stash: str | None, phase: str, error: str | None = None) -> None:
        data = dict(repo=str(self.repo), vault=str(self.vault), remote=self.remote, branch=self.branch,
                    stash=stash, phase=phase, error=error, head=self._git('rev-parse', 'HEAD').stdout.strip())
        fd = os.open(self.recovery, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        _fsync_directory(self.state_dir)

    def run(self, message: str = 'Sync voice notes') -> None:
        os.close(open_private_directory(self.state_dir, create=True, label='state'))
        lock_fd = os.open(self.state_dir / 'vault-sync.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self.recovery.exists():
                raise VaultSyncError('publication recovery requires operator inspection: ' + str(self.recovery))
            self._boundary()
            for marker in ('MERGE_HEAD', 'REBASE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'BISECT_LOG',
                           'rebase-merge', 'rebase-apply', 'sequencer', 'index.lock'):
                if (self.repo / '.git' / marker).exists():
                    raise VaultSyncError('Git operation already in progress: ' + marker)
            if self._git('symbolic-ref', '--quiet', '--short', 'HEAD', check=False).stdout.strip() != self.branch:
                raise VaultSyncError('checkout must be on the selected branch')
            paths = self._changed_paths()
            self._scope(paths)
            self._lint()
            self._generated(paths)
            stash_ref, stash_applied = None, False
            phase = 'validated'
            try:
                if paths:
                    previous = self._git('rev-parse', '-q', '--verify', 'refs/stash', check=False).stdout.strip()
                    phase = 'stashing'
                    self._journal(None, phase)
                    self._git('stash', 'push', '--include-untracked', '-m', 'voice-note-vault-sync', '--', *paths)
                    stash_ref = self._git('rev-parse', 'refs/stash').stdout.strip()
                    if stash_ref == previous:
                        stash_ref = None  # Never restore or clean up somebody else's preexisting stash.
                        raise VaultSyncError('Git did not preserve generated changes in a stash')
                    self._journal(stash_ref, 'stashed')
                phase = 'fetch'
                self._git('fetch', '--no-tags', '--no-recurse-submodules', self.remote, 'refs/heads/' + self.branch)
                remote_head = self._git('rev-parse', 'FETCH_HEAD').stdout.strip()
                if self._git('ls-tree', remote_head, '--', 'src/voice_note_intake').stdout.strip():
                    raise VaultSyncError('remote source checkout is not a vault publication boundary')
                phase = 'fast-forward'
                if self._git('merge-base', '--is-ancestor', 'HEAD', remote_head, check=False).returncode == 0:
                    self._history_scope('HEAD', remote_head)
                    self._git('merge', '--ff-only', remote_head)
                elif self._git('merge-base', '--is-ancestor', remote_head, 'HEAD', check=False).returncode != 0:
                    raise VaultSyncError('local and selected remote branch have diverged')
                self._history_scope(remote_head, 'HEAD')
                if stash_ref:
                    phase = 'restore'
                    self._journal(stash_ref, phase)
                    stash_applied = True
                    if self._git('stash', 'apply', '--index', stash_ref, check=False).returncode:
                        raise VaultSyncError('restoring generated voice changes conflicted; stash was preserved')
                phase = 'lint-and-stage'
                self._lint()
                paths = self._changed_paths()
                self._scope(paths)
                self._generated(paths)
                if paths:
                    self._git('add', '-A', '--', *paths)
                staged = [p for p in self._git('diff', '--cached', '--name-only', '-z').stdout.split('\0') if p]
                self._scope(staged)
                if staged:
                    self._git('commit', '-m', message, '--', *staged)
                self._history_scope(remote_head, 'HEAD')
                outgoing = [p for p in self._git('diff', '--name-only', '-z', remote_head, 'HEAD').stdout.split('\0') if p]
                self._generated(outgoing)
                phase = 'push'
                self._git('push', self.remote, 'HEAD:refs/heads/' + self.branch)
                phase = 'remote-read-back'
                head = self._git('rev-parse', 'HEAD').stdout.strip()
                remote = self._git('ls-remote', self.remote, 'refs/heads/' + self.branch).stdout.split()
                if len(remote) != 2 or head != remote[0]:
                    raise VaultSyncError('remote head does not match the synced commit')
                if stash_ref:
                    if self._git('rev-parse', '-q', '--verify', 'refs/stash', check=False).stdout.strip() != stash_ref:
                        raise VaultSyncError('temporary stash changed before cleanup; recovery stash was preserved')
                    self._git('stash', 'drop', 'stash@{0}')
                if self.recovery.exists():
                    self.recovery.unlink()
                    _fsync_directory(self.state_dir)
            except BaseException as error:
                restore_error = None
                if stash_ref and not stash_applied:
                    try:
                        restored = self._git('stash', 'apply', '--index', stash_ref, check=False)
                        if restored.returncode:
                            restore_error = (restored.stderr or restored.stdout).strip()
                    except (OSError, subprocess.SubprocessError) as recovery_error:
                        restore_error = str(recovery_error)
                if stash_ref or self.recovery.exists():
                    self._journal(stash_ref, phase, str(error) + (f'; restore failed: {restore_error}' if restore_error else ''))
                raise
        finally:
            os.close(lock_fd)


def main() -> None:
    from .config import Config

    parser = argparse.ArgumentParser(description='Publish validated generated notes to an explicitly selected vault remote')
    parser.parse_args()
    try:
        config = Config.from_env()
        if config.vault_sync:
            VaultSync(config.vault_dir, config.state_dir, config.vault_repo_dir,
                      config.vault_remote, config.vault_branch, config.vault_git_ssh_key).run()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, f'vault publication refused: {error}\n')


if __name__ == '__main__':
    main()
