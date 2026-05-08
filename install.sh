#!/usr/bin/env bash
# context-absorb installer
# Usage:
#   curl -sSL https://raw.githubusercontent.com/ThatGuyAstro/context-absorb/main/install.sh | bash
#   CONTEXT_ABSORB_DIR=/custom/path bash install.sh

set -euo pipefail

REPO_URL="https://github.com/ThatGuyAstro/context-absorb.git"
DEFAULT_DIR="${HOME}/.local/share/context-absorb-src"
TARGET_DIR="${CONTEXT_ABSORB_DIR:-${DEFAULT_DIR}}"

log() {
    printf '[context-absorb] %s\n' "$*"
}

err() {
    printf '[context-absorb] ERROR: %s\n' "$*" >&2
}

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        err "required command not found: $1"
        err "$2"
        exit 1
    fi
}

check_python_version() {
    local version major minor
    version="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "")"
    if [ -z "$version" ]; then
        err "could not determine python3 version"
        exit 1
    fi
    major="${version%%.*}"
    minor="${version#*.}"
    if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 10 ]; }; then
        err "python3 >= 3.10 required, found ${version}"
        err "install a newer python3 (https://www.python.org/downloads/) and re-run"
        exit 1
    fi
    log "python3 ${version} detected"
}

detect_rc_file() {
    local shell_name
    shell_name="$(basename "${SHELL:-}")"
    case "$shell_name" in
        zsh) printf '%s' "${HOME}/.zshrc" ;;
        bash)
            if [ -f "${HOME}/.bashrc" ]; then
                printf '%s' "${HOME}/.bashrc"
            else
                printf '%s' "${HOME}/.bash_profile"
            fi
            ;;
        fish) printf '%s' "${HOME}/.config/fish/config.fish" ;;
        *) printf '%s' "${HOME}/.profile" ;;
    esac
}

path_contains_local_bin() {
    case ":${PATH}:" in
        *":${HOME}/.local/bin:"*) return 0 ;;
        *) return 1 ;;
    esac
}

main() {
    log "starting install"
    log "target directory: ${TARGET_DIR}"

    require_cmd python3 "install python3 >= 3.10 from https://www.python.org/downloads/"
    require_cmd git "install git from https://git-scm.com/downloads"
    check_python_version

    if [ -d "${TARGET_DIR}/.git" ]; then
        log "existing checkout found, pulling latest"
        git -C "${TARGET_DIR}" pull --ff-only
    elif [ -e "${TARGET_DIR}" ]; then
        err "${TARGET_DIR} exists but is not a git repo"
        err "remove it or set CONTEXT_ABSORB_DIR to a different path"
        exit 1
    else
        log "cloning ${REPO_URL}"
        mkdir -p "$(dirname "${TARGET_DIR}")"
        git clone "${REPO_URL}" "${TARGET_DIR}"
    fi

    log "running session_absorb_core install"
    python3 "${TARGET_DIR}/skills/shared/session_absorb_core.py" install --repo-root "${TARGET_DIR}"

    log "install complete"
    log ""
    log "next steps:"

    if path_contains_local_bin; then
        log "  PATH already contains ~/.local/bin"
    else
        local rc_file
        rc_file="$(detect_rc_file)"
        log "  ~/.local/bin is NOT in PATH - add it to ${rc_file}:"
        log "    echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ${rc_file}"
        log "    source ${rc_file}"
    fi

    log ""
    log "  optional shell alias for shorter invocation:"
    local rc_file
    rc_file="$(detect_rc_file)"
    log "    echo 'alias sa=\"session-absorb\"' >> ${rc_file}"
    log ""
    log "  verify install:"
    log "    session-absorb list --limit 5"
}

main "$@"
