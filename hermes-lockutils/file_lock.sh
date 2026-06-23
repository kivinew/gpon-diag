#!/usr/bin/env bash
# File locking via atomic directory creation.
# Usage: source file_lock.sh
#        lock_file /path/to/file
#        ... critical section ...
#        unlock_file /path/to/file

LOCK_TIMEOUT="${LOCK_TIMEOUT:-30}"
LOCK_RETRY_INTERVAL="${LOCK_RETRY_INTERVAL:-0.1}"

lock_file() {
    local target="$1"
    local lock_dir="${target}.lock"
    local elapsed=0
    while true; do
        if mkdir "$lock_dir" 2>/dev/null; then
            echo "$$" > "${lock_dir}/pid"
            date +%s > "${lock_dir}/time"
            return 0
        fi
        # check stale lock
        if [ -d "$lock_dir" ]; then
            local lock_time=$(cat "${lock_dir}/time" 2>/dev/null || echo 0)
            local now=$(date +%s)
            local age=$(( now - lock_time ))
            if [ "$age" -gt "$LOCK_TIMEOUT" ]; then
                echo "WARNING: Stale lock detected (${age}s old), breaking: $lock_dir" >&2
                rm -rf "$lock_dir"
                continue
            fi
        fi
        elapsed=$(( elapsed + $(echo "$LOCK_RETRY_INTERVAL" | awk '{printf "%d", $1 * 1000}') ))
        if [ "$elapsed" -ge $(( LOCK_TIMEOUT * 1000 )) ]; then
            echo "ERROR: Failed to acquire lock after ${LOCK_TIMEOUT}s: $lock_dir" >&2
            return 1
        fi
        sleep "$LOCK_RETRY_INTERVAL"
    done
}

unlock_file() {
    local target="$1"
    local lock_dir="${target}.lock"
    rm -rf "$lock_dir"
}

is_locked() {
    local target="$1"
    local lock_dir="${target}.lock"
    [ -d "$lock_dir" ]
}

lock_info() {
    local target="$1"
    local lock_dir="${target}.lock"
    if [ -d "$lock_dir" ]; then
        local pid=$(cat "${lock_dir}/pid" 2>/dev/null || echo "unknown")
        local lock_time=$(cat "${lock_dir}/time" 2>/dev/null || echo 0)
        local now=$(date +%s)
        local age=$(( now - lock_time ))
        echo "Lock held by PID $pid, age: ${age}s, path: $lock_dir"
    else
        echo "No lock on $target"
    fi
}