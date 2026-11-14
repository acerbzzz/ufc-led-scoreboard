#!/bin/sh
set -eu
cd /home/pi/ufc-led-scoreboard
sudo install -m 0644 scripts/ufc-led-scoreboard.service /etc/systemd/system/ufc-led-scoreboard.service
sudo systemctl daemon-reload
sudo systemctl enable ufc-led-scoreboard.service
sudo systemctl restart ufc-led-scoreboard.service
systemctl is-active ufc-led-scoreboard.service
