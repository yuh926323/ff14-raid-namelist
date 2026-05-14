#!/usr/bin/env bash
set -euo pipefail

bot_pid=""

shutdown() {
    if [[ -n "${bot_pid}" ]] && kill -0 "${bot_pid}" 2>/dev/null; then
        kill "${bot_pid}"
        wait "${bot_pid}" 2>/dev/null || true
    fi
}

trap shutdown TERM INT

is_placeholder() {
    [[ "$1" == replace-with-* ]]
}

if [[ -n "${DISCORD_BOT_TOKEN:-}" ]] \
    && [[ -n "${DISCORD_CHANNEL_ID:-}" ]] \
    && ! is_placeholder "${DISCORD_BOT_TOKEN}" \
    && ! is_placeholder "${DISCORD_CHANNEL_ID}"; then
    echo "Starting FF14 raid namelist bot..."
    cd /works/ff14-raid-namelist
    python -m ff14_raid_namelist.bot &
    bot_pid="$!"
else
    echo "Python workspace is ready."
    echo "Set DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID in /works/ff14-raid-namelist/.env to auto-start the bot."
fi

while true; do
    sleep 1d &
    wait "$!" || true
done
