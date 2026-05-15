#!/usr/bin/env bash
set -euo pipefail

pids=()
names=()

shutdown() {
    for pid in "${pids[@]:-}"; do
        if kill -0 "${pid}" 2>/dev/null; then
            kill "${pid}" 2>/dev/null || true
        fi
    done

    for pid in "${pids[@]:-}"; do
        wait "${pid}" 2>/dev/null || true
    done
}

trap shutdown TERM INT

is_placeholder() {
    [[ "$1" == replace-with-* ]]
}

looks_like_bot_token() {
    [[ "${#1}" -ge 50 && "$1" == *.* && "$1" != *" "* ]]
}

has_env_value() {
    local env_file="$1"
    local key="$2"
    local value

    [[ -f "${env_file}" ]] || return 1
    value="$(grep -E "^${key}=" "${env_file}" | tail -n 1 | cut -d= -f2- | tr -d '[:space:]' || true)"
    [[ -n "${value}" && "${value}" != replace-with-* ]]
}

start_process() {
    local name="$1"
    local workdir="$2"
    shift 2

    echo "Starting ${name}..."
    (
        cd "${workdir}"
        exec "$@"
    ) &

    names+=("${name}")
    pids+=("$!")
}

if [[ -n "${DISCORD_BOT_TOKEN:-}" ]] \
    && [[ -n "${DISCORD_CHANNEL_ID:-}" ]] \
    && ! is_placeholder "${DISCORD_BOT_TOKEN}" \
    && ! is_placeholder "${DISCORD_CHANNEL_ID}" \
    && looks_like_bot_token "${DISCORD_BOT_TOKEN}"; then
    start_process "FF14 raid namelist bot" /works/ff14-raid-namelist python -m ff14_raid_namelist.bot
else
    echo "Set a valid bot token and channel ID in /works/ff14-raid-namelist/.env to auto-start the bot."
fi

if [[ -f /works/XClientTransaction/main.py ]]; then
    start_process "XClientTransaction API" /works/XClientTransaction gunicorn --bind 0.0.0.0:5000 --workers 2 --threads 2 main:app
else
    echo "Skipping XClientTransaction API; /works/XClientTransaction/main.py was not found."
fi

if has_env_value /works/Artale_Robot/.env DISCORD_TOKEN; then
    start_process "Artale Robot bot" /works/Artale_Robot python artale.py
else
    echo "Set DISCORD_TOKEN in /works/Artale_Robot/.env to auto-start Artale Robot."
fi

if [[ "${#pids[@]}" -eq 0 ]]; then
    echo "Python workspace is ready. No auto-start services are configured."
fi

while true; do
    for index in "${!pids[@]}"; do
        pid="${pids[$index]}"
        name="${names[$index]}"
        if ! kill -0 "${pid}" 2>/dev/null; then
            status=0
            wait "${pid}" || status="$?"
            echo "${name} exited with status ${status}; stopping python workspace."
            shutdown
            exit "${status}"
        fi
    done
    sleep 5
done
