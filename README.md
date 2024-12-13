# tattle-phone
Raspberry Pi + Rotary telephone so my kids can tattle as much as they like

## Notes on running
1) Requires `sox` to be installed
2) Requires `espeak-ng` to be installed
3) Need to GPIO pins connected to both the DIAL and the HOOK circuits of the phone, and you need to know which pins they are. In my case it was 12 and 16. This is something that's currently hard-coded into tattle-core.py, but which could easily be a config file somewhere or a command line parameter.

## Manual install
Currently the install is totally manual, here's what I did:
* Created the folder `/var/lib/tattles` to store the kids tattles and confessions
* Created the folder `/opt/tattle` to store this code
* Created the executable `/usr/local/bin/tattle` which just calls the tattle-core python script in `/opt/tattle/src`

## Starting automatically at startup
Confession: still working on this 🤣