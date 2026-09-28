#!/bin/sh
# Siddh farm kiosk watchdog.
#
# The kiosk is two halves and only one of them is under systemd's control: the
# Node server is a unit, but Chromium is started from the Openbox session (see
# /etc/xdg/openbox/autostart) and dies with it. This loop watches both and
# bounces whichever one has gone away.
#
# Started by siddh-watchdog.service, which invokes it as `/bin/sh <script>`, so
# the file does not need the executable bit set inside the live image.

set -u

KIOSK_URL="http://localhost:3000/kiosk"
INTERVAL=15

# Consecutive failed checks tolerated before acting, so that a service which is
# still coming up is not fought with.
APP_FAILS_MAX=3
SESSION_FAILS_MAX=4

# Never bounce the graphical session more often than this, in seconds.
SESSION_RESTART_GAP=120

app_fails=0
session_fails=0
last_session_restart=0

log() {
  echo "siddh-watchdog: $*"
}

while :; do
  sleep "$INTERVAL"

  # 1. The Node server: let systemd do the restarting, we only decide when.
  if systemctl is-active --quiet siddh-app.service; then
    app_fails=0
  else
    app_fails=$((app_fails + 1))
    log "siddh-app.service is not active ($app_fails/$APP_FAILS_MAX)"
    if [ "$app_fails" -ge "$APP_FAILS_MAX" ]; then
      log "restarting siddh-app.service"
      systemctl restart siddh-app.service
      app_fails=0
    fi
  fi

  # 2. The kiosk browser. Chromium carries the only window on screen, so if it
  #    is gone the wall shows an empty Openbox desktop. Restarting the whole
  #    session is the cheapest reliable recovery, rate limited so that a
  #    browser which cannot start at all does not become a restart loop.
  if ! systemctl is-active --quiet nodm.service; then
    session_fails=0
    continue
  fi

  if pgrep -f -- "chromium.*--app=$KIOSK_URL" >/dev/null 2>&1; then
    session_fails=0
    continue
  fi

  session_fails=$((session_fails + 1))
  log "kiosk browser not found ($session_fails/$SESSION_FAILS_MAX)"
  if [ "$session_fails" -lt "$SESSION_FAILS_MAX" ]; then
    continue
  fi

  now=$(date +%s)
  if [ $((now - last_session_restart)) -lt "$SESSION_RESTART_GAP" ]; then
    log "session restart rate limited, still waiting"
    continue
  fi

  log "restarting nodm.service (kiosk session)"
  systemctl restart nodm.service
  last_session_restart=$(date +%s)
  session_fails=0
done
